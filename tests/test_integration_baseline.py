import json
import re
from inspect import getsource
from pathlib import Path

from typer.main import get_command

from paperflow.cli import app
from paperflow.zotero_local import ZoteroLocalClient


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads(
    (ROOT / "tests/fixtures/integration/baseline.json").read_text(encoding="utf-8")
)


def _commands(group_name: str | None = None) -> list[str]:
    root = get_command(app)
    group = root if group_name is None else root.commands[group_name]
    return sorted(group.commands)


def _swift_enum_cases(path: Path, enum_name: str) -> list[str]:
    source = path.read_text(encoding="utf-8")
    match = re.search(rf"enum {enum_name}.*?\{{(.*?)\n\}}", source, flags=re.DOTALL)
    assert match, f"Missing Swift enum {enum_name}"
    return re.findall(r"^\s*case\s+(\w+)", match.group(1), flags=re.MULTILINE)


def test_cli_command_inventory_matches_the_recorded_baseline() -> None:
    assert set(FIXTURE["cli"]["rootCommands"]) <= set(_commands())
    assert _commands("zotero") == FIXTURE["cli"]["zoteroCommands"]
    assert _commands("local") == FIXTURE["cli"]["localCommands"]
    assert _commands("vault") == FIXTURE["cli"]["vaultCommands"]
    assert _commands("cleanup") == FIXTURE["cli"]["cleanupCommands"]
    assert _commands("taxonomy") == FIXTURE["cli"]["taxonomyCommands"]


def test_native_navigation_and_confirmation_flows_match_the_baseline() -> None:
    models = ROOT / "PaperFlowApp/Models.swift"
    assert _swift_enum_cases(models, "AppSection") == FIXTURE["nativeApp"]["sections"]
    confirmation_cases = _swift_enum_cases(models, "ConfirmationKind")
    assert confirmation_cases == FIXTURE["nativeApp"]["confirmationCases"]
    info_plist = (ROOT / "PaperFlowApp/Info.plist").read_text(encoding="utf-8")
    assert f"<string>{FIXTURE['nativeApp']['bundleId']}</string>" in info_plist


def test_zotero_local_client_remains_get_only() -> None:
    source = getsource(ZoteroLocalClient)
    assert "self.client.get(" in source
    for method in ("post", "put", "patch", "delete"):
        assert f"self.client.{method}(" not in source


def test_documented_safety_defaults_and_output_formats_remain_visible() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for promise in (
        "never edits `zotero.sqlite`",
        "never renames files",
        "never deletes Zotero items",
        "Local API only for read-only scanning",
        "defaults to dry-run behavior",
        "must require `--apply`",
    ):
        assert promise in readme
    cli_source = (ROOT / "paperflow/cli.py").read_text(encoding="utf-8")
    for paths in FIXTURE["outputFormats"].values():
        if isinstance(paths, list):
            for path in paths:
                assert path in cli_source
