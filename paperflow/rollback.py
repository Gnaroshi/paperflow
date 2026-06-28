from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperflow.migration_apply import collection_maps
from paperflow.migration_models import RollbackPlan
from paperflow.utils import ensure_parent_dir, write_json
from paperflow.zotero_web import ZoteroWebClient


ROLLBACK_CONFIRMATION = "ROLLBACK ZOTERO MIGRATION"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_rollback_plan(
    backup_dir: Path,
    current_collections: list[dict[str, Any]] | None = None,
    remove_new_collections: bool = False,
) -> RollbackPlan:
    backup_collections = _load_json(backup_dir / "collections.json")
    backup_items = _load_json(backup_dir / "items.json")
    if current_collections is None:
        current_collections = backup_collections
    current_key_by_path, _, _ = collection_maps(current_collections)
    backup_key_by_path, _, _ = collection_maps(backup_collections)

    recreate = []
    for path, key in backup_key_by_path.items():
        if path not in current_key_by_path:
            collection = next(
                row for row in backup_collections if (row.get("key") or row.get("data", {}).get("key")) == key
            )
            data = collection.get("data", {})
            recreate.append(
                {
                    "backupCollectionKey": key,
                    "path": path,
                    "name": data.get("name"),
                    "parentCollection": data.get("parentCollection"),
                }
            )

    item_updates = []
    for item in backup_items:
        data = item.get("data", {})
        item_key = item.get("key") or data.get("key")
        if not item_key or data.get("itemType") in {"attachment", "note"}:
            continue
        item_updates.append(
            {
                "itemKey": item_key,
                "version": item.get("version") or data.get("version"),
                "collections": data.get("collections", []) or [],
                "tags": data.get("tags", []) or [],
            }
        )
    return RollbackPlan(
        backup_dir=str(backup_dir),
        recreate_collections=recreate,
        item_updates=item_updates,
        remove_new_collections=remove_new_collections,
    )


def write_rollback_plan(plan: RollbackPlan, path: Path) -> None:
    write_json(path.with_suffix(".json"), plan)
    lines = [
        "# rollback plan",
        "",
        f"- Backup: {plan.backup_dir}",
        f"- Collections to recreate: {len(plan.recreate_collections)}",
        f"- Item tag/collection updates: {len(plan.item_updates)}",
        f"- Remove new AI Library collections: {plan.remove_new_collections}",
    ]
    ensure_parent_dir(path)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_rollback_request(apply: bool, confirm: str | None, backup_dir: Path) -> None:
    if not backup_dir.exists():
        raise ValueError(f"Backup directory does not exist: {backup_dir}")
    if not apply:
        raise ValueError("Refusing rollback: --apply is required.")
    if confirm != ROLLBACK_CONFIRMATION:
        raise ValueError(f'Refusing rollback: --confirm "{ROLLBACK_CONFIRMATION}" is required.')


def apply_rollback_plan(
    plan: RollbackPlan,
    user_id: str,
    api_key: str,
    web_base_url: str = "https://api.zotero.org",
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with ZoteroWebClient(user_id=user_id, api_key=api_key, base_url=web_base_url) as client:
        for update in plan.item_updates:
            body = {
                "collections": update["collections"],
                "tags": update["tags"],
            }
            response = client.patch_item(
                update["itemKey"],
                body,
                version=update.get("version"),
            )
            events.append(
                {
                    "event": "item-restored",
                    "itemKey": update["itemKey"],
                    "statusCode": response.status_code,
                }
            )
    return events
