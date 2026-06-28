from pathlib import Path

from paperflow.migration_apply import (
    APPLY_CONFIRMATION,
    CollectionMode,
    TagMode,
    apply_migration_with_web_api,
    compute_final_collection_keys,
    compute_final_tags,
    validate_apply_request,
)
from paperflow.migration_models import MigrationPlan, MigrationStats
from paperflow.utils import write_json


def test_apply_refuses_without_apply() -> None:
    try:
        validate_apply_request(
            apply=False,
            confirm=APPLY_CONFIRMATION,
            tag_mode=TagMode.REPLACE_MANAGED,
            confirm_tags=None,
            user_id="1",
            api_key="key",
        )
    except ValueError as exc:
        assert "--apply is required" in str(exc)
    else:
        raise AssertionError("expected refusal")


def test_apply_refuses_without_confirmation_string() -> None:
    try:
        validate_apply_request(
            apply=True,
            confirm="wrong",
            tag_mode=TagMode.REPLACE_MANAGED,
            confirm_tags=None,
            user_id="1",
            api_key="key",
        )
    except ValueError as exc:
        assert "REPLACE MY ZOTERO COLLECTIONS" in str(exc)
    else:
        raise AssertionError("expected refusal")


def test_apply_refuses_non_numeric_user_id() -> None:
    try:
        validate_apply_request(
            apply=True,
            confirm=APPLY_CONFIRMATION,
            tag_mode=TagMode.REPLACE_MANAGED,
            confirm_tags=None,
            user_id="person@example.com",
            api_key="key",
        )
    except ValueError as exc:
        assert "numeric Zotero user ID" in str(exc)
    else:
        raise AssertionError("expected refusal")


def test_replace_all_computes_complete_collection_list() -> None:
    final = compute_final_collection_keys(
        existing_collection_keys=["OLD"],
        planned_collection_paths=["AI Library/20 Areas/RAG"],
        key_by_path={"AI Library/20 Areas/RAG": "RAGKEY"},
        mode=CollectionMode.REPLACE_ALL,
    )

    assert final == ["RAGKEY"]


def test_tag_mode_replace_managed_preserves_non_managed_manual_tags() -> None:
    final = compute_final_tags(
        existing_tags=["manual/keep", "status/read", "area/rag"],
        normalized_tags=["status/to-read", "area/vlm", "type/method"],
        mode=TagMode.REPLACE_MANAGED,
    )

    assert "manual/keep" in final
    assert "status/read" not in final
    assert "area/rag" not in final
    assert "status/to-read" in final


class _Response:
    status_code = 200


class _FakeClient:
    events: list[str] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *args) -> None:
        pass

    def iter_collections(self) -> list[dict]:
        return [
            {
                "key": "AIROOT",
                "version": 1,
                "data": {"key": "AIROOT", "name": "AI Library", "parentCollection": False},
            },
            {
                "key": "RAGKEY",
                "version": 1,
                "data": {
                    "key": "RAGKEY",
                    "name": "RAG",
                    "parentCollection": "AIROOT",
                },
            },
        ]

    def iter_items(self) -> list[dict]:
        return [
            {
                "key": "ITEM1",
                "version": 3,
                "data": {
                    "key": "ITEM1",
                    "itemType": "journalArticle",
                    "collections": ["OLD"],
                    "tags": [{"tag": "manual/keep"}],
                },
            }
        ]

    def post_collections(self, payload: list[dict]) -> _Response:
        self.events.append("create")
        return _Response()

    def patch_item(self, item_key: str, body: dict, version: int | None = None) -> _Response:
        self.events.append("patch")
        return _Response()


def test_backup_is_written_before_apply(tmp_path: Path, monkeypatch) -> None:
    plan = MigrationPlan(
        source_jsonl="test.jsonl",
        tag_vocabulary=["status/to-read", "area/rag", "type/method"],
        stats=MigrationStats(
            source_items=0,
            planned_items=0,
            duplicate_candidates=0,
            missing_metadata=0,
            missing_abstract=0,
            non_paper_items=0,
        ),
        items=[],
    )
    plan_path = tmp_path / "migration_plan.json"
    write_json(plan_path, plan)
    events: list[str] = []

    def fake_backup(*args, **kwargs):
        events.append("backup")
        return tmp_path / "backup"

    monkeypatch.setattr("paperflow.migration_apply.write_backup_snapshot", fake_backup)
    monkeypatch.setattr("paperflow.migration_apply.ZoteroWebClient", _FakeClient)
    apply_migration_with_web_api(
        plan_path,
        user_id="1",
        api_key="key",
        collection_mode=CollectionMode.REPLACE_ALL,
        tag_mode=TagMode.REPLACE_MANAGED,
        backup_root=tmp_path / "backups",
    )

    assert events == ["backup"]
