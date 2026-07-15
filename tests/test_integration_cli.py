import json
from pathlib import Path

from typer.testing import CliRunner

from paperflow.cli import app
from paperflow.models import ZoteroItem


runner = CliRunner()


def _json_result(arguments: list[str]) -> tuple[object, object]:
    result = runner.invoke(app, arguments)
    payload = json.loads(result.stdout)
    return result, payload


def test_manifest_declares_real_provider_entrypoints_without_private_values() -> None:
    manifest = json.loads(Path("gnaroshi.app.json").read_text(encoding="utf-8"))
    assert manifest["schemaVersion"] == 1
    assert manifest["id"] == "paperflow"
    assert manifest["bundleId"] == "com.paperflow.app"
    assert manifest["entrypoints"]["app"]["discovery"] == "bundle-id"
    assert manifest["entrypoints"]["cli"]["versionSubcommand"] == ["version", "--json"]
    assert manifest["entrypoints"]["cli"]["statusSubcommand"] == ["status", "--json"]
    assert manifest["entrypoints"]["cli"]["healthSubcommand"] == ["doctor", "--json"]
    assert manifest["entrypoints"]["cli"]["recentActivitySubcommand"] == [
        "recent",
        "--json",
        "--limit",
        "5",
    ]
    assert manifest["health"]["contractVersion"] == 1
    assert manifest["distribution"]["source"]["mode"] == "git-fetch"
    serialized = json.dumps(manifest)
    assert "/Users/" not in serialized
    assert "token" not in serialized.lower()
    assert "secret" not in serialized.lower()


def test_version_and_status_are_single_versioned_json_values() -> None:
    version_result, version = _json_result(["version", "--json"])
    status_result, status = _json_result(["status", "--json"])
    assert version_result.exit_code == 0
    assert status_result.exit_code == 0
    assert version["schemaVersion"] == 1
    assert version["provider"] == {
        "id": "paperflow",
        "version": "0.2.2",
        "contractVersion": 1,
    }
    assert status["capability"] == "status"
    assert status["data"]["safety"]["zoteroSqlite"] == "never-edited"
    assert status["data"]["safety"]["writeBoundary"] == "explicit-apply"
    assert "/Users/" not in status_result.stdout


def test_recent_activity_is_bounded_path_free_and_does_not_modify_artifacts(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    scan = data / "zotero_items.jsonl"
    plan = data / "organize_plan.json"
    scan.write_text("{}\n", encoding="utf-8")
    plan.write_text("{}\n", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in (scan, plan)}

    result, payload = _json_result(
        ["recent", "--json", "--limit", "1", "--data-dir", str(data)]
    )

    assert result.exit_code == 0
    assert payload["capability"] == "recent-activity"
    assert payload["data"]["activityCount"] == 1
    assert len(payload["data"]["activities"]) == 1
    assert str(tmp_path) not in result.stdout
    assert {path.name: path.read_bytes() for path in (scan, plan)} == before


def test_doctor_json_reports_read_only_health_and_nonzero_blocker(monkeypatch) -> None:
    monkeypatch.setattr("paperflow.cli.ZoteroLocalClient.health_check", lambda self: True)
    result, payload = _json_result(["doctor", "--json"])
    assert result.exit_code == 0
    assert payload["capability"] == "health"
    assert payload["status"] == "ok"

    def unavailable(_self):
        raise ValueError("private diagnostic")

    monkeypatch.setattr("paperflow.cli.ZoteroLocalClient.health_check", unavailable)
    blocked, blocked_payload = _json_result(["doctor", "--json"])
    assert blocked.exit_code == 2
    assert blocked_payload["status"] == "blocked"
    assert blocked_payload["errors"][0]["code"] == "zotero-local-api-unavailable"
    assert "private diagnostic" not in blocked.stdout


def test_zotero_scan_json_keeps_human_command_and_local_api_read_only(
    tmp_path: Path, monkeypatch
) -> None:
    item = ZoteroItem(key="ITEM1", item_type="journalArticle", title="Fixture")
    monkeypatch.setattr("paperflow.cli.ZoteroLocalClient.scan_items", lambda self: [item])
    jsonl = tmp_path / "items.jsonl"
    csv = tmp_path / "items.csv"

    result, payload = _json_result(
        [
            "zotero",
            "scan",
            "--jsonl-output",
            str(jsonl),
            "--csv-output",
            str(csv),
            "--json",
        ]
    )
    assert result.exit_code == 0
    assert payload["capability"] == "scan-library"
    assert payload["data"]["itemCount"] == 1
    assert payload["data"]["writesExecuted"] is False
    assert str(tmp_path) not in result.stdout
    assert jsonl.is_file() and csv.is_file()

    human = runner.invoke(
        app,
        ["zotero", "scan", "--jsonl-output", str(jsonl), "--csv-output", str(csv)],
    )
    assert human.exit_code == 0
    assert human.output.startswith("Scanned 1 regular Zotero items")


def test_plan_organization_json_preserves_plan_shape_and_human_output(tmp_path: Path) -> None:
    source = tmp_path / "items.jsonl"
    source.write_text(
        ZoteroItem(
            key="ITEM1",
            item_type="journalArticle",
            title="Retrieval-Augmented Generation",
            abstract_note="Retrieval and generation method.",
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "plan.json"
    result, payload = _json_result(
        ["zotero", "plan-organize", "--input", str(source), "--output", str(output), "--json"]
    )
    assert result.exit_code == 0
    assert payload["capability"] == "plan-organization"
    assert payload["data"]["scannedItems"] == 1
    assert payload["data"]["writesExecuted"] is False
    assert str(tmp_path) not in result.stdout
    assert json.loads(output.read_text(encoding="utf-8"))["stats"]["scanned_items"] == 1

    human = runner.invoke(
        app,
        ["zotero", "plan-organize", "--input", str(source), "--output", str(output)],
    )
    assert human.exit_code == 0
    assert human.output.startswith("Planned 1 items")


def test_json_errors_are_machine_readable_redacted_and_nonzero(tmp_path: Path) -> None:
    missing = tmp_path / "private" / "missing.jsonl"
    result, payload = _json_result(
        ["zotero", "plan-organize", "--input", str(missing), "--json"]
    )
    assert result.exit_code != 0
    assert payload["status"] == "failed"
    assert payload["errors"][0]["code"] == "organization-input-invalid"
    assert str(tmp_path) not in result.stdout
