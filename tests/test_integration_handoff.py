import json
from pathlib import Path

from typer.testing import CliRunner

from paperflow.cli import app
from paperflow.models import ZoteroItem


runner = CliRunner()


def _invoke(arguments: list[str]):
    result = runner.invoke(app, ["import", *arguments, "--dry-run", "--json"])
    return result, json.loads(result.stdout)


def test_selected_pdf_returns_an_accepted_preview_without_writes(
    tmp_path: Path, monkeypatch
) -> None:
    pdf = tmp_path / "2401.00001.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfixture")
    monkeypatch.setattr("paperflow.ingest._first_page_text", lambda _path: "Fixture paper")
    monkeypatch.setattr("paperflow.cli.ZoteroLocalClient.scan_items", lambda _self: [])

    result, payload = _invoke(["--file", str(pdf)])

    assert result.exit_code == 0
    assert payload["data"]["disposition"] == "accepted"
    assert payload["data"]["writesExecuted"] is False
    assert all(not change["executed"] for change in payload["data"]["plannedChanges"])
    assert {change["kind"] for change in payload["data"]["plannedChanges"]} >= {
        "copy-pdf-to-managed-vault",
        "create-linked-local-attachment",
    }
    assert str(tmp_path) not in result.stdout


def test_url_and_arxiv_handoffs_require_review_without_downloading(monkeypatch) -> None:
    monkeypatch.setattr("paperflow.cli.ZoteroLocalClient.scan_items", lambda _self: [])
    url_result, url_payload = _invoke(["--url", "https://example.org/paper"])
    arxiv_result, arxiv_payload = _invoke(["--arxiv", "2401.00001v2"])

    assert url_result.exit_code == 0
    assert arxiv_result.exit_code == 0
    assert url_payload["data"]["disposition"] == "needs-review"
    assert arxiv_payload["data"]["sourceId"] == "arxiv:2401.00001v2"
    assert all(not change["executed"] for change in url_payload["data"]["plannedChanges"])


def test_metadata_candidate_can_report_a_read_only_duplicate(
    tmp_path: Path, monkeypatch
) -> None:
    candidate = tmp_path / "candidate.json"
    candidate.write_text(
        json.dumps(
            {
                "title": "Existing paper",
                "authors": ["Ada Lovelace"],
                "year": 2024,
                "doi": "10.1234/existing",
                "url": "https://example.org/existing",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "paperflow.cli.ZoteroLocalClient.scan_items",
        lambda _self: [
            ZoteroItem(
                key="ITEM123",
                item_type="journalArticle",
                title="Existing paper",
                doi="10.1234/existing",
            )
        ],
    )

    result, payload = _invoke(["--metadata", str(candidate)])

    assert result.exit_code == 0
    assert payload["data"]["disposition"] == "duplicate"
    assert payload["data"]["resultingLocalRecordId"] == "zotero-item:ITEM123"
    assert "Ada Lovelace" not in result.stdout
    assert str(tmp_path) not in result.stdout


def test_handoff_rejects_ambiguous_invalid_and_non_dry_run_inputs(tmp_path: Path) -> None:
    ambiguous = runner.invoke(
        app,
        [
            "import",
            "--file",
            str(tmp_path / "a.pdf"),
            "--url",
            "https://example.org",
            "--dry-run",
            "--json",
        ],
    )
    ambiguous_payload = json.loads(ambiguous.stdout)
    assert ambiguous.exit_code != 0
    assert ambiguous_payload["data"]["disposition"] == "rejected"
    assert ambiguous_payload["errors"][0]["code"] == "exactly-one-source-required"

    no_dry_run = runner.invoke(
        app,
        ["import", "--url", "https://example.org", "--json"],
    )
    no_dry_run_payload = json.loads(no_dry_run.stdout)
    assert no_dry_run.exit_code != 0
    assert no_dry_run_payload["errors"][0]["code"] == "dry-run-required"

    invalid = runner.invoke(
        app,
        ["import", "--arxiv", "not-an-arxiv-id", "--dry-run", "--json"],
    )
    invalid_payload = json.loads(invalid.stdout)
    assert invalid.exit_code != 0
    assert invalid_payload["errors"][0]["code"] == "invalid-handoff-source"
    assert str(tmp_path) not in invalid.stdout


def test_human_handoff_output_remains_available(monkeypatch) -> None:
    monkeypatch.setattr("paperflow.cli.ZoteroLocalClient.scan_items", lambda _self: [])
    result = runner.invoke(
        app,
        ["import", "--url", "https://example.org/paper", "--dry-run"],
    )
    assert result.exit_code == 0
    assert result.output.startswith("PaperFlow handoff preview: needs-review")
    assert "No files copied and no Zotero writes executed" in result.output
