from __future__ import annotations

import json
import os
import time
from enum import StrEnum
from pathlib import Path

import httpx
import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from paperflow.backup import write_backup_snapshot
from paperflow.cleanup import (
    CleanupMode,
    apply_cleanup_report,
    build_cleanup_report,
    validate_cleanup_request,
    write_cleanup_report,
)
from paperflow.cleanup_workbench import (
    ABSTRACT_CONFIRMATION,
    METADATA_CONFIRMATION,
    apply_abstract_repairs,
    apply_metadata_repairs,
    build_abstract_repair_plan,
    build_metadata_repair_plan,
    duplicate_resolution_plan,
    explain_item as explain_item_data,
    migration_audit as build_migration_audit,
    validate_abstract_apply,
    validate_metadata_apply,
    write_abstract_repair_report,
    write_duplicate_resolution_report,
    write_metadata_repair_report,
    write_migration_audit_report,
)
from paperflow.credentials import (
    DEFAULT_GEMINI_MODEL,
    verify_gemini_api_key,
    verify_zotero_api_key,
    zotero_key_has_write_access,
)
from paperflow.attachment_localize import (
    BRIDGE_NOTE,
    CLEANUP_STORED_CONFIRMATION,
    LOCALIZE_CONFIRMATION,
    apply_localize_attachments_plan,
    cleanup_stored_attachments_file,
    plan_localize_attachments_file,
    validate_cleanup_stored_request,
    validate_localize_apply,
    verify_localized_attachments_file,
    write_apply_log,
)
from paperflow.dedupe import detect_duplicates_file
from paperflow.ingest import (
    ProgressEmitter,
    StorageMode,
    apply_ingest_plan,
    build_ingest_apply_log,
    build_ingest_debug_trace,
    build_ingest_plan,
    explain_ingest_plan,
    timestamped_ingest_apply_log_path,
    validate_ingest_request,
    write_ingest_report,
)
from paperflow.local_import import (
    LOCAL_IMPORT_CONFIRMATION,
    SOURCE_QUARANTINE_CONFIRMATION,
    apply_local_import_plan,
    audit_local_import,
    build_zotero_index,
    cleanup_source_files,
    classify_new_local_papers,
    local_scan,
    match_local_to_zotero,
    plan_local_import,
    validate_local_apply,
    validate_source_cleanup,
    write_classification_report,
    write_import_plan_report,
    write_local_apply_markdown,
    write_local_audit_report,
    write_local_scan_report,
    write_match_report,
    write_source_cleanup_report,
    write_zotero_index_report,
    timestamped_path,
)
from paperflow.metadata import enrich_metadata_file
from paperflow.migration import default_dedupe_input, default_items_input, plan_migration_file
from paperflow.migration_apply import (
    APPLY_CONFIRMATION,
    TAG_REPLACE_ALL_CONFIRMATION,
    CollectionMode,
    TagMode,
    apply_migration_with_web_api,
    build_apply_preview,
    read_protected_collection_paths,
    validate_apply_request,
    write_apply_preview,
)
from paperflow.migration_models import MigrationPlan
from paperflow.models import OrganizePlan, ZoteroItem
from paperflow.planner import plan_from_jsonl
from paperflow.reporter import write_report
from paperflow.rollback import (
    ROLLBACK_CONFIRMATION,
    apply_rollback_plan,
    build_rollback_plan,
    validate_rollback_request,
    write_rollback_plan,
)
from paperflow.utils import dump_json_data, read_json_model, write_jsonl
from paperflow.vault import (
    DEFAULT_VAULT_LIBRARY,
    DEFAULT_VAULT_ROOT,
    ZOTERO_BASE_DIR_INSTRUCTION,
    init_vault,
    plan_vault_paths_file,
)
from paperflow.zotero_local import (
    DEFAULT_LIBRARY_PREFIX,
    DEFAULT_LOCAL_API_BASE_URL,
    LOCAL_API_SETUP_MESSAGE,
    LocalAPIUnavailable,
    ZoteroLocalClient,
)
from paperflow.zotero_web import (
    ApplyMode,
    WebAPIBackendDisabled,
    ZoteroWebClient,
    apply_plan_with_web_api,
    build_planned_api_calls,
)


console = Console()
app = typer.Typer(help="Safe Zotero AI paper organization planning.")
zotero_app = typer.Typer(help="Zotero scan, plan, report, and apply commands.")
vault_app = typer.Typer(help="Local-first PDF vault commands.")
local_app = typer.Typer(help="Local recursive paper import commands.")
credentials_app = typer.Typer(help="Credential verification commands.")
cleanup_app = typer.Typer(help="Cleanup workbench commands.")
app.add_typer(zotero_app, name="zotero")
app.add_typer(vault_app, name="vault")
app.add_typer(local_app, name="local")
app.add_typer(credentials_app, name="credentials")
app.add_typer(cleanup_app, name="cleanup")


class ApplyModeOption(StrEnum):
    ADD_ONLY = "add-only"
    REPLACE_COLLECTIONS = "replace-collections"


def parse_bool_value(value: bool | str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise typer.BadParameter("Expected a boolean value such as true or false.")


zotero_credentials_app = typer.Typer(help="Zotero credential commands.")
credentials_app.add_typer(zotero_credentials_app, name="zotero")


@zotero_credentials_app.command("verify")
def verify_zotero_credentials() -> None:
    """Verify Zotero API key and print non-secret JSON."""

    try:
        result = verify_zotero_api_key()
    except Exception as exc:
        console.print_json(data={"ok": False, "error_type": "invalid_key", "message": str(exc)})
        raise typer.Exit(2)
    console.print_json(data=result)


gemini_credentials_app = typer.Typer(help="Gemini credential commands.")
credentials_app.add_typer(gemini_credentials_app, name="gemini")


@gemini_credentials_app.command("verify")
def verify_gemini_credentials(
    model: str = typer.Option(
        DEFAULT_GEMINI_MODEL,
        "--model",
        help="Gemini model to test.",
    ),
) -> None:
    """Verify Gemini API key with a tiny Flash request and print JSON."""

    try:
        result = verify_gemini_api_key(model=model)
    except Exception as exc:
        console.print_json(data={"ok": False, "error_type": "invalid_key", "message": str(exc)})
        raise typer.Exit(2)
    console.print_json(data=result)
    if not result.get("ok"):
        raise typer.Exit(2)


@vault_app.command("init")
def vault_init(
    vault_root: Path = typer.Option(
        DEFAULT_VAULT_ROOT,
        "--vault-root",
        help="Root directory for the local PaperFlow vault.",
    ),
) -> None:
    """Create local PaperFlow vault directories."""

    paths = init_vault(vault_root)
    console.print("[bold green]Initialized PaperFlow vault directories:[/bold green]")
    for path in paths:
        console.print(f"- {path}")
    console.print("")
    console.print("[bold]Zotero linked attachment base directory[/bold]")
    console.print(ZOTERO_BASE_DIR_INSTRUCTION)


@vault_app.command("plan-paths")
def vault_plan_paths(
    input_path: Path = typer.Option(
        Path("data/migration_plan.json"),
        "--input",
        "-i",
        help="Migration plan JSON input.",
    ),
    output_path: Path = typer.Option(
        Path("data/vault_path_plan.json"),
        "--output",
        "-o",
        help="Vault path plan JSON output.",
    ),
    report_path: Path = typer.Option(
        Path("data/vault_path_report.md"),
        "--report",
        help="Vault path report Markdown output.",
    ),
    vault_library: Path = typer.Option(
        DEFAULT_VAULT_LIBRARY,
        "--vault-library",
        help="Local vault library directory.",
    ),
) -> None:
    """Plan safe local vault filenames for migrated Zotero items."""

    plan = plan_vault_paths_file(input_path, output_path, report_path, vault_library)
    console.print(
        f"Planned {len(plan['items'])} vault paths to {output_path}; report: {report_path}."
    )


@app.command("ingest")
def ingest(
    pdf_paths: list[Path] = typer.Argument(
        ...,
        help="PDF files to ingest into the local vault.",
    ),
    storage_mode: StorageMode = typer.Option(
        StorageMode.LINKED_LOCAL,
        "--storage-mode",
        help="PDF storage mode. Only linked-local is supported.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Plan ingest without copying files or writing Zotero.",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Copy PDFs to the vault and create Zotero linked attachments.",
    ),
    vault_library: Path = typer.Option(
        DEFAULT_VAULT_LIBRARY,
        "--vault-library",
        help="Local vault library directory.",
    ),
    json_output: Path = typer.Option(
        Path("data/ingest_plan.json"),
        "--json-output",
        help="Ingest plan JSON output.",
    ),
    report_path: Path = typer.Option(
        Path("data/ingest_report.md"),
        "--report",
        help="Ingest report Markdown output.",
    ),
    progress_jsonl: bool = typer.Option(
        False,
        "--progress-jsonl",
        help="Emit machine-readable progress events as JSON Lines.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Emit extra progress/debug context.",
    ),
    debug_trace: bool = typer.Option(
        False,
        "--debug-trace",
        help="Emit an ingest debug trace with file and metadata decisions.",
    ),
    total_timeout_seconds: int = typer.Option(
        60,
        "--total-timeout-seconds",
        help="Total ingest dry-run timeout budget in seconds.",
    ),
    network_timeout_seconds: int = typer.Option(
        10,
        "--network-timeout-seconds",
        help="Timeout for each arXiv/Crossref metadata call.",
    ),
    pdf_timeout_seconds: int = typer.Option(
        20,
        "--pdf-timeout-seconds",
        help="PDF parsing timeout budget in seconds.",
    ),
    llm_timeout_seconds: int = typer.Option(
        30,
        "--llm-timeout-seconds",
        help="LLM timeout budget if LLM extraction is explicitly enabled.",
    ),
    no_gemini: bool = typer.Option(
        False,
        "--no-gemini",
        help="Disable Gemini/LLM use. This is the default for dry-run.",
    ),
    no_network: bool = typer.Option(
        False,
        "--no-network",
        help="Disable arXiv/Crossref network metadata calls.",
    ),
    offline_fast: bool = typer.Option(
        False,
        "--offline-fast",
        help="Fast local-only dry-run: disables network and Gemini.",
    ),
) -> None:
    """Ingest PDFs as local vault files and Zotero linked attachments."""

    if not dry_run and not apply:
        dry_run = True

    user_id = os.environ.get("ZOTERO_USER_ID")
    api_key = os.environ.get("ZOTERO_API_KEY")
    try:
        validate_ingest_request(
            pdf_paths=pdf_paths,
            storage_mode=storage_mode,
            apply=apply,
            dry_run=dry_run,
            user_id=user_id,
            api_key=api_key,
        )
    except ValueError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(2)

    started_at = time.monotonic()
    network_enabled = not (no_network or offline_fast)
    gemini_enabled = False
    if not no_gemini and not dry_run and not offline_fast:
        gemini_enabled = False
    progress = ProgressEmitter(enabled=progress_jsonl)
    if verbose and progress_jsonl:
        progress.emit(
            "debug",
            "validate_files",
            "Ingest configured.",
            file_path=None,
            file_index=None,
            total_files=len(pdf_paths),
            total_timeout_seconds=total_timeout_seconds,
            network_timeout_seconds=network_timeout_seconds,
            pdf_timeout_seconds=pdf_timeout_seconds,
            llm_timeout_seconds=llm_timeout_seconds,
            gemini_enabled=gemini_enabled,
            network_enabled=network_enabled,
        )
    plan = build_ingest_plan(
        pdf_paths,
        vault_library=vault_library,
        progress=progress,
        network_enabled=network_enabled,
        network_timeout_seconds=network_timeout_seconds,
    )
    plan["mode"] = "apply" if apply else "dry-run"
    if time.monotonic() - started_at > total_timeout_seconds:
        console.print("[bold red]Ingest exceeded total timeout before writing report.[/bold red]")
        raise typer.Exit(124)
    if dry_run:
        dump_json_data(json_output, plan)
        with progress.stage(
            "write_dry_run_report",
            f"Writing ingest dry-run report to {report_path}",
            file_path=None,
            file_index=None,
            total_files=len(pdf_paths),
        ):
            write_ingest_report(plan, report_path, applied=False)
    if debug_trace:
        trace = build_ingest_debug_trace(
            plan,
            gemini_enabled=gemini_enabled,
            network_enabled=network_enabled,
            zotero_write_enabled=apply,
        )
        if progress_jsonl:
            progress.emit(
                "debug_trace",
                "write_dry_run_report",
                "Debug trace generated.",
                file_path=None,
                file_index=None,
                total_files=len(pdf_paths),
                trace=trace,
            )
        else:
            console.print_json(data=trace)
    if dry_run:
        progress.emit(
            "done",
            "done",
            f"Dry-run ingest planned {len(plan['items'])} PDFs. No files copied and no Zotero writes executed.",
            file_path=None,
            file_index=None,
            total_files=len(pdf_paths),
        )
        if not progress_jsonl:
            console.print(
                f"Dry-run ingest planned {len(plan['items'])} PDFs. "
                f"No files copied and no Zotero writes executed. Output: {json_output}, {report_path}."
            )
        return

    try:
        events = apply_ingest_plan(plan, user_id=user_id or "", api_key=api_key or "")
    except httpx.HTTPStatusError as exc:
        console.print("[bold red]Zotero rejected linked local attachment creation.[/bold red]")
        console.print(BRIDGE_NOTE)
        console.print(f"HTTP status: {exc.response.status_code}; response: {exc.response.text}")
        raise typer.Exit(2)
    apply_log_path = timestamped_ingest_apply_log_path(json_output.parent)
    dump_json_data(apply_log_path, build_ingest_apply_log(plan, events))
    write_ingest_report(plan, report_path, applied=True)
    progress.emit(
        "done",
        "done",
        f"Applied linked-local ingest for {len(plan['items'])} PDFs. No PDF bytes were uploaded to Zotero Storage.",
        file_path=None,
        file_index=None,
        total_files=len(pdf_paths),
    )
    if not progress_jsonl:
        console.print(
            f"Applied linked-local ingest for {len(plan['items'])} PDFs. "
            f"No PDF bytes were uploaded to Zotero Storage. Apply log: {apply_log_path}."
        )


@cleanup_app.command("repair-abstracts")
def cleanup_repair_abstracts(
    migration_plan: Path = typer.Option(
        Path("data/migration_plan.json"),
        "--migration-plan",
        help="Migration plan JSON input.",
    ),
    enriched_items: Path = typer.Option(
        Path("data/zotero_items_enriched.jsonl"),
        "--enriched-items",
        help="Enriched Zotero item JSONL input.",
    ),
    output_path: Path = typer.Option(
        Path("data/abstract_repair_plan.json"),
        "--output",
        "-o",
        help="Abstract repair plan JSON output.",
    ),
    report_path: Path = typer.Option(
        Path("data/abstract_repair_report.md"),
        "--report",
        help="Abstract repair report Markdown output.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Plan abstract repairs without Zotero writes.",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply high-confidence repairs to Zotero.",
    ),
    confirm: str | None = typer.Option(
        None,
        "--confirm",
        help=f'Required confirmation: "{ABSTRACT_CONFIRMATION}".',
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Allow overwriting non-empty Zotero abstractNote.",
    ),
    enable_gemini: bool = typer.Option(
        False,
        "--enable-gemini",
        "--use-gemini",
        help="Use Gemini as a final extraction-only fallback.",
    ),
    gemini_model: str = typer.Option(
        DEFAULT_GEMINI_MODEL,
        "--gemini-model",
        help="Gemini model for extraction fallback.",
    ),
    continue_on_gemini_quota: bool = typer.Option(
        False,
        "--continue-on-gemini-quota",
        help="Continue cleanup planning after Gemini reports rate limiting.",
    ),
    stop_on_gemini_quota: str | None = typer.Option(
        None,
        "--stop-on-gemini-quota",
        help="Boolean override; stop cleanup planning after Gemini quota/rate limiting.",
    ),
    item_key: list[str] | None = typer.Option(
        None,
        "--item-key",
        help="Limit repair planning/apply to a specific Zotero parent item key. Can be repeated.",
    ),
) -> None:
    """Repair Missing Abstract cleanup items with conservative evidence."""

    if not dry_run and not apply:
        dry_run = True
    plan = build_abstract_repair_plan(
        migration_plan_path=migration_plan,
        enriched_path=enriched_items,
        enable_gemini=enable_gemini,
        gemini_model=gemini_model,
        stop_on_gemini_quota_hit=(
            parse_bool_value(stop_on_gemini_quota)
            if stop_on_gemini_quota is not None
            else not continue_on_gemini_quota
        ),
        item_keys=set(item_key) if item_key else None,
    )
    dump_json_data(output_path, plan)
    write_abstract_repair_report(plan, report_path)
    if dry_run:
        console.print(f"Wrote abstract repair plan to {output_path}; no writes executed.")
        return
    try:
        validate_abstract_apply(apply=apply, confirm=confirm)
    except ValueError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(2)
    user_id = os.environ.get("ZOTERO_USER_ID")
    api_key = os.environ.get("ZOTERO_API_KEY")
    if not user_id or not api_key:
        console.print("[bold red]ZOTERO_USER_ID and ZOTERO_API_KEY must be set.[/bold red]")
        raise typer.Exit(2)
    events = apply_abstract_repairs(plan, user_id, api_key, overwrite=overwrite)
    dump_json_data(output_path.with_name("abstract_repair_apply_log.json"), {"events": events})
    console.print(f"Applied abstract repairs. Events: {len(events)}.")


@cleanup_app.command("repair-metadata")
def cleanup_repair_metadata(
    migration_plan: Path = typer.Option(
        Path("data/migration_plan.json"),
        "--migration-plan",
        help="Migration plan JSON input.",
    ),
    enriched_items: Path = typer.Option(
        Path("data/zotero_items_enriched.jsonl"),
        "--enriched-items",
        help="Enriched Zotero item JSONL input.",
    ),
    output_path: Path = typer.Option(
        Path("data/metadata_repair_plan.json"),
        "--output",
        "-o",
        help="Metadata repair plan JSON output.",
    ),
    report_path: Path = typer.Option(
        Path("data/metadata_repair_report.md"),
        "--report",
        help="Metadata repair report Markdown output.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan repairs without writes."),
    apply: bool = typer.Option(False, "--apply", help="Apply selected safe repairs."),
    confirm: str | None = typer.Option(
        None,
        "--confirm",
        help=f'Required confirmation: "{METADATA_CONFIRMATION}".',
    ),
    item_key: list[str] | None = typer.Option(
        None,
        "--item-key",
        help="Limit repair planning/apply to a specific Zotero parent item key. Can be repeated.",
    ),
    approved_field: list[str] | None = typer.Option(
        None,
        "--approved-field",
        help="Limit metadata writes to approved fields from the repair diff. Can be repeated.",
    ),
    enable_gemini: bool = typer.Option(
        False,
        "--enable-gemini",
        "--use-gemini",
        help="Use Gemini as a final extraction-only fallback.",
    ),
    gemini_model: str = typer.Option(
        DEFAULT_GEMINI_MODEL,
        "--gemini-model",
        help="Gemini model for extraction fallback.",
    ),
    continue_on_gemini_quota: bool = typer.Option(
        False,
        "--continue-on-gemini-quota",
        help="Continue cleanup planning after Gemini reports rate limiting.",
    ),
    stop_on_gemini_quota: str | None = typer.Option(
        None,
        "--stop-on-gemini-quota",
        help="Boolean override; stop cleanup planning after Gemini quota/rate limiting.",
    ),
) -> None:
    """Repair Missing Metadata cleanup items with field-level diffs."""

    if not dry_run and not apply:
        dry_run = True
    plan = build_metadata_repair_plan(
        migration_plan,
        enriched_items,
        item_keys=set(item_key) if item_key else None,
        approved_fields=set(approved_field) if approved_field else None,
        enable_gemini=enable_gemini,
        gemini_model=gemini_model,
        stop_on_gemini_quota_hit=(
            parse_bool_value(stop_on_gemini_quota)
            if stop_on_gemini_quota is not None
            else not continue_on_gemini_quota
        ),
    )
    dump_json_data(output_path, plan)
    write_metadata_repair_report(plan, report_path)
    if dry_run:
        console.print(f"Wrote metadata repair plan to {output_path}; no writes executed.")
        return
    try:
        validate_metadata_apply(apply=apply, confirm=confirm)
    except ValueError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(2)
    user_id = os.environ.get("ZOTERO_USER_ID")
    api_key = os.environ.get("ZOTERO_API_KEY")
    if not user_id or not api_key:
        console.print("[bold red]ZOTERO_USER_ID and ZOTERO_API_KEY must be set.[/bold red]")
        raise typer.Exit(2)
    events = apply_metadata_repairs(plan, user_id, api_key)
    dump_json_data(output_path.with_name("metadata_repair_apply_log.json"), {"events": events})
    console.print(f"Applied metadata repairs. Events: {len(events)}.")


@cleanup_app.command("plan-duplicates")
def cleanup_plan_duplicates(
    dedupe_path: Path = typer.Option(
        Path("data/dedupe_plan.json"),
        "--dedupe",
        help="Dedupe plan JSON input.",
    ),
    migration_path: Path = typer.Option(
        Path("data/migration_plan.json"),
        "--migration",
        help="Migration plan JSON input.",
    ),
    output_path: Path = typer.Option(
        Path("data/duplicate_resolution_plan.json"),
        "--output",
        "-o",
        help="Duplicate resolution plan JSON output.",
    ),
    report_path: Path = typer.Option(
        Path("data/duplicate_resolution_report.md"),
        "--report",
        help="Duplicate resolution report Markdown output.",
    ),
) -> None:
    """Build duplicate-resolution workbench plan; never deletes items."""

    plan = duplicate_resolution_plan(dedupe_path=dedupe_path, migration_path=migration_path)
    dump_json_data(output_path, plan)
    write_duplicate_resolution_report(plan, report_path)
    console.print(f"Wrote duplicate resolution plan to {output_path}; no writes executed.")


def _read_json_or_exit(path: Path, label: str) -> dict:
    if not path.exists():
        console.print(f"[bold red]{label} not found: {path}[/bold red]")
        raise typer.Exit(2)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[bold red]Could not read {label}: {exc}[/bold red]")
        raise typer.Exit(2)


@local_app.command("scan")
def local_scan_command(
    root_path: Path = typer.Argument(..., help="Local root folder or PDF file to scan."),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="Walk folders recursively."),
    include_hidden: bool = typer.Option(False, "--include-hidden", help="Include hidden files/folders."),
    max_depth: int | None = typer.Option(None, "--max-depth", help="Maximum recursive depth."),
    follow_symlinks: bool = typer.Option(False, "--follow-symlinks/--no-follow-symlinks", help="Follow symlinks while walking."),
    exclude_glob: list[str] | None = typer.Option(None, "--exclude-glob", help="Glob pattern to exclude; repeatable."),
    include_glob: list[str] | None = typer.Option(None, "--include-glob", help="Glob pattern to include; repeatable."),
    min_size_kb: int = typer.Option(1, "--min-size-kb", help="Skip PDFs smaller than this size."),
    max_size_mb: int | None = typer.Option(None, "--max-size-mb", help="Skip PDFs larger than this size."),
    output_path: Path = typer.Option(Path("data/local_scan.json"), "--output", "-o", help="JSON output."),
    report_path: Path = typer.Option(Path("data/local_scan_report.md"), "--report", help="Markdown report output."),
    csv_output: Path = typer.Option(Path("data/local_scan.csv"), "--csv-output", help="CSV report output."),
    progress_jsonl: bool = typer.Option(False, "--progress-jsonl", help="Emit progress JSONL."),
    verbose: bool = typer.Option(False, "--verbose", help="Emit extra scan warnings."),
) -> None:
    """Recursively scan local PDFs without modifying Zotero or files."""

    plan = local_scan(
        root_path=root_path,
        recursive=recursive,
        include_hidden=include_hidden,
        max_depth=max_depth,
        follow_symlinks=follow_symlinks,
        exclude_glob=exclude_glob or [],
        include_glob=include_glob or [],
        min_size_kb=min_size_kb,
        max_size_mb=max_size_mb,
        progress_jsonl=progress_jsonl,
        verbose=verbose,
    )
    dump_json_data(output_path, plan)
    write_local_scan_report(plan, report_path, csv_output)
    console.print(f"Scanned {len(plan['files'])} local PDF rows to {output_path}.")


@local_app.command("index-zotero")
def local_index_zotero_command(
    output_path: Path = typer.Option(Path("data/zotero_index.json"), "--output", "-o", help="JSON index output."),
    report_path: Path = typer.Option(Path("data/zotero_index_report.md"), "--report", help="Markdown report output."),
    base_url: str = typer.Option(DEFAULT_LOCAL_API_BASE_URL, "--base-url", help="Zotero Local API base URL."),
    library_prefix: str = typer.Option(DEFAULT_LIBRARY_PREFIX, "--library-prefix", help="Local API library prefix."),
    web_base_url: str = typer.Option("https://api.zotero.org", "--web-base-url", help="Zotero Web API base URL."),
    fallback_jsonl: Path = typer.Option(Path("data/zotero_items_enriched.jsonl"), "--fallback-jsonl", help="Fallback enriched item JSONL."),
) -> None:
    """Index existing Zotero items for local duplicate/existence detection."""

    try:
        index = build_zotero_index(
            local_base_url=base_url,
            library_prefix=library_prefix,
            web_base_url=web_base_url,
            fallback_jsonl=fallback_jsonl,
        )
    except LocalAPIUnavailable:
        console.print(f"[bold red]{LOCAL_API_SETUP_MESSAGE}[/bold red]")
        raise typer.Exit(2)
    dump_json_data(output_path, index)
    write_zotero_index_report(index, report_path)
    console.print(f"Indexed {len(index['items'])} Zotero parent items to {output_path}.")


@local_app.command("match-zotero")
def local_match_zotero_command(
    scan_path: Path = typer.Option(Path("data/local_scan.json"), "--scan", help="Local scan JSON input."),
    index_path: Path = typer.Option(Path("data/zotero_index.json"), "--index", help="Zotero index JSON input."),
    output_path: Path = typer.Option(Path("data/local_zotero_match_plan.json"), "--output", "-o", help="Match plan JSON output."),
    report_path: Path = typer.Option(Path("data/local_zotero_match_report.md"), "--report", help="Markdown report output."),
) -> None:
    """Determine which local PDFs already exist in Zotero."""

    scan = _read_json_or_exit(scan_path, "local scan JSON")
    index = _read_json_or_exit(index_path, "Zotero index JSON")
    plan = match_local_to_zotero(scan, index)
    dump_json_data(output_path, plan)
    write_match_report(plan, report_path)
    console.print(f"Wrote local/Zotero match plan to {output_path}.")


@local_app.command("classify-new")
def local_classify_new_command(
    scan_path: Path = typer.Option(Path("data/local_scan.json"), "--scan", help="Local scan JSON input."),
    match_path: Path = typer.Option(Path("data/local_zotero_match_plan.json"), "--matches", help="Local/Zotero match plan input."),
    output_path: Path = typer.Option(Path("data/local_classification_plan.json"), "--output", "-o", help="Classification plan JSON output."),
    report_path: Path = typer.Option(Path("data/local_classification_report.md"), "--report", help="Markdown report output."),
    csv_output: Path = typer.Option(Path("data/local_classification.csv"), "--csv-output", help="CSV report output."),
    include_possible_existing: bool = typer.Option(False, "--include-possible-existing", help="Classify possible matches for review/import."),
    include_update_candidates: bool = typer.Option(False, "--include-update-candidates", help="Classify newer arXiv/update candidates."),
    use_gemini: bool = typer.Option(False, "--use-gemini", help="Use Gemini only as fallback for ambiguous/low-confidence classification."),
    gemini_model: str = typer.Option(DEFAULT_GEMINI_MODEL, "--gemini-model", help="Gemini model for optional classification fallback."),
    gemini_batch_size: int = typer.Option(5, "--gemini-batch-size", min=1, help="Number of rows to process per Gemini batch window."),
    stop_on_gemini_quota: str = typer.Option("true", "--stop-on-gemini-quota", help="Stop and write a partial plan if Gemini reports quota/rate limiting."),
    gemini_review_threshold: float = typer.Option(0.75, "--gemini-review-threshold", min=0.0, max=1.0, help="Minimum Gemini confidence to accept a fallback classification."),
) -> None:
    """Classify only local PDFs that are not already in Zotero by default."""

    scan = _read_json_or_exit(scan_path, "local scan JSON")
    matches = _read_json_or_exit(match_path, "local/Zotero match JSON")
    plan = classify_new_local_papers(
        scan,
        matches,
        include_possible_existing=include_possible_existing,
        include_update_candidates=include_update_candidates,
        use_gemini=use_gemini,
        gemini_model=gemini_model,
        gemini_batch_size=gemini_batch_size,
        stop_on_gemini_quota=parse_bool_value(stop_on_gemini_quota),
        gemini_review_threshold=gemini_review_threshold,
    )
    dump_json_data(output_path, plan)
    write_classification_report(plan, report_path, csv_output)
    suffix = " Partial plan: Gemini quota/rate limit reached." if plan.get("partial") else ""
    console.print(f"Wrote local classification plan to {output_path}.{suffix}")


@local_app.command("plan-import")
def local_plan_import_command(
    classification_path: Path = typer.Option(Path("data/local_classification_plan.json"), "--classification", help="Classification plan input."),
    output_path: Path = typer.Option(Path("data/local_import_plan.json"), "--output", "-o", help="Import plan JSON output."),
    report_path: Path = typer.Option(Path("data/local_import_report.md"), "--report", help="Markdown report output."),
    vault_library: Path = typer.Option(DEFAULT_VAULT_LIBRARY, "--vault-library", help="Local vault library path."),
) -> None:
    """Plan vault copy/rename and Zotero linked attachment creation."""

    classification = _read_json_or_exit(classification_path, "local classification JSON")
    plan = plan_local_import(classification, vault_library=vault_library)
    dump_json_data(output_path, plan)
    write_import_plan_report(plan, report_path)
    console.print(f"Planned {len(plan['items'])} local imports to {output_path}. No writes executed.")


@local_app.command("apply-import")
def local_apply_import_command(
    input_path: Path = typer.Option(Path("data/local_import_plan.json"), "--input", "-i", help="Local import plan input."),
    apply: bool = typer.Option(False, "--apply", help="Required for copying/writing."),
    confirm: str | None = typer.Option(None, "--confirm", help=f'Required confirmation: "{LOCAL_IMPORT_CONFIRMATION}"'),
    web_base_url: str = typer.Option("https://api.zotero.org", "--web-base-url", help="Zotero Web API base URL."),
) -> None:
    """Apply local import as linked-local Zotero attachments."""

    user_id = os.environ.get("ZOTERO_USER_ID")
    api_key = os.environ.get("ZOTERO_API_KEY")
    try:
        validate_local_apply(apply=apply, confirm=confirm, user_id=user_id, api_key=api_key)
    except ValueError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(2)
    plan = _read_json_or_exit(input_path, "local import plan JSON")
    log = apply_local_import_plan(plan, user_id=user_id or "", api_key=api_key or "", web_base_url=web_base_url)
    json_log = timestamped_path("local_import_apply_log", data_dir=input_path.parent)
    md_log = json_log.with_suffix(".md")
    dump_json_data(json_log, log)
    write_local_apply_markdown(log, md_log)
    console.print(f"Applied local import. Logs: {json_log}, {md_log}.")


@local_app.command("audit-import")
def local_audit_import_command(
    plan_path: Path = typer.Option(Path("data/local_import_plan.json"), "--plan", help="Local import plan input."),
    apply_log_path: Path | None = typer.Option(None, "--apply-log", help="Apply log input; defaults to latest."),
    json_output: Path = typer.Option(Path("data/local_import_audit.json"), "--json-output", help="Audit JSON output."),
    markdown_output: Path = typer.Option(Path("data/local_import_audit.md"), "--markdown-output", help="Audit Markdown output."),
) -> None:
    """Verify local import results."""

    audit = audit_local_import(plan_path=plan_path, apply_log_path=apply_log_path, data_dir=json_output.parent)
    dump_json_data(json_output, audit)
    write_local_audit_report(audit, markdown_output)
    console.print(f"Wrote local import audit to {json_output} and {markdown_output}.")


@local_app.command("cleanup-source-files")
def local_cleanup_source_files_command(
    audit_path: Path = typer.Option(Path("data/local_import_audit.json"), "--audit", help="Import audit JSON input."),
    output_path: Path = typer.Option(Path("data/local_source_cleanup_report.json"), "--output", "-o", help="Cleanup JSON output."),
    markdown_output: Path = typer.Option(Path("data/local_source_cleanup_report.md"), "--markdown-output", help="Cleanup Markdown output."),
    apply: bool = typer.Option(False, "--apply", help="Move sources to quarantine."),
    confirm: str | None = typer.Option(None, "--confirm", help=f'Required confirmation: "{SOURCE_QUARANTINE_CONFIRMATION}"'),
) -> None:
    """Report or move imported source PDFs to quarantine. Never permanently deletes."""

    audit = _read_json_or_exit(audit_path, "local import audit JSON")
    try:
        validate_source_cleanup(apply=apply, confirm=confirm, audit=audit)
    except ValueError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(2)
    report = cleanup_source_files(audit, apply=apply)
    dump_json_data(output_path, report)
    write_source_cleanup_report(report, markdown_output)
    console.print(f"Wrote local source cleanup report to {output_path}.")


def _items_to_csv(items: list[ZoteroItem], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in items:
        rows.append(
            {
                "key": item.key,
                "version": item.version,
                "itemType": item.item_type,
                "title": item.title,
                "year": item.year,
                "DOI": item.doi,
                "URL": item.url,
                "publicationTitle": item.publication_title,
                "creators": "; ".join(
                    creator.name
                    or " ".join(
                        part
                        for part in [creator.first_name, creator.last_name]
                        if part
                    )
                    for creator in item.creators
                ),
                "tags": "; ".join(item.existing_tags),
                "collections": "; ".join(item.existing_collection_keys),
                "childAttachments": "; ".join(item.child_attachment_keys),
                "pdfPaths": "; ".join(
                    attachment.local_path or ""
                    for attachment in item.attachments
                    if attachment.is_pdf
                ),
                "hasAbstract": bool(item.abstract_note),
            }
        )
    pd.DataFrame(rows).to_csv(output_path, index=False)


@zotero_app.command("scan")
def scan(
    jsonl_output: Path = typer.Option(
        Path("data/zotero_items.jsonl"),
        "--jsonl-output",
        help="Path for scanned Zotero item JSONL.",
    ),
    csv_output: Path = typer.Option(
        Path("data/zotero_items.csv"),
        "--csv-output",
        help="Path for human-readable CSV summary.",
    ),
    base_url: str = typer.Option(
        DEFAULT_LOCAL_API_BASE_URL,
        "--base-url",
        help="Zotero Local API base URL.",
    ),
    library_prefix: str = typer.Option(
        DEFAULT_LIBRARY_PREFIX,
        "--library-prefix",
        help="Local API library prefix, usually /users/0.",
    ),
) -> None:
    """Read regular parent items from the Zotero Local API."""

    try:
        with ZoteroLocalClient(base_url=base_url, library_prefix=library_prefix) as client:
            items = client.scan_items()
    except LocalAPIUnavailable:
        console.print(f"[bold red]{LOCAL_API_SETUP_MESSAGE}[/bold red]")
        raise typer.Exit(2)

    write_jsonl(jsonl_output, items)
    _items_to_csv(items, csv_output)
    console.print(
        f"Scanned {len(items)} regular Zotero items to {jsonl_output} and {csv_output}."
    )


@zotero_app.command("plan-organize")
def plan_organize(
    input_path: Path = typer.Option(
        Path("data/zotero_items.jsonl"),
        "--input",
        "-i",
        help="Scanned Zotero item JSONL.",
    ),
    output_path: Path = typer.Option(
        Path("data/organize_plan.json"),
        "--output",
        "-o",
        help="Organization plan JSON output.",
    ),
    pdf_snippets: bool = typer.Option(
        False,
        "--pdf-snippets",
        help="Use first-page PDF snippets when local paths are available.",
    ),
) -> None:
    """Build a side-effect-free organization plan."""

    plan = plan_from_jsonl(input_path, output_path, use_pdf_snippets=pdf_snippets)
    console.print(
        "Planned "
        f"{plan.stats.scanned_items} items: "
        f"{plan.stats.classified_items} classified, "
        f"{plan.stats.inbox_items} sent to Inbox. Output: {output_path}"
    )


@zotero_app.command("report")
def report(
    input_path: Path = typer.Option(
        Path("data/organize_plan.json"),
        "--input",
        "-i",
        help="Organization plan JSON input.",
    ),
    markdown_output: Path = typer.Option(
        Path("data/organize_report.md"),
        "--markdown-output",
        help="Markdown report output.",
    ),
    csv_output: Path = typer.Option(
        Path("data/organize_report.csv"),
        "--csv-output",
        help="CSV report output.",
    ),
) -> None:
    """Generate Markdown and CSV reports from an organization plan."""

    plan = write_report(input_path, markdown_output, csv_output)
    console.print(
        f"Wrote report for {plan.stats.scanned_items} items to "
        f"{markdown_output} and {csv_output}."
    )


def _render_planned_calls(plan: OrganizePlan, user_id: str, mode: ApplyMode) -> None:
    calls = build_planned_api_calls(plan, user_id=user_id, mode=mode)
    table = Table(title="Planned Zotero Web API calls")
    table.add_column("Method")
    table.add_column("URL")
    table.add_column("Body / Note")
    for call in calls:
        body = call.body if call.body is not None else {}
        table.add_row(call.method, call.url, f"{body}\n{call.note or ''}")
    console.print(table)


@zotero_app.command("apply-plan")
def apply_plan(
    input_path: Path = typer.Option(
        Path("data/organize_plan.json"),
        "--input",
        "-i",
        help="Organization plan JSON input.",
    ),
    mode: ApplyModeOption = typer.Option(
        ApplyModeOption.ADD_ONLY,
        "--mode",
        help="Apply mode for future Web API writes.",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Required for any write operation. The backend is still disabled.",
    ),
) -> None:
    """Preview future Web API writes; refuse real writes in this version."""

    plan = read_json_model(input_path, OrganizePlan)
    user_id = os.environ.get("ZOTERO_USER_ID")
    api_key = os.environ.get("ZOTERO_API_KEY")
    display_user_id = user_id or "$ZOTERO_USER_ID"
    selected_mode = ApplyMode(mode.value)

    _render_planned_calls(plan, user_id=display_user_id, mode=selected_mode)

    if not apply:
        console.print(
            "[bold yellow]Dry-run only: no writes executed. "
            "Pass --apply to request writes.[/bold yellow]"
        )
        raise typer.Exit(2)

    if not user_id or not api_key:
        console.print(
            "[bold red]Refusing to apply: ZOTERO_USER_ID and ZOTERO_API_KEY "
            "must be set.[/bold red]"
        )
        raise typer.Exit(2)

    try:
        apply_plan_with_web_api(plan=plan, user_id=user_id, api_key=api_key, mode=selected_mode)
    except WebAPIBackendDisabled as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(2)


def _read_current_zotero_state_for_preview(
    base_url: str = DEFAULT_LOCAL_API_BASE_URL,
    library_prefix: str = DEFAULT_LIBRARY_PREFIX,
    web_base_url: str = "https://api.zotero.org",
) -> tuple[list[dict], list[dict]]:
    try:
        with ZoteroLocalClient(base_url=base_url, library_prefix=library_prefix) as client:
            return client.iter_collections(), client.iter_items()
    except Exception:
        user_id = os.environ.get("ZOTERO_USER_ID")
        api_key = os.environ.get("ZOTERO_API_KEY")
        if user_id and api_key:
            with ZoteroWebClient(user_id=user_id, api_key=api_key, base_url=web_base_url) as client:
                return client.iter_collections(), client.iter_items()
    console.print(
        "[bold yellow]Could not read current Zotero collections/items; "
        "preview will use placeholder collection keys.[/bold yellow]"
    )
    return [], []


@zotero_app.command("backup")
def backup(
    output_root: Path = typer.Option(
        Path("data/backups"),
        "--output-root",
        help="Backup root directory.",
    ),
    base_url: str = typer.Option(
        DEFAULT_LOCAL_API_BASE_URL,
        "--base-url",
        help="Zotero Local API base URL.",
    ),
    library_prefix: str = typer.Option(
        DEFAULT_LIBRARY_PREFIX,
        "--library-prefix",
        help="Local API library prefix, usually /users/0.",
    ),
    web_base_url: str = typer.Option(
        "https://api.zotero.org",
        "--web-base-url",
        help="Zotero Web API base URL used only as read fallback.",
    ),
) -> None:
    """Export a full restorable Zotero snapshot without writes."""

    try:
        backup_dir = write_backup_snapshot(
            backup_root=output_root,
            local_base_url=base_url,
            library_prefix=library_prefix,
            web_base_url=web_base_url,
        )
    except LocalAPIUnavailable as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(2)
    console.print(f"Wrote Zotero backup snapshot to {backup_dir}.")


@zotero_app.command("enrich-metadata")
def enrich_metadata(
    input_path: Path = typer.Option(
        Path("data/zotero_items.jsonl"),
        "--input",
        "-i",
        help="Scanned Zotero item JSONL.",
    ),
    output_path: Path = typer.Option(
        Path("data/zotero_items_enriched.jsonl"),
        "--output",
        "-o",
        help="Enriched item JSONL output.",
    ),
    report_path: Path = typer.Option(
        Path("data/metadata_repair_report.md"),
        "--report",
        help="Metadata repair report output.",
    ),
) -> None:
    """Enrich local scan metadata without Zotero writes."""

    items = enrich_metadata_file(input_path, output_path, report_path)
    console.print(f"Enriched {len(items)} items to {output_path}; report: {report_path}.")


@zotero_app.command("detect-duplicates")
def detect_duplicates(
    input_path: Path | None = typer.Option(
        None,
        "--input",
        "-i",
        help="Enriched JSONL input. Defaults to enriched scan if present.",
    ),
    output_path: Path = typer.Option(
        Path("data/dedupe_plan.json"),
        "--output",
        "-o",
        help="Duplicate candidate plan JSON output.",
    ),
    report_path: Path = typer.Option(
        Path("data/dedupe_report.md"),
        "--report",
        help="Duplicate report output.",
    ),
) -> None:
    """Detect duplicate candidates for review; never deletes items."""

    source = input_path or default_dedupe_input(
        Path("data/zotero_items_enriched.jsonl"),
        Path("data/zotero_items.jsonl"),
    )
    plan = detect_duplicates_file(source, output_path, report_path)
    console.print(
        f"Detected {len(plan.groups)} duplicate groups with "
        f"{len(plan.duplicate_candidate_keys)} duplicate candidates."
    )


@zotero_app.command("plan-migration")
def plan_migration(
    input_path: Path | None = typer.Option(
        None,
        "--input",
        "-i",
        help="Enriched JSONL input. Defaults to enriched scan if present.",
    ),
    dedupe_path: Path = typer.Option(
        Path("data/dedupe_plan.json"),
        "--dedupe",
        help="Dedupe plan JSON input if present.",
    ),
    output_path: Path = typer.Option(
        Path("data/migration_plan.json"),
        "--output",
        "-o",
        help="Migration plan JSON output.",
    ),
    markdown_output: Path = typer.Option(
        Path("data/migration_report.md"),
        "--markdown-output",
        help="Migration report Markdown output.",
    ),
    csv_output: Path = typer.Option(
        Path("data/migration_report.csv"),
        "--csv-output",
        help="Migration report CSV output.",
    ),
) -> None:
    """Generate a taxonomy v2 migration plan with no side effects."""

    source = input_path or default_items_input(
        Path("data/zotero_items_enriched.jsonl"),
        Path("data/zotero_items.jsonl"),
    )
    plan = plan_migration_file(
        source,
        output_path,
        markdown_output,
        csv_output,
        dedupe_path=dedupe_path if dedupe_path.exists() else None,
    )
    console.print(
        f"Planned migration for {plan.stats.planned_items} items. "
        f"Output: {output_path}, {markdown_output}, {csv_output}."
    )


@zotero_app.command("dry-run-migration")
def dry_run_migration(
    input_path: Path = typer.Option(
        Path("data/migration_plan.json"),
        "--input",
        "-i",
        help="Migration plan JSON input.",
    ),
    json_output: Path = typer.Option(
        Path("data/apply_preview.json"),
        "--json-output",
        help="Apply preview JSON output.",
    ),
    markdown_output: Path = typer.Option(
        Path("data/apply_preview.md"),
        "--markdown-output",
        help="Apply preview Markdown output.",
    ),
    collection_mode: CollectionMode = typer.Option(
        CollectionMode.REPLACE_ALL,
        "--collection-mode",
        help="Collection replacement mode for preview.",
    ),
    tag_mode: TagMode = typer.Option(
        TagMode.REPLACE_MANAGED,
        "--tag-mode",
        help="Tag replacement mode for preview.",
    ),
) -> None:
    """Print and save exact planned Zotero API operations without writes."""

    plan = read_json_model(input_path, MigrationPlan)
    collections, items = _read_current_zotero_state_for_preview()
    protected_paths = read_protected_collection_paths()
    user_id = os.environ.get("ZOTERO_USER_ID") or "$ZOTERO_USER_ID"
    preview = build_apply_preview(
        plan,
        collections,
        items,
        user_id=user_id,
        collection_mode=collection_mode,
        tag_mode=tag_mode,
        protected_collection_paths=protected_paths,
    )
    write_apply_preview(preview, json_output, markdown_output)
    console.print(
        f"Dry-run wrote {len(preview.operations)} planned operations to "
        f"{json_output} and {markdown_output}."
    )


@zotero_app.command("apply-migration")
def apply_migration(
    input_path: Path = typer.Option(
        Path("data/migration_plan.json"),
        "--input",
        "-i",
        help="Migration plan JSON input.",
    ),
    collection_mode: CollectionMode = typer.Option(
        CollectionMode.REPLACE_ALL,
        "--collection-mode",
        help="Collection application mode.",
    ),
    tag_mode: TagMode = typer.Option(
        TagMode.REPLACE_MANAGED,
        "--tag-mode",
        help="Tag application mode.",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Required for Zotero writes.",
    ),
    confirm: str | None = typer.Option(
        None,
        "--confirm",
        help=f'Required confirmation: "{APPLY_CONFIRMATION}".',
    ),
    confirm_tags: str | None = typer.Option(
        None,
        "--confirm-tags",
        help=f'Required only for replace-all tags: "{TAG_REPLACE_ALL_CONFIRMATION}".',
    ),
) -> None:
    """Apply migration_plan.json to Zotero through the Web API."""

    user_id = os.environ.get("ZOTERO_USER_ID")
    api_key = os.environ.get("ZOTERO_API_KEY")
    try:
        validate_apply_request(
            apply=apply,
            confirm=confirm,
            tag_mode=tag_mode,
            confirm_tags=confirm_tags,
            user_id=user_id,
            api_key=api_key,
        )
    except ValueError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(2)

    try:
        key_info = verify_zotero_api_key(api_key)
        if not zotero_key_has_write_access(key_info):
            console.print("[bold red]Refusing to apply: Zotero API key lacks write access.[/bold red]")
            raise typer.Exit(2)
    except typer.Exit:
        raise
    except Exception:
        console.print("[bold yellow]Could not verify Zotero key permissions before apply.[/bold yellow]")

    protected_paths = read_protected_collection_paths()
    json_log, md_log = apply_migration_with_web_api(
        input_path,
        user_id=user_id or "",
        api_key=api_key or "",
        collection_mode=collection_mode,
        tag_mode=tag_mode,
        protected_collection_paths=protected_paths,
    )
    console.print(f"Applied migration. Logs: {json_log}, {md_log}.")


@zotero_app.command("cleanup-collections")
def cleanup_collections(
    mode: CleanupMode = typer.Option(
        CleanupMode.REPORT_ONLY,
        "--mode",
        help="Cleanup mode.",
    ),
    output_path: Path = typer.Option(
        Path("data/cleanup_report.md"),
        "--output",
        "-o",
        help="Cleanup report Markdown output.",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Required for cleanup writes.",
    ),
    confirm: str | None = typer.Option(
        None,
        "--confirm",
        help="Required cleanup confirmation string.",
    ),
    force_nonempty: bool = typer.Option(
        False,
        "--force-nonempty",
        help="Allow deleting non-empty old collections with stronger confirmation.",
    ),
) -> None:
    """Report, delete empty, or archive old collections outside AI Library."""

    try:
        validate_cleanup_request(
            mode=mode,
            apply=apply,
            confirm=confirm,
            force_nonempty=force_nonempty,
        )
    except ValueError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(2)

    api_key = os.environ.get("ZOTERO_API_KEY")
    real_user_id = os.environ.get("ZOTERO_USER_ID")
    if mode == CleanupMode.REPORT_ONLY:
        collections, items = _read_current_zotero_state_for_preview()
        user_id = real_user_id or "$ZOTERO_USER_ID"
    else:
        if not real_user_id or not api_key:
            console.print("[bold red]ZOTERO_USER_ID and ZOTERO_API_KEY must be set.[/bold red]")
            raise typer.Exit(2)
        if not real_user_id.isdigit():
            console.print(
                "[bold red]ZOTERO_USER_ID must be your numeric Zotero user ID.[/bold red]"
            )
            raise typer.Exit(2)
        with ZoteroWebClient(user_id=real_user_id, api_key=api_key) as client:
            collections = client.iter_collections()
            items = client.iter_items()
        user_id = real_user_id

    report = build_cleanup_report(
        collections,
        items,
        mode=mode,
        user_id=user_id,
        force_nonempty=force_nonempty,
    )
    write_cleanup_report(report, output_path)
    if mode == CleanupMode.REPORT_ONLY:
        console.print(f"Wrote cleanup report to {output_path}. No writes executed.")
        return

    events = apply_cleanup_report(report, real_user_id, api_key)
    dump_json_data(output_path.with_name("cleanup_apply_log.json"), {"events": events})
    console.print(f"Cleanup applied. Events: {len(events)}.")


@zotero_app.command("plan-localize-attachments")
def plan_localize_attachments(
    output_path: Path = typer.Option(
        Path("data/localize_attachments_plan.json"),
        "--output",
        "-o",
        help="Stored attachment localization plan JSON output.",
    ),
    report_path: Path = typer.Option(
        Path("data/localize_attachments_report.md"),
        "--report",
        help="Stored attachment localization report output.",
    ),
    vault_library: Path = typer.Option(
        DEFAULT_VAULT_LIBRARY,
        "--vault-library",
        help="Local vault library directory.",
    ),
    base_url: str = typer.Option(
        DEFAULT_LOCAL_API_BASE_URL,
        "--base-url",
        help="Zotero Local API base URL.",
    ),
    library_prefix: str = typer.Option(
        DEFAULT_LIBRARY_PREFIX,
        "--library-prefix",
        help="Local API library prefix, usually /users/0.",
    ),
) -> None:
    """Plan conversion of stored Zotero PDFs into local linked PDFs."""

    try:
        plan = plan_localize_attachments_file(
            output_path=output_path,
            report_path=report_path,
            local_base_url=base_url,
            library_prefix=library_prefix,
            vault_library=vault_library,
        )
    except RuntimeError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(2)
    console.print(
        f"Planned localization for {len(plan['items'])} stored PDF attachments. "
        f"Output: {output_path}, {report_path}."
    )


@zotero_app.command("apply-localize-attachments")
def apply_localize_attachments(
    input_path: Path = typer.Option(
        Path("data/localize_attachments_plan.json"),
        "--input",
        "-i",
        help="Stored attachment localization plan JSON input.",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Required for Zotero writes.",
    ),
    confirm: str | None = typer.Option(
        None,
        "--confirm",
        help=f'Required confirmation: "{LOCALIZE_CONFIRMATION}".',
    ),
) -> None:
    """Copy stored PDFs to the vault and create linked Zotero attachments."""

    user_id = os.environ.get("ZOTERO_USER_ID")
    api_key = os.environ.get("ZOTERO_API_KEY")
    try:
        validate_localize_apply(
            apply=apply,
            confirm=confirm,
            user_id=user_id,
            api_key=api_key,
        )
    except ValueError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(2)

    import json

    plan = json.loads(input_path.read_text(encoding="utf-8"))
    try:
        events = apply_localize_attachments_plan(
            plan,
            user_id=user_id or "",
            api_key=api_key or "",
        )
    except httpx.HTTPStatusError as exc:
        console.print("[bold red]Zotero rejected linked local attachment creation.[/bold red]")
        console.print(BRIDGE_NOTE)
        console.print(f"HTTP status: {exc.response.status_code}; response: {exc.response.text}")
        raise typer.Exit(2)
    json_log, md_log = write_apply_log(events)
    console.print(f"Applied attachment localization. Logs: {json_log}, {md_log}.")


@zotero_app.command("verify-localized-attachments")
def verify_localized_attachments(
    input_path: Path = typer.Option(
        Path("data/localize_attachments_plan.json"),
        "--input",
        "-i",
        help="Stored attachment localization plan JSON input.",
    ),
    json_output: Path = typer.Option(
        Path("data/localize_verify_report.json"),
        "--json-output",
        help="Localization verification JSON output.",
    ),
    markdown_output: Path = typer.Option(
        Path("data/localize_verify_report.md"),
        "--markdown-output",
        help="Localization verification Markdown output.",
    ),
) -> None:
    """Verify localized linked PDFs and old stored PDFs still exist."""

    report = verify_localized_attachments_file(
        plan_path=input_path,
        json_output=json_output,
        markdown_output=markdown_output,
        user_id=os.environ.get("ZOTERO_USER_ID"),
        api_key=os.environ.get("ZOTERO_API_KEY"),
    )
    ok_count = sum(1 for item in report["items"] if item["ok"])
    console.print(
        f"Verified {len(report['items'])} localized attachments; "
        f"{ok_count} OK. Output: {json_output}, {markdown_output}."
    )


@zotero_app.command("cleanup-stored-attachments")
def cleanup_stored_attachments(
    input_path: Path = typer.Option(
        Path("data/localize_attachments_plan.json"),
        "--input",
        "-i",
        help="Stored attachment localization plan JSON input.",
    ),
    verify_path: Path = typer.Option(
        Path("data/localize_verify_report.json"),
        "--verify",
        help="Localization verification JSON input.",
    ),
    json_output: Path = typer.Option(
        Path("data/stored_attachment_cleanup_report.json"),
        "--json-output",
        help="Stored attachment cleanup JSON report output.",
    ),
    markdown_output: Path = typer.Option(
        Path("data/stored_attachment_cleanup_report.md"),
        "--markdown-output",
        help="Stored attachment cleanup Markdown report output.",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Required to delete old stored attachment items.",
    ),
    confirm: str | None = typer.Option(
        None,
        "--confirm",
        help=f'Required confirmation: "{CLEANUP_STORED_CONFIRMATION}".',
    ),
) -> None:
    """Report or delete verified old stored PDF attachments."""

    user_id = os.environ.get("ZOTERO_USER_ID")
    api_key = os.environ.get("ZOTERO_API_KEY")
    try:
        validate_cleanup_stored_request(
            apply=apply,
            confirm=confirm,
            verify_path=verify_path,
            user_id=user_id,
            api_key=api_key,
        )
    except ValueError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(2)

    report, events = cleanup_stored_attachments_file(
        plan_path=input_path,
        verify_path=verify_path,
        json_output=json_output,
        markdown_output=markdown_output,
        apply=apply,
        user_id=user_id,
        api_key=api_key,
    )
    if not apply:
        console.print(
            f"Wrote stored attachment cleanup report to {markdown_output}. "
            "No writes executed."
        )
        return
    dump_json_data(json_output.with_name("stored_attachment_cleanup_apply_log.json"), {"events": events})
    deleted = sum(1 for event in events if event["event"] == "old-stored-attachment-deleted")
    console.print(
        f"Stored attachment cleanup applied. Deleted {deleted} old stored attachment items; "
        "parent items and linked vault files were preserved."
    )


@zotero_app.command("explain-item")
def explain_item_command(
    item_key: str = typer.Argument(..., help="Zotero item key to explain."),
    migration_path: Path = typer.Option(
        Path("data/migration_plan.json"),
        "--migration",
        help="Migration plan JSON input.",
    ),
    preview_path: Path = typer.Option(
        Path("data/apply_preview.json"),
        "--preview",
        help="Apply preview JSON input.",
    ),
) -> None:
    """Explain where a paper was planned to move and why."""

    try:
        result = explain_item_data(item_key, migration_path, preview_path)
    except ValueError as exc:
        console.print_json(data={"ok": False, "message": str(exc)})
        raise typer.Exit(2)
    console.print_json(data=result)


@zotero_app.command("migration-audit")
def migration_audit_command(
    migration_path: Path = typer.Option(
        Path("data/migration_plan.json"),
        "--migration",
        help="Migration plan JSON input.",
    ),
    preview_path: Path = typer.Option(
        Path("data/apply_preview.json"),
        "--preview",
        help="Apply preview JSON input.",
    ),
    json_output: Path = typer.Option(
        Path("data/migration_audit.json"),
        "--json-output",
        help="Migration audit JSON output.",
    ),
    markdown_output: Path = typer.Option(
        Path("data/migration_audit.md"),
        "--markdown-output",
        help="Migration audit Markdown output.",
    ),
) -> None:
    """Audit migration status from local plans/logs."""

    audit = build_migration_audit(migration_path=migration_path, preview_path=preview_path)
    dump_json_data(json_output, audit)
    write_migration_audit_report(audit, markdown_output)
    console.print(f"Wrote migration audit to {json_output} and {markdown_output}.")


@zotero_app.command("explain-ingest")
def explain_ingest_command(
    plan_path: Path = typer.Argument(
        ...,
        help="Ingest plan or apply log JSON file.",
    ),
) -> None:
    """Explain where an ingest dry-run/apply would put papers."""

    if not plan_path.exists():
        console.print(f"[bold red]Ingest JSON not found: {plan_path}[/bold red]")
        raise typer.Exit(2)
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[bold red]Could not read ingest JSON: {exc}[/bold red]")
        raise typer.Exit(2)
    console.print(explain_ingest_plan(payload), soft_wrap=True)


@zotero_app.command("rollback")
def rollback(
    backup_dir: Path = typer.Option(
        ...,
        "--backup",
        help="Backup directory, for example data/backups/<timestamp>.",
    ),
    output_path: Path = typer.Option(
        Path("data/rollback_plan.md"),
        "--output",
        "-o",
        help="Rollback plan Markdown output.",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Required for rollback writes.",
    ),
    confirm: str | None = typer.Option(
        None,
        "--confirm",
        help=f'Required confirmation: "{ROLLBACK_CONFIRMATION}".',
    ),
    remove_new_collections: bool = typer.Option(
        False,
        "--remove-new-collections",
        help="Do not use by default; new AI Library collections are preserved unless set.",
    ),
) -> None:
    """Restore item collections and tags from a backup."""

    plan = build_rollback_plan(
        backup_dir,
        remove_new_collections=remove_new_collections,
    )
    write_rollback_plan(plan, output_path)
    try:
        validate_rollback_request(apply=apply, confirm=confirm, backup_dir=backup_dir)
    except ValueError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(2)

    user_id = os.environ.get("ZOTERO_USER_ID")
    api_key = os.environ.get("ZOTERO_API_KEY")
    if not user_id or not api_key:
        console.print("[bold red]ZOTERO_USER_ID and ZOTERO_API_KEY must be set.[/bold red]")
        raise typer.Exit(2)
    events = apply_rollback_plan(plan, user_id, api_key)
    dump_json_data(output_path.with_name("rollback_apply_log.json"), {"events": events})
    console.print(f"Rollback applied. Events: {len(events)}.")


if __name__ == "__main__":
    app()
