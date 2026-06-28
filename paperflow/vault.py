from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperflow.migration_models import MigrationItem, MigrationPlan
from paperflow.utils import dump_json_data, ensure_parent_dir, read_json_model


DEFAULT_VAULT_ROOT = Path("~/Papers/Paperflow").expanduser()
DEFAULT_VAULT_LIBRARY = DEFAULT_VAULT_ROOT / "Library"
DEFAULT_VAULT_INBOX = DEFAULT_VAULT_ROOT / "Inbox"
DEFAULT_VAULT_LOGS = DEFAULT_VAULT_ROOT / "Logs"
DEFAULT_VAULT_BACKUPS = DEFAULT_VAULT_ROOT / "Backups"

ZOTERO_BASE_DIR_INSTRUCTION = (
    "Zotero -> Settings -> Advanced -> Files and Folders -> "
    "Linked Attachment Base Directory\n"
    f"Set it to:\n{DEFAULT_VAULT_LIBRARY}"
)


INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WHITESPACE_RE = re.compile(r"\s+")


def vault_dirs(vault_root: Path = DEFAULT_VAULT_ROOT) -> list[Path]:
    root = vault_root.expanduser()
    return [
        root / "Library",
        root / "Inbox",
        root / "Logs",
        root / "Backups",
    ]


def init_vault(vault_root: Path = DEFAULT_VAULT_ROOT) -> list[Path]:
    paths = vault_dirs(vault_root)
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
    return paths


def sanitize_filename_component(value: str | None, fallback: str = "untitled") -> str:
    text = (value or "").strip() or fallback
    text = INVALID_FILENAME_CHARS_RE.sub(" ", text)
    text = text.replace("\n", " ").replace("\r", " ")
    text = WHITESPACE_RE.sub(" ", text).strip(" .")
    if not text:
        text = fallback
    return text[:160].strip(" .") or fallback


def sanitize_identifier(value: str | None, fallback: str) -> str:
    text = sanitize_filename_component(value, fallback=fallback)
    text = text.replace("/", "_")
    return text[:80].strip(" .") or fallback


def year_label(year: int | None) -> str:
    return str(year) if year else "unknown-year"


def identifier_for_item(item: MigrationItem | Any) -> str:
    return (
        getattr(item, "arxiv_id", None)
        or getattr(item, "doi_normalized", None)
        or getattr(item, "doi", None)
        or getattr(item, "item_key", None)
        or getattr(item, "key", None)
        or "unknown"
    )


def safe_pdf_filename(
    year: int | None,
    title: str | None,
    identifier: str,
) -> str:
    year_part = year_label(year)
    title_part = sanitize_filename_component(title)
    identifier_part = sanitize_identifier(identifier, fallback="unknown")
    filename = f"{year_part} - {title_part} [{identifier_part}].pdf"
    if len(filename) <= 240:
        return filename
    overflow = len(filename) - 240
    title_part = title_part[: max(20, len(title_part) - overflow)].strip(" .")
    return f"{year_part} - {title_part} [{identifier_part}].pdf"


def target_path_for_item(
    item: MigrationItem | Any,
    vault_library: Path = DEFAULT_VAULT_LIBRARY,
) -> Path:
    identifier = identifier_for_item(item)
    filename = safe_pdf_filename(
        getattr(item, "year", None),
        getattr(item, "title", None),
        identifier,
    )
    return vault_library.expanduser() / year_label(getattr(item, "year", None)) / filename


def zotero_linked_attachment_path(
    file_path: Path,
    vault_library: Path = DEFAULT_VAULT_LIBRARY,
) -> str:
    expanded_file = file_path.expanduser().resolve(strict=False)
    expanded_library = vault_library.expanduser().resolve(strict=False)
    try:
        relative = expanded_file.relative_to(expanded_library)
    except ValueError:
        return str(expanded_file)
    return "attachments:" + relative.as_posix()


def dedupe_target_path(path: Path, seen: set[Path], suffix: str) -> Path:
    candidate = path
    if candidate not in seen:
        seen.add(candidate)
        return candidate
    stem = path.stem
    parent = path.parent
    safe_suffix = sanitize_identifier(suffix, fallback="copy")
    index = 2
    while True:
        candidate = parent / f"{stem} - {safe_suffix}-{index}.pdf"
        if candidate not in seen:
            seen.add(candidate)
            return candidate
        index += 1


def build_vault_path_plan(
    migration_plan: MigrationPlan,
    vault_library: Path = DEFAULT_VAULT_LIBRARY,
) -> dict[str, Any]:
    seen: set[Path] = set()
    items: list[dict[str, Any]] = []
    for item in migration_plan.items:
        target = dedupe_target_path(
            target_path_for_item(item, vault_library),
            seen,
            item.item_key,
        )
        items.append(
            {
                "item_key": item.item_key,
                "title": item.title,
                "year": item.year,
                "identifier": identifier_for_item(item),
                "target_path": str(target),
                "target_directory": str(target.parent),
                "filename": target.name,
            }
        )
    return {
        "schema_version": "1.0",
        "source_plan": migration_plan.source_jsonl,
        "vault_library": str(vault_library.expanduser()),
        "items": items,
    }


def write_vault_path_report(plan: dict[str, Any], path: Path) -> None:
    ensure_parent_dir(path)
    lines = [
        "# vault path report",
        "",
        f"- Vault library: {plan['vault_library']}",
        f"- Planned item paths: {len(plan['items'])}",
        "",
        "## Zotero linked attachment base directory",
        "",
        "Set Zotero's Linked Attachment Base Directory to:",
        "",
        f"`{plan['vault_library']}`",
        "",
        "## Planned paths",
        "",
    ]
    for item in plan["items"]:
        lines.append(
            f"- {item['item_key']} | {item.get('title') or '(untitled)'} -> "
            f"`{item['target_path']}`"
        )
    if not plan["items"]:
        lines.append("- None")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def plan_vault_paths_file(
    input_path: Path,
    output_path: Path,
    report_path: Path,
    vault_library: Path = DEFAULT_VAULT_LIBRARY,
) -> dict[str, Any]:
    migration_plan = read_json_model(input_path, MigrationPlan)
    plan = build_vault_path_plan(migration_plan, vault_library=vault_library)
    dump_json_data(output_path, plan)
    write_vault_path_report(plan, report_path)
    return plan
