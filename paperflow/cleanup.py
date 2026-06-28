from __future__ import annotations

from collections import Counter
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from paperflow.migration_apply import collection_maps, collection_path_is_ai_library
from paperflow.migration_models import ApplyOperation, CleanupReport
from paperflow.utils import ensure_parent_dir, write_json
from paperflow.zotero_web import ZoteroWebClient


class CleanupMode(StrEnum):
    REPORT_ONLY = "report-only"
    DELETE_EMPTY = "delete-empty"
    ARCHIVE_OLD = "archive-old"


DELETE_EMPTY_CONFIRMATION = "DELETE EMPTY OLD COLLECTIONS"
DELETE_NONEMPTY_CONFIRMATION = "DELETE NONEMPTY COLLECTIONS"


def regular_parent_item_counts_by_collection(items: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in items:
        data = item.get("data", {})
        if data.get("itemType") in {"attachment", "note"}:
            continue
        counts.update(data.get("collections", []) or [])
    return counts


def old_collection_rows(
    collections: list[dict[str, Any]],
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    _, path_by_key, by_key = collection_maps(collections)
    counts = regular_parent_item_counts_by_collection(items)
    rows: list[dict[str, Any]] = []
    for key, collection in by_key.items():
        path = path_by_key.get(key, collection.get("data", {}).get("name"))
        if collection_path_is_ai_library(path):
            continue
        rows.append(
            {
                "collectionKey": key,
                "path": path,
                "name": collection.get("data", {}).get("name"),
                "parentCollection": collection.get("data", {}).get("parentCollection"),
                "version": collection.get("version") or collection.get("data", {}).get("version"),
                "regularParentItemCount": counts.get(key, 0),
            }
        )
    return sorted(rows, key=lambda row: row.get("path") or row["collectionKey"])


def build_cleanup_report(
    collections: list[dict[str, Any]],
    items: list[dict[str, Any]],
    mode: CleanupMode,
    user_id: str = "$ZOTERO_USER_ID",
    force_nonempty: bool = False,
    web_base_url: str = "https://api.zotero.org",
) -> CleanupReport:
    rows = old_collection_rows(collections, items)
    operations: list[ApplyOperation] = []
    prefix = f"{web_base_url.rstrip('/')}/users/{user_id}"
    today = datetime.now().strftime("%Y-%m-%d")
    if mode == CleanupMode.DELETE_EMPTY:
        delete_rows = sorted(
            rows,
            key=lambda row: (str(row.get("path") or "").count("/"), str(row.get("path") or "")),
            reverse=True,
        )
        for row in delete_rows:
            if row["regularParentItemCount"] == 0 or force_nonempty:
                operations.append(
                    ApplyOperation(
                        method="DELETE",
                        url=f"{prefix}/collections/{row['collectionKey']}",
                        headers={"If-Unmodified-Since-Version": str(row["version"])}
                        if row.get("version")
                        else {},
                        note=f"Delete old collection {row.get('path')}",
                    )
                )
    elif mode == CleanupMode.ARCHIVE_OLD:
        for row in rows:
            if row.get("parentCollection"):
                continue
            new_name = f"_OLD_{today}/{row['name']}"
            operations.append(
                ApplyOperation(
                    method="PATCH",
                    url=f"{prefix}/collections/{row['collectionKey']}",
                    headers={"If-Unmodified-Since-Version": str(row["version"])}
                    if row.get("version")
                    else {},
                    body={"name": new_name},
                    note=f"Archive old root collection {row.get('path')}",
                )
            )
    return CleanupReport(mode=mode.value, collections=rows, operations=operations)


def write_cleanup_report(report: CleanupReport, path: Path) -> None:
    write_json(path.with_suffix(".json"), report)
    lines = [
        "# cleanup collections report",
        "",
        f"- Mode: {report.mode}",
        f"- Old collections outside AI Library: {len(report.collections)}",
        f"- Planned operations: {len(report.operations)}",
        "",
    ]
    for row in report.collections:
        lines.append(
            f"- {row['collectionKey']} | {row.get('path')} | "
            f"{row['regularParentItemCount']} regular parent items"
        )
    ensure_parent_dir(path)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_cleanup_request(
    mode: CleanupMode,
    apply: bool,
    confirm: str | None,
    force_nonempty: bool,
) -> None:
    if mode == CleanupMode.REPORT_ONLY:
        return
    if not apply:
        raise ValueError("Refusing cleanup: --apply is required for cleanup writes.")
    expected = DELETE_NONEMPTY_CONFIRMATION if force_nonempty else DELETE_EMPTY_CONFIRMATION
    if confirm != expected:
        raise ValueError(f'Refusing cleanup: --confirm "{expected}" is required.')


def apply_cleanup_report(
    report: CleanupReport,
    user_id: str,
    api_key: str,
    web_base_url: str = "https://api.zotero.org",
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with ZoteroWebClient(user_id=user_id, api_key=api_key, base_url=web_base_url) as client:
        for operation in report.operations:
            collection_key = operation.url.rstrip("/").split("/")[-1]
            version = operation.headers.get("If-Unmodified-Since-Version")
            if operation.method == "DELETE":
                response = client.delete_collection(
                    collection_key,
                    version=int(version) if version else None,
                )
            else:
                response = client.patch_collection(
                    collection_key,
                    operation.body or {},
                    version=int(version) if version else None,
                )
            events.append(
                {
                    "method": operation.method,
                    "collectionKey": collection_key,
                    "statusCode": response.status_code,
                }
            )
    return events
