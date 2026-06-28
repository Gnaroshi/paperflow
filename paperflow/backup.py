from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from paperflow.migration_models import BackupManifest
from paperflow.utils import dump_json_data, ensure_parent_dir
from paperflow.zotero_local import (
    DEFAULT_LIBRARY_PREFIX,
    DEFAULT_LOCAL_API_BASE_URL,
    LocalAPIUnavailable,
    ZoteroLocalClient,
)
from paperflow.zotero_web import ZoteroWebClient


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def collection_memberships_from_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    memberships: list[dict[str, Any]] = []
    for item in items:
        data = item.get("data", {})
        item_key = item.get("key") or data.get("key")
        if not item_key:
            continue
        for collection_key in data.get("collections", []) or []:
            memberships.append(
                {
                    "itemKey": item_key,
                    "itemVersion": item.get("version") or data.get("version"),
                    "itemType": data.get("itemType"),
                    "parentItem": data.get("parentItem"),
                    "collectionKey": collection_key,
                }
            )
    return memberships


def _read_local_snapshot(
    base_url: str,
    library_prefix: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], Literal["local-api"]]:
    with ZoteroLocalClient(base_url=base_url, library_prefix=library_prefix) as client:
        return client.iter_items(), client.iter_collections(), client.iter_tags(), "local-api"


def _read_web_snapshot(
    user_id: str,
    api_key: str,
    base_url: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], Literal["web-api"]]:
    with ZoteroWebClient(user_id=user_id, api_key=api_key, base_url=base_url) as client:
        return client.iter_items(), client.iter_collections(), client.iter_tags(), "web-api"


def read_snapshot(
    local_base_url: str = DEFAULT_LOCAL_API_BASE_URL,
    library_prefix: str = DEFAULT_LIBRARY_PREFIX,
    web_base_url: str = "https://api.zotero.org",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str]:
    try:
        return _read_local_snapshot(local_base_url, library_prefix)
    except Exception as local_error:
        user_id = os.environ.get("ZOTERO_USER_ID")
        api_key = os.environ.get("ZOTERO_API_KEY")
        if not user_id or not api_key:
            raise LocalAPIUnavailable(
                "Zotero Local API is unavailable and Web API fallback requires "
                "ZOTERO_USER_ID and ZOTERO_API_KEY."
            ) from local_error
        return _read_web_snapshot(user_id, api_key, web_base_url)


def write_backup_snapshot(
    backup_root: Path = Path("data/backups"),
    local_base_url: str = DEFAULT_LOCAL_API_BASE_URL,
    library_prefix: str = DEFAULT_LIBRARY_PREFIX,
    web_base_url: str = "https://api.zotero.org",
) -> Path:
    items, collections, tags, source = read_snapshot(
        local_base_url=local_base_url,
        library_prefix=library_prefix,
        web_base_url=web_base_url,
    )
    backup_dir = backup_root / timestamp()
    backup_dir.mkdir(parents=True, exist_ok=False)
    memberships = collection_memberships_from_items(items)
    manifest = BackupManifest(
        generated_at=datetime.now().isoformat(),
        item_count=len(items),
        collection_count=len(collections),
        tag_count=len(tags),
        membership_count=len(memberships),
        source=source,  # type: ignore[arg-type]
    )

    dump_json_data(backup_dir / "items.json", items)
    dump_json_data(backup_dir / "collections.json", collections)
    dump_json_data(backup_dir / "tags.json", tags)
    dump_json_data(backup_dir / "collection_memberships.json", memberships)
    dump_json_data(backup_dir / "manifest.json", manifest.model_dump())

    report = [
        "# Zotero backup report",
        "",
        f"- Generated at: {manifest.generated_at}",
        f"- Source: {source}",
        f"- Items: {len(items)}",
        f"- Collections: {len(collections)}",
        f"- Tags: {len(tags)}",
        f"- Collection memberships: {len(memberships)}",
        "",
        "No Zotero writes were executed.",
    ]
    ensure_parent_dir(backup_dir / "report.md")
    (backup_dir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return backup_dir
