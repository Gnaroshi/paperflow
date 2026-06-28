from __future__ import annotations

from collections import Counter
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from paperflow.backup import write_backup_snapshot
from paperflow.migration_models import ApplyOperation, ApplyPreview, MigrationPlan
from paperflow.taxonomy_v2 import (
    ROOT_COLLECTION,
    expand_collection_paths,
    managed_tag,
    unique_preserve_order,
)
from paperflow.utils import dump_json_data, ensure_parent_dir, read_json_model, write_json
from paperflow.zotero_web import ZoteroWebClient


class CollectionMode(StrEnum):
    ADD_ONLY = "add-only"
    REPLACE_ALL = "replace-all"
    REPLACE_NON_PROTECTED = "replace-non-protected"


class TagMode(StrEnum):
    APPEND_NORMALIZED = "append-normalized"
    REPLACE_MANAGED = "replace-managed"
    REPLACE_ALL = "replace-all"


APPLY_CONFIRMATION = "REPLACE MY ZOTERO COLLECTIONS"
TAG_REPLACE_ALL_CONFIRMATION = "REPLACE ALL TAGS"


def chunks(values: list[Any], size: int = 50) -> list[list[Any]]:
    return [values[idx : idx + size] for idx in range(0, len(values), size)]


def extract_item_tags(raw_item: dict[str, Any]) -> list[str]:
    tags = raw_item.get("data", {}).get("tags", [])
    output: list[str] = []
    for tag in tags:
        if isinstance(tag, dict) and tag.get("tag"):
            output.append(str(tag["tag"]))
        elif isinstance(tag, str):
            output.append(tag)
    return output


def extract_item_collections(raw_item: dict[str, Any]) -> list[str]:
    collections = raw_item.get("data", {}).get("collections", [])
    return [str(collection) for collection in collections]


def collection_maps(
    collections: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str], dict[str, dict[str, Any]]]:
    by_key: dict[str, dict[str, Any]] = {}
    for collection in collections:
        data = collection.get("data", {})
        key = collection.get("key") or data.get("key")
        if key:
            by_key[str(key)] = collection

    path_by_key: dict[str, str] = {}

    def build_path(key: str) -> str:
        if key in path_by_key:
            return path_by_key[key]
        data = by_key[key].get("data", {})
        name = data.get("name") or key
        parent = data.get("parentCollection")
        if parent and parent in by_key:
            path = f"{build_path(parent)}/{name}"
        else:
            path = str(name)
        path_by_key[key] = path
        return path

    for key in by_key:
        build_path(key)

    key_by_path = {path: key for key, path in path_by_key.items()}
    return key_by_path, path_by_key, by_key


def collection_path_is_ai_library(path: str | None) -> bool:
    return bool(path and (path == ROOT_COLLECTION or path.startswith(f"{ROOT_COLLECTION}/")))


def creation_plan(
    target_paths: list[str],
    existing_collections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    key_by_path, _, _ = collection_maps(existing_collections)
    desired_paths = expand_collection_paths(target_paths)
    return [
        {
            "path": path,
            "name": path.split("/")[-1],
            "parentPath": "/".join(path.split("/")[:-1]) or None,
            "parentCollection": key_by_path.get("/".join(path.split("/")[:-1]))
            if "/" in path
            else False,
        }
        for path in desired_paths
        if path not in key_by_path
    ]


def placeholder_key(path: str) -> str:
    return f"CREATE:{path}"


def collection_key_for_path(path: str, key_by_path: dict[str, str]) -> str:
    return key_by_path.get(path, placeholder_key(path))


def compute_final_collection_keys(
    existing_collection_keys: list[str],
    planned_collection_paths: list[str],
    key_by_path: dict[str, str],
    mode: CollectionMode,
    protected_collection_keys: set[str] | None = None,
) -> list[str]:
    protected_collection_keys = protected_collection_keys or set()
    planned_keys = [collection_key_for_path(path, key_by_path) for path in planned_collection_paths]
    if mode == CollectionMode.ADD_ONLY:
        return unique_preserve_order([*existing_collection_keys, *planned_keys])
    if mode == CollectionMode.REPLACE_ALL:
        return unique_preserve_order(planned_keys)
    preserved = [key for key in existing_collection_keys if key in protected_collection_keys]
    return unique_preserve_order([*preserved, *planned_keys])


def compute_final_tags(
    existing_tags: list[str],
    normalized_tags: list[str],
    mode: TagMode,
) -> list[str]:
    if mode == TagMode.APPEND_NORMALIZED:
        return unique_preserve_order([*existing_tags, *normalized_tags])
    if mode == TagMode.REPLACE_MANAGED:
        preserved = [tag for tag in existing_tags if not managed_tag(tag)]
        return unique_preserve_order([*preserved, *normalized_tags])
    return unique_preserve_order(normalized_tags)


def removed_tags(existing_tags: list[str], final_tags: list[str]) -> list[str]:
    final = set(final_tags)
    return [tag for tag in existing_tags if tag not in final]


def read_protected_collection_paths(path: Path = Path("config/protected_collections.yaml")) -> set[str]:
    if not path.exists():
        return set()
    protected: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("-").strip().strip("\"'")
        if line and not line.endswith(":"):
            protected.add(line)
    return protected


def protected_keys_from_paths(
    protected_paths: set[str],
    key_by_path: dict[str, str],
) -> set[str]:
    return {key_by_path[path] for path in protected_paths if path in key_by_path}


def raw_items_by_key(raw_items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for item in raw_items:
        data = item.get("data", {})
        key = item.get("key") or data.get("key")
        if key:
            output[str(key)] = item
    return output


def old_collections_that_would_be_empty(
    current_items: list[dict[str, Any]],
    path_by_key: dict[str, str],
    item_updates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for raw_item in current_items:
        item_type = raw_item.get("data", {}).get("itemType")
        if item_type in {"attachment", "note"}:
            continue
        counts.update(extract_item_collections(raw_item))

    for update in item_updates:
        item_key = update["itemKey"]
        raw_item = next(
            (
                item
                for item in current_items
                if (item.get("key") or item.get("data", {}).get("key")) == item_key
            ),
            None,
        )
        if raw_item is None:
            continue
        old_keys = set(extract_item_collections(raw_item))
        new_keys = set(update["finalCollectionKeys"])
        for removed in old_keys - new_keys:
            counts[removed] -= 1
        for added in new_keys - old_keys:
            counts[added] += 1

    empty: list[dict[str, Any]] = []
    for key, count in counts.items():
        path = path_by_key.get(key)
        if count <= 0 and not collection_path_is_ai_library(path):
            empty.append({"collectionKey": key, "path": path, "itemCount": 0})
    return sorted(empty, key=lambda row: row.get("path") or row["collectionKey"])


def build_apply_preview(
    plan: MigrationPlan,
    current_collections: list[dict[str, Any]],
    current_items: list[dict[str, Any]],
    user_id: str,
    collection_mode: CollectionMode = CollectionMode.REPLACE_ALL,
    tag_mode: TagMode = TagMode.REPLACE_MANAGED,
    protected_collection_paths: set[str] | None = None,
    web_base_url: str = "https://api.zotero.org",
) -> ApplyPreview:
    key_by_path, path_by_key, _ = collection_maps(current_collections)
    protected_keys = protected_keys_from_paths(protected_collection_paths or set(), key_by_path)
    create = creation_plan(plan.collection_tree, current_collections)
    current_by_key = raw_items_by_key(current_items)
    item_updates: list[dict[str, Any]] = []
    operations: list[ApplyOperation] = []
    prefix = f"{web_base_url.rstrip('/')}/users/{user_id}"

    for collection in create:
        operations.append(
            ApplyOperation(
                method="POST",
                url=f"{prefix}/collections",
                body={
                    "name": collection["name"],
                    "parentCollection": collection["parentCollection"]
                    if collection["parentCollection"] is not None
                    else placeholder_key(collection["parentPath"] or ROOT_COLLECTION),
                },
                note=f"Create collection {collection['path']}",
            )
        )

    for item in plan.items:
        raw_item = current_by_key.get(item.item_key, {})
        existing_collections = extract_item_collections(raw_item) or item.existing_collection_keys
        existing_tags = extract_item_tags(raw_item) or item.existing_tags
        final_collections = compute_final_collection_keys(
            existing_collections,
            item.target_collections,
            key_by_path,
            collection_mode,
            protected_keys,
        )
        final_tags = compute_final_tags(existing_tags, item.normalized_tags, tag_mode)
        removed_collection_keys = [
            key for key in existing_collections if key not in set(final_collections)
        ]
        tags_removed = removed_tags(existing_tags, final_tags)
        version = raw_item.get("version") or raw_item.get("data", {}).get("version") or item.version
        body = {
            "collections": final_collections,
            "tags": [{"tag": tag} for tag in final_tags],
        }
        update = {
            "itemKey": item.item_key,
            "version": version,
            "title": item.title,
            "targetCollections": item.target_collections,
            "finalCollectionKeys": final_collections,
            "removedCollectionKeys": removed_collection_keys,
            "tagsAdded": [tag for tag in final_tags if tag not in set(existing_tags)],
            "tagsRemoved": tags_removed,
            "body": body,
        }
        item_updates.append(update)
        operations.append(
            ApplyOperation(
                method="PATCH",
                url=f"{prefix}/items/{item.item_key}",
                headers={"If-Unmodified-Since-Version": str(version)} if version else {},
                body=body,
                note=f"Update collections/tags for {item.item_key}",
            )
        )

    return ApplyPreview(
        collection_mode=collection_mode.value,
        tag_mode=tag_mode.value,
        collections_to_create=create,
        item_updates=item_updates,
        old_collections_that_would_be_empty=old_collections_that_would_be_empty(
            current_items,
            path_by_key,
            item_updates,
        ),
        operations=operations,
    )


def write_apply_preview(
    preview: ApplyPreview,
    json_path: Path,
    markdown_path: Path,
) -> None:
    write_json(json_path, preview)
    lines = [
        "# apply preview",
        "",
        f"- Collection mode: {preview.collection_mode}",
        f"- Tag mode: {preview.tag_mode}",
        f"- Collections to create: {len(preview.collections_to_create)}",
        f"- Item updates: {len(preview.item_updates)}",
        f"- Old collections that would become empty: {len(preview.old_collections_that_would_be_empty)}",
        "",
        "## Collections to create",
        "",
    ]
    if preview.collections_to_create:
        lines.extend(f"- {row['path']}" for row in preview.collections_to_create)
    else:
        lines.append("- None")
    lines.extend(["", "## Item PATCH operations", ""])
    for update in preview.item_updates:
        lines.append(
            f"- {update['itemKey']}: remove collections "
            f"{update['removedCollectionKeys']}; add tags {update['tagsAdded']}; "
            f"remove tags {update['tagsRemoved']}"
        )
    if not preview.item_updates:
        lines.append("- None")
    lines.extend(["", "## Old collections that would become empty", ""])
    if preview.old_collections_that_would_be_empty:
        lines.extend(
            f"- {row['collectionKey']} | {row.get('path') or '(unknown path)'}"
            for row in preview.old_collections_that_would_be_empty
        )
    else:
        lines.append("- None")
    ensure_parent_dir(markdown_path)
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_apply_request(
    apply: bool,
    confirm: str | None,
    tag_mode: TagMode,
    confirm_tags: str | None,
    user_id: str | None,
    api_key: str | None,
) -> None:
    if not apply:
        raise ValueError("Refusing to apply: --apply is required.")
    if confirm != APPLY_CONFIRMATION:
        raise ValueError(f'Refusing to apply: --confirm "{APPLY_CONFIRMATION}" is required.')
    if tag_mode == TagMode.REPLACE_ALL and confirm_tags != TAG_REPLACE_ALL_CONFIRMATION:
        raise ValueError(
            f'Refusing to replace all tags: --confirm-tags "{TAG_REPLACE_ALL_CONFIRMATION}" is required.'
        )
    if not user_id or not api_key:
        raise ValueError("Refusing to apply: ZOTERO_USER_ID and ZOTERO_API_KEY must be set.")
    if not user_id.isdigit():
        raise ValueError(
            "Refusing to apply: ZOTERO_USER_ID must be your numeric Zotero user ID, "
            "not an email address or username."
        )


def apply_migration_with_web_api(
    plan_path: Path,
    user_id: str,
    api_key: str,
    collection_mode: CollectionMode,
    tag_mode: TagMode,
    protected_collection_paths: set[str] | None = None,
    web_base_url: str = "https://api.zotero.org",
    backup_root: Path = Path("data/backups"),
) -> tuple[Path, Path]:
    backup_dir = write_backup_snapshot(backup_root=backup_root, web_base_url=web_base_url)
    plan = read_json_model(plan_path, MigrationPlan)
    apply_events: list[dict[str, Any]] = [
        {"event": "backup-created", "backupDir": str(backup_dir)}
    ]

    with ZoteroWebClient(user_id=user_id, api_key=api_key, base_url=web_base_url) as client:
        collections = client.iter_collections()
        current_items = client.iter_items()
        key_by_path, _, _ = collection_maps(collections)

        for collection in creation_plan(plan.collection_tree, collections):
            parent_path = collection["parentPath"]
            parent_key = key_by_path.get(parent_path) if parent_path else False
            response = client.post_collections(
                [{"name": collection["name"], "parentCollection": parent_key}]
            )
            apply_events.append(
                {
                    "event": "collection-created",
                    "path": collection["path"],
                    "statusCode": response.status_code,
                }
            )
            collections = client.iter_collections()
            key_by_path, _, _ = collection_maps(collections)

        preview = build_apply_preview(
            plan,
            collections,
            current_items,
            user_id=user_id,
            collection_mode=collection_mode,
            tag_mode=tag_mode,
            protected_collection_paths=protected_collection_paths,
            web_base_url=web_base_url,
        )

        for batch in chunks(preview.item_updates, 50):
            for update in batch:
                response = client.patch_item(
                    update["itemKey"],
                    update["body"],
                    version=update.get("version"),
                )
                apply_events.append(
                    {
                        "event": "item-updated",
                        "itemKey": update["itemKey"],
                        "statusCode": response.status_code,
                    }
                )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_log = Path(f"data/apply_log_{ts}.json")
    md_log = Path(f"data/apply_log_{ts}.md")
    dump_json_data(json_log, {"events": apply_events})
    md_lines = ["# apply log", "", f"- Backup: {backup_dir}", ""]
    md_lines.extend(f"- {event['event']}: {event}" for event in apply_events)
    ensure_parent_dir(md_log)
    md_log.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return json_log, md_log
