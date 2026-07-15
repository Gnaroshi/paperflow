from pathlib import Path

from paperflow.attachment_localize import (
    CLEANUP_STORED_CONFIRMATION,
    build_cleanup_stored_report,
    validate_cleanup_stored_request,
)
from paperflow.ingest import StorageMode, linked_attachment_body, validate_ingest_request
from paperflow.migration_models import MigrationItem, MigrationPlan, MigrationStats
from paperflow.vault import build_vault_path_plan, safe_pdf_filename


def test_vault_filename_sanitizes_invalid_characters() -> None:
    filename = safe_pdf_filename(
        2024,
        'A/B:C*D?"Paper"',
        "10.48550/arXiv.2505.07817",
    )

    assert filename == "2024 - A B C D Paper [10.48550 arXiv.2505.07817].pdf"
    assert "/" not in filename
    assert ":" not in filename


def test_vault_path_plan_uses_identifier_and_year(tmp_path: Path) -> None:
    plan = MigrationPlan(
        source_jsonl="data/zotero_items_enriched.jsonl",
        tag_vocabulary=["status/to-read", "area/vlm", "type/method"],
        stats=MigrationStats(
            source_items=1,
            planned_items=1,
            duplicate_candidates=0,
            missing_metadata=0,
            missing_abstract=0,
            non_paper_items=0,
        ),
        items=[
            MigrationItem(
                item_key="ITEM1",
                item_type="journalArticle",
                title="Vision Language Paper",
                year=2025,
                doi_normalized="10.1234/example",
                target_collections=["AI Library/20 Areas/Vision-Language Models"],
                normalized_tags=["status/to-read", "area/vlm", "type/method"],
                metadata_quality_score=0.8,
                confidence=0.8,
                rationale="test",
            )
        ],
    )

    output = build_vault_path_plan(plan, vault_library=tmp_path / "Library")

    assert output["items"][0]["target_directory"].endswith("/2025")
    assert "Vision Language Paper" in output["items"][0]["filename"]
    assert "10.1234 example" in output["items"][0]["filename"]


def test_ingest_apply_requires_credentials() -> None:
    try:
        validate_ingest_request(
            pdf_paths=[Path("paper.pdf")],
            storage_mode=StorageMode.LINKED_LOCAL,
            apply=True,
            dry_run=False,
            user_id=None,
            api_key=None,
        )
    except ValueError as exc:
        assert "ZOTERO_USER_ID" in str(exc)
    else:
        raise AssertionError("expected refusal")


def test_linked_attachment_body_does_not_upload_file() -> None:
    body = linked_attachment_body("PARENT", Path("/vault/2025/paper.pdf"), "Paper")

    assert body["linkMode"] == "linked_file"
    assert body["path"] == "/vault/2025/paper.pdf"
    assert "filename" not in body
    assert "file" not in body


def test_linked_attachment_body_uses_absolute_path_without_hidden_zotero_setting(tmp_path: Path) -> None:
    vault = tmp_path / "Library"
    pdf = vault / "2025" / "paper.pdf"

    body = linked_attachment_body("PARENT", pdf, "Paper", vault_library=vault)

    assert body["path"] == str(pdf.resolve())


def test_cleanup_stored_attachments_refuses_missing_verify_on_apply(tmp_path: Path) -> None:
    try:
        validate_cleanup_stored_request(
            apply=True,
            confirm=CLEANUP_STORED_CONFIRMATION,
            verify_path=tmp_path / "missing.json",
            user_id="123",
            api_key="key",
        )
    except ValueError as exc:
        assert "verify report is missing" in str(exc)
    else:
        raise AssertionError("expected refusal")


def test_cleanup_stored_attachments_blocks_unsafe_attachment() -> None:
    plan = {
        "items": [
            {
                "attachment_key": "ATT1",
                "attachment_version": 7,
                "parent_item_key": "ITEM1",
                "target_path": "/vault/paper.pdf",
                "unsafe_to_delete": True,
                "unsafe_reasons": ["old-stored-attachment-has-reading-work"],
            }
        ]
    }
    verify = {
        "items": [
            {
                "attachment_key": "ATT1",
                "linked_file_exists": True,
                "checksum_ok": True,
                "old_stored_file_exists": True,
                "parent_has_linked_pdf": True,
            }
        ]
    }

    report = build_cleanup_stored_report(plan, verify)

    assert not report["items"][0]["can_delete_old_stored_attachment"]
    assert "old-stored-attachment-has-reading-work" in report["items"][0]["blockers"]
