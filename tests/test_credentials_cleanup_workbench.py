import json
from pathlib import Path

import httpx

from paperflow.cleanup_workbench import (
    abstract_text_is_verbatim,
    build_abstract_repair_plan,
    duplicate_resolution_plan,
    explain_item,
    extract_abstract_from_text,
    migration_audit,
    validate_duplicate_delete,
)
from paperflow.credentials import (
    classify_gemini_error,
    parse_gemini_usage,
    parse_zotero_key_response,
    record_gemini_usage,
    redact_secret,
    validate_numeric_user_id,
    verify_zotero_api_key,
    zotero_key_has_write_access,
)
from paperflow.migration_models import (
    DedupePlan,
    DuplicateGroup,
    DuplicateItem,
    EnrichedZoteroItem,
    MigrationItem,
    MigrationPlan,
    MigrationStats,
)
from paperflow.models import ReadingActivity
from paperflow.utils import write_json, write_jsonl


def _migration_plan(items: list[MigrationItem]) -> MigrationPlan:
    return MigrationPlan(
        source_jsonl="items.jsonl",
        tag_vocabulary=["status/to-read", "area/vlm", "type/method"],
        stats=MigrationStats(
            source_items=len(items),
            planned_items=len(items),
            duplicate_candidates=sum(1 for item in items if item.duplicate_role == "duplicate_candidate"),
            missing_metadata=sum("cleanup/missing-metadata" in item.normalized_tags for item in items),
            missing_abstract=sum("cleanup/missing-abstract" in item.normalized_tags for item in items),
            non_paper_items=sum("cleanup/non-paper" in item.normalized_tags for item in items),
        ),
        items=items,
    )


def _migration_item(
    key: str = "ITEM1",
    tags: list[str] | None = None,
    collections: list[str] | None = None,
    confidence: float = 0.9,
) -> MigrationItem:
    return MigrationItem(
        item_key=key,
        item_type="journalArticle",
        title="A Paper",
        target_collections=collections or ["AI Library/40 Cleanup/Missing Abstract"],
        normalized_tags=tags or ["status/to-read", "type/method", "cleanup/missing-abstract"],
        metadata_quality_score=0.7,
        confidence=confidence,
        rationale="test rationale",
    )


def test_zotero_user_id_must_be_numeric() -> None:
    assert validate_numeric_user_id("1234567") == "1234567"
    for value in ("person@example.com", "username"):
        try:
            validate_numeric_user_id(value)
        except ValueError as exc:
            assert "numeric" in str(exc)
        else:
            raise AssertionError("expected numeric validation failure")


def test_zotero_keys_current_response_extracts_access() -> None:
    parsed = parse_zotero_key_response(
        {
            "userID": 1234567,
            "username": "paperuser",
            "access": {
                "user": {
                    "library": True,
                    "write": False,
                    "notes": True,
                    "files": False,
                }
            },
        }
    )

    assert parsed["userID"] == 1234567
    assert parsed["username"] == "paperuser"
    assert parsed["access"]["user"]["library"] is True
    assert zotero_key_has_write_access(parsed) is False


def test_zotero_verify_uses_key_without_printing_it() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Zotero-API-Key"] == "secret-key"
        return httpx.Response(200, json={"userID": 1, "username": "u", "access": {"user": {"write": True}}})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = verify_zotero_api_key("secret-key", client=client)

    assert result["userID"] == 1
    assert redact_secret("secret-key", "zotero") == "zotero_********-key"


def test_gemini_error_classification_and_usage(tmp_path: Path) -> None:
    assert classify_gemini_error(429, {"error": {"status": "RESOURCE_EXHAUSTED"}}).error_type == "rate_limited"
    assert classify_gemini_error(401).error_type == "invalid_key"
    assert classify_gemini_error(503).error_type == "service_error"
    usage = parse_gemini_usage(
        {"usageMetadata": {"promptTokenCount": 2, "candidatesTokenCount": 3, "totalTokenCount": 5}}
    )
    assert usage["totalTokenCount"] == 5

    stored = record_gemini_usage(usage, path=tmp_path / "usage.json")
    assert stored["input_tokens"] == 2
    assert stored["output_tokens"] == 3
    assert stored["total_tokens"] == 5

    limited = record_gemini_usage(error_type="rate_limited", path=tmp_path / "usage.json")
    assert limited["failed_rate_limit_calls"] == 1
    assert limited["last_429_resource_exhausted_time"]


def test_existing_abstract_resolves_missing_abstract(tmp_path: Path) -> None:
    migration_path = tmp_path / "migration.json"
    enriched_path = tmp_path / "items.jsonl"
    write_json(migration_path, _migration_plan([_migration_item()]))
    write_jsonl(
        enriched_path,
        [
            EnrichedZoteroItem(
                key="ITEM1",
                itemType="journalArticle",
                title="A Paper",
                abstractNote="This is already a real abstract.",
                normalized_title="a paper",
                metadata_quality_score=0.7,
            )
        ],
    )

    plan = build_abstract_repair_plan(migration_path, enriched_path)

    assert plan["repairs"][0]["found"] is True
    assert plan["repairs"][0]["evidence_source"] == "zotero"


def test_pdf_abstract_section_is_extracted() -> None:
    text = """
    Title
    ABSTRACT
    This paper presents a robust method for extracting abstracts from papers.
    It includes enough text to pass the conservative length threshold and stops cleanly.
    The method is evaluated on several examples and reports high precision.
    1 Introduction
    This should not be included.
    """

    result = extract_abstract_from_text(text)

    assert result["found"] is True
    assert "This should not be included" not in result["abstract_text"]


def test_pdf_without_abstract_returns_not_found() -> None:
    assert extract_abstract_from_text("Introduction\nNo abstract here.")["found"] is False


def test_gemini_invented_abstract_is_rejected() -> None:
    assert not abstract_text_is_verbatim(
        "Abstract This is the original abstract from the PDF.",
        "This is a generated summary that does not appear in the source.",
    )


def test_duplicate_resolution_shows_canonical_and_duplicate(tmp_path: Path) -> None:
    migration_path = tmp_path / "migration.json"
    dedupe_path = tmp_path / "dedupe.json"
    write_json(
        migration_path,
        _migration_plan(
            [
                _migration_item("CAN", tags=["status/to-read", "type/method", "area/vlm"], collections=["AI Library/20 Areas/Vision-Language Models"]),
                _migration_item(
                    "DUP",
                    tags=["status/to-read", "type/method", "cleanup/duplicate-candidate"],
                    collections=["AI Library/40 Cleanup/Duplicate Candidates"],
                ),
            ]
        ),
    )
    plan = DedupePlan(
        source_jsonl="items.jsonl",
        groups=[
            DuplicateGroup(
                group_id="dup-1",
                match_type="strong_doi",
                normalized_title="a paper",
                canonical_item_key="CAN",
                canonical_reason="reading work",
                metadata_merge_suggested=True,
                suggested_metadata_source_item_key="DUP",
                items=[
                    DuplicateItem(
                        item_key="CAN",
                        metadata_quality_score=70,
                        reading_activity=ReadingActivity(highlight_count=1, has_reading_work=True, score=30),
                        canonical_rank_tuple=[True, 30, True, 70, 5, 1],
                        is_canonical=True,
                        unsafe_to_delete=True,
                    ),
                    DuplicateItem(
                        item_key="DUP",
                        metadata_quality_score=90,
                        reading_activity=ReadingActivity(),
                        canonical_rank_tuple=[False, 0, True, 90, 5, 1],
                    ),
                ],
            )
        ],
    )
    write_json(dedupe_path, plan)

    output = duplicate_resolution_plan(dedupe_path, migration_path)

    assert output["groups"][0]["canonical_item_key"] == "CAN"
    assert output["groups"][0]["items"][1]["item_key"] == "DUP"
    assert output["groups"][0]["metadata_merge_suggested"] is True


def test_delete_duplicate_requires_confirmation_and_no_reading_work() -> None:
    try:
        validate_duplicate_delete(None, {"unsafe_to_delete": False})
    except ValueError as exc:
        assert "DELETE DUPLICATE ITEM" in str(exc)
    else:
        raise AssertionError("expected confirmation failure")

    try:
        validate_duplicate_delete("DELETE DUPLICATE ITEM", {"unsafe_to_delete": True})
    except ValueError as exc:
        assert "reading work" in str(exc)
    else:
        raise AssertionError("expected unsafe failure")


def test_explain_item_and_audit(tmp_path: Path) -> None:
    migration_path = tmp_path / "migration.json"
    preview_path = tmp_path / "preview.json"
    write_json(
        migration_path,
        _migration_plan(
            [
                _migration_item(
                    "ITEM1",
                    tags=["status/to-read", "type/method", "cleanup/missing-abstract"],
                    collections=["AI Library/40 Cleanup/Missing Abstract"],
                )
            ]
        ),
    )
    preview_path.write_text(
        json.dumps(
            {
                "item_updates": [
                    {
                        "itemKey": "ITEM1",
                        "tagsAdded": ["cleanup/missing-abstract"],
                        "tagsRemoved": [],
                    }
                ],
                "old_collections_that_would_be_empty": [],
            }
        ),
        encoding="utf-8",
    )

    explained = explain_item("ITEM1", migration_path, preview_path)
    audit = migration_audit(migration_path, preview_path, apply_log_glob=str(tmp_path / "none_*.json"))

    assert explained["new_collections"] == ["AI Library/40 Cleanup/Missing Abstract"]
    assert explained["apply_status"] == "planned"
    assert "ITEM1" in audit["items_still_in_old_collections"]
    assert audit["failed_item_updates"] == ["ITEM1"]
