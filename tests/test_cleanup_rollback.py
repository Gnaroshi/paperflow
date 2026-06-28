import json
from pathlib import Path

from paperflow.cleanup import CleanupMode, build_cleanup_report
from paperflow.rollback import build_rollback_plan


def test_cleanup_collections_refuses_to_delete_non_empty_by_default() -> None:
    collections = [
        {
            "key": "OLD",
            "version": 4,
            "data": {"key": "OLD", "name": "Old Collection", "parentCollection": False},
        }
    ]
    items = [
        {
            "key": "ITEM",
            "data": {
                "key": "ITEM",
                "itemType": "journalArticle",
                "collections": ["OLD"],
            },
        }
    ]

    report = build_cleanup_report(collections, items, CleanupMode.DELETE_EMPTY)

    assert report.collections[0]["regularParentItemCount"] == 1
    assert report.operations == []


def test_rollback_plan_generation(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    collections = [
        {
            "key": "OLD",
            "version": 1,
            "data": {"key": "OLD", "name": "Old Collection", "parentCollection": False},
        }
    ]
    items = [
        {
            "key": "ITEM",
            "version": 9,
            "data": {
                "key": "ITEM",
                "itemType": "journalArticle",
                "collections": ["OLD"],
                "tags": [{"tag": "manual/keep"}],
            },
        }
    ]
    (backup_dir / "collections.json").write_text(json.dumps(collections), encoding="utf-8")
    (backup_dir / "items.json").write_text(json.dumps(items), encoding="utf-8")

    plan = build_rollback_plan(backup_dir, current_collections=[])

    assert plan.recreate_collections[0]["backupCollectionKey"] == "OLD"
    assert plan.item_updates[0]["itemKey"] == "ITEM"
    assert plan.item_updates[0]["collections"] == ["OLD"]
