from pathlib import Path

from typer.testing import CliRunner

from paperflow.cli import app
from paperflow.migration_models import MigrationPlan, MigrationStats
from paperflow.models import ZoteroItem
from paperflow.planner import build_plan


runner = CliRunner()


def _write_sample_plan(path: Path) -> Path:
    item = ZoteroItem(
        key="SAFE123",
        item_type="journalArticle",
        title="Retrieval-Augmented Generation for Language Models",
        abstract_note="A RAG method for language model question answering.",
        url="https://arxiv.org/abs/2401.00001",
    )
    plan = build_plan([item], source_jsonl="data/zotero_items.jsonl")
    path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    return path


def _write_sample_migration_plan(path: Path) -> Path:
    plan = MigrationPlan(
        source_jsonl="data/zotero_items_enriched.jsonl",
        tag_vocabulary=["status/to-read", "area/rag", "type/method"],
        stats=MigrationStats(
            source_items=1,
            planned_items=1,
            duplicate_candidates=0,
            missing_metadata=0,
            missing_abstract=0,
            non_paper_items=0,
        ),
        items=[
            {
                "item_key": "SAFE123",
                "version": 1,
                "title": "Retrieval-Augmented Generation for Language Models",
                "item_type": "journalArticle",
                "abstract_present": True,
                "target_collections": ["AI Library/20 Areas/RAG"],
                "normalized_tags": ["status/to-read", "area/rag", "type/method"],
                "metadata_quality_score": 0.8,
                "confidence": 0.9,
                "rationale": "Explicit retrieval-augmented generation.",
            }
        ],
    )
    path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_apply_plan_refuses_without_apply(tmp_path: Path) -> None:
    plan_path = _write_sample_plan(tmp_path / "organize_plan.json")

    result = runner.invoke(
        app,
        ["zotero", "apply-plan", "--input", str(plan_path), "--mode", "add-only"],
    )

    assert result.exit_code != 0
    assert "Dry-run only" in result.output
    assert "Planned Zotero Web API calls" in result.output


def test_apply_plan_refuses_without_api_credentials(
    tmp_path: Path, monkeypatch
) -> None:
    plan_path = _write_sample_plan(tmp_path / "organize_plan.json")
    monkeypatch.delenv("ZOTERO_USER_ID", raising=False)
    monkeypatch.delenv("ZOTERO_API_KEY", raising=False)

    result = runner.invoke(
        app,
        [
            "zotero",
            "apply-plan",
            "--input",
            str(plan_path),
            "--mode",
            "add-only",
            "--apply",
        ],
    )

    assert result.exit_code != 0
    assert "ZOTERO_USER_ID and ZOTERO_API_KEY" in result.output


def test_apply_migration_refuses_key_without_write_access(
    tmp_path: Path, monkeypatch
) -> None:
    plan_path = _write_sample_migration_plan(tmp_path / "migration_plan.json")
    monkeypatch.setenv("ZOTERO_USER_ID", "1234567")
    monkeypatch.setenv("ZOTERO_API_KEY", "zotero-secret")
    monkeypatch.setattr(
        "paperflow.cli.verify_zotero_api_key",
        lambda api_key: {"ok": True, "access": {"user": {"write": False}}},
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("apply_migration_with_web_api should not be called")

    monkeypatch.setattr("paperflow.cli.apply_migration_with_web_api", fail_if_called)

    result = runner.invoke(
        app,
        [
            "zotero",
            "apply-migration",
            "--input",
            str(plan_path),
            "--collection-mode",
            "replace-all",
            "--tag-mode",
            "replace-managed",
            "--apply",
            "--confirm",
            "REPLACE MY ZOTERO COLLECTIONS",
        ],
    )

    assert result.exit_code != 0
    assert "lacks write access" in result.output
