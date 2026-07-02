import json
import time
from pathlib import Path

import httpx
from typer.testing import CliRunner

from paperflow.cli import app
from paperflow.ingest import ProgressEmitter, build_ingest_plan


LOOPED_WORLD_MODELS_FIRST_PAGE = """
Published by FaceMind Research Asia
LOOPEDWORLDMODELS
FaceMind Research Asia
Leading Contributors
ABSTRACT
Current world models face a critical limitation: fixed computational depth.
This paper introduces looped world models, a recurrent-depth transformer
architecture that enables adaptive computation for control and planning.
The model improves efficient compute while preserving temporal dynamics.
1 Introduction
arXiv:2606.18208v1  [cs.LG]  16 Jun 2026
"""


def _fake_pdf(tmp_path: Path, name: str = "2606.18208v1.pdf") -> Path:
    path = tmp_path / name
    path.write_bytes(b"%PDF-1.4\n% fake pdf content for metadata dry-run tests\n")
    return path


def test_ingest_progress_jsonl_is_valid_json(tmp_path: Path, monkeypatch) -> None:
    pdf = _fake_pdf(tmp_path)
    monkeypatch.setattr("paperflow.ingest._first_page_text", lambda path: LOOPED_WORLD_MODELS_FIRST_PAGE)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "ingest",
            str(pdf),
            "--dry-run",
            "--storage-mode",
            "linked-local",
            "--progress-jsonl",
            "--verbose",
            "--offline-fast",
            "--json-output",
            str(tmp_path / "ingest_plan.json"),
            "--report",
            str(tmp_path / "ingest_report.md"),
        ],
    )

    assert result.exit_code == 0, result.output
    events = [json.loads(line) for line in result.output.splitlines() if line.strip()]
    assert events
    assert {event["event"] for event in events} >= {"stage_started", "stage_finished", "done"}
    assert all("elapsed_ms" in event for event in events)
    assert any(event["stage"] == "extract_first_page_text" for event in events)


def test_default_dry_run_uses_no_gemini_and_no_zotero_write(tmp_path: Path, monkeypatch) -> None:
    pdf = _fake_pdf(tmp_path)
    monkeypatch.setattr("paperflow.ingest._first_page_text", lambda path: LOOPED_WORLD_MODELS_FIRST_PAGE)

    plan = build_ingest_plan(
        [pdf],
        vault_library=tmp_path / "Library",
        network_enabled=False,
        cache_dir=tmp_path / "cache",
    )

    item = plan["items"][0]
    assert item["gemini_enabled"] is False
    assert item["zotero_write_enabled"] is False


def test_network_timeout_error_continues_without_hanging(tmp_path: Path, monkeypatch) -> None:
    pdf = _fake_pdf(tmp_path)
    monkeypatch.setattr("paperflow.ingest._first_page_text", lambda path: LOOPED_WORLD_MODELS_FIRST_PAGE)

    def timeout_arxiv(*args, **kwargs):
        raise httpx.TimeoutException("arXiv timed out")

    monkeypatch.setattr("paperflow.ingest.fetch_arxiv_metadata", timeout_arxiv)

    started = time.monotonic()
    plan = build_ingest_plan(
        [pdf],
        vault_library=tmp_path / "Library",
        network_enabled=True,
        network_timeout_seconds=0.01,
        cache_dir=tmp_path / "cache",
    )

    assert time.monotonic() - started < 2
    assert plan["items"][0]["title"] == "Looped World Models"


def test_looped_world_models_single_pdf_expected_dry_run(tmp_path: Path, monkeypatch) -> None:
    pdf = _fake_pdf(tmp_path)
    events: list[dict] = []
    monkeypatch.setattr("paperflow.ingest._first_page_text", lambda path: LOOPED_WORLD_MODELS_FIRST_PAGE)

    plan = build_ingest_plan(
        [pdf],
        vault_library=tmp_path / "Library",
        progress=ProgressEmitter(enabled=True, writer=events.append),
        network_enabled=False,
        cache_dir=tmp_path / "cache",
    )

    item = plan["items"][0]
    assert plan["schema_version"] == "1.0"
    assert plan["mode"] == "dry-run"
    assert plan["storage_mode"] == "linked-local"
    assert plan["upload_to_zotero_storage"] is False
    assert item["source_file"] == str(pdf)
    assert item["file_exists"] is True
    assert item["file_size_bytes"] == pdf.stat().st_size
    assert item["arxiv_id"] == "2606.18208v1"
    assert item["title"] == "Looped World Models"
    assert item["authors"] == []
    assert item["year"] == 2026
    assert item["abstract_found"] is True
    assert item["abstract_present"] is True
    assert item["abstract_source"] == "pdf_first_page"
    assert item["metadata_source"] == "filename+pdf_first_page"
    assert Path(item["target_path"]).name == "2026 - Looped World Models [arXiv 2606.18208v1].pdf"
    assert item["planned_filename"] == "2026 - Looped World Models [arXiv 2606.18208v1].pdf"
    assert Path(item["planned_vault_path"]).name == "2026 - Looped World Models [arXiv 2606.18208v1].pdf"
    assert item["zotero_write_enabled"] is False
    assert item["storage_mode"] == "linked-local"
    assert item["upload_to_zotero_storage"] is False
    assert item["zotero"]["operation"] == "create"
    assert item["zotero"]["item_key"] is None
    assert "AI Library/20 Areas/World Models & Simulation/Latent World Models" in item["target_collections"]
    assert "AI Library/20 Areas/World Models & Simulation/Latent World Models" in item["planned_collections"]
    assert "AI Library/20 Areas/Recurrent & Adaptive Computation/Looped Transformers" in item["target_collections"]
    assert "AI Library/20 Areas/Efficient ML Systems/Parameter Sharing" in item["target_collections"]
    assert "status/to-read" in item["normalized_tags"]
    assert "method/world-model" in item["normalized_tags"]
    assert "method/transformer" in item["normalized_tags"]
    assert "method/looped-transformer" in item["normalized_tags"]
    assert "method/parameter-sharing" in item["normalized_tags"]
    assert "source/arxiv" in item["normalized_tags"]
    assert "method/looped-transformer" in item["planned_tags"]
    assert "source/arxiv" in item["planned_tags"]
    assert item["classification"]["confidence"] > 0
    assert "world model" in item["classification"]["rationale"]
    assert item["actions"] == [
        {"name": "copy_to_vault", "executed": False},
        {"name": "create_or_update_zotero_item", "executed": False},
        {"name": "create_linked_attachment", "executed": False},
        {"name": "add_to_collections", "executed": False},
        {"name": "add_tags", "executed": False},
    ]
    assert any(event["event"] == "stage_started" for event in events)


def test_explain_ingest_command_reads_structured_json(tmp_path: Path, monkeypatch) -> None:
    pdf = _fake_pdf(tmp_path)
    monkeypatch.setattr("paperflow.ingest._first_page_text", lambda path: LOOPED_WORLD_MODELS_FIRST_PAGE)
    plan = build_ingest_plan(
        [pdf],
        vault_library=tmp_path / "Library",
        network_enabled=False,
        cache_dir=tmp_path / "cache",
    )
    plan_path = tmp_path / "ingest_plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["zotero", "explain-ingest", str(plan_path)])

    assert result.exit_code == 0, result.output
    assert "Source:" in result.output
    assert "Planned vault path:" in result.output
    assert "World Models & Simulation" in result.output
    assert "Latent World Models" in result.output
    assert "status/to-read" in result.output
    assert "Zotero write executed: false" in result.output
