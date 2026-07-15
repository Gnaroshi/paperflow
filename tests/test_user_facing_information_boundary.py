from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "PaperFlowApp"


def source(name: str) -> str:
    return (APP / name).read_text(encoding="utf-8")


def test_technical_details_are_opt_in_and_logs_are_filtered() -> None:
    app_state = source("AppState.swift")
    main = source("MainWindowView.swift")
    shelf = source("DropShelfView.swift")

    assert "@Published var showTechnicalDetails = false" in app_state
    assert "AppSection.visibleCases(showTechnicalDetails:" in main
    assert "PFWMode.visibleCases(showTechnicalDetails:" in shelf
    assert "ForEach(AppSection.allCases)" not in main
    assert "ForEach(PFWMode.allCases)" not in shelf


def test_primary_copy_does_not_expose_known_developer_literals() -> None:
    primary_sources = "\n".join(
        source(name)
        for name in (
            "DashboardView.swift",
            "UserGuideView.swift",
            "ZoteroOrganizeView.swift",
            "LocalVaultView.swift",
            "ExistingAttachmentsView.swift",
        )
    )
    forbidden = (
        'Text("PID:',
        'Text("Command:',
        "Backend missing:",
        "JSONL",
        "API operation",
        "config/user_taxonomy_overrides.yaml",
        "ingest_report.md",
    )

    for literal in forbidden:
        assert literal not in primary_sources


def test_dashboard_does_not_show_project_path_or_repeated_sync_warning() -> None:
    dashboard = source("DashboardView.swift")

    assert "Text(state.projectPath)" not in dashboard
    assert "SyncWarningBox" not in dashboard
    assert "queued" not in dashboard


def test_routine_apply_does_not_require_typed_confirmation() -> None:
    main = source("MainWindowView.swift")
    models = source("Models.swift")

    assert "if kind.requiresTypedConfirmation" in main
    assert "case .cleanupDeleteEmpty, .cleanupStoredAttachments:" in models
    assert "case .applyIngest, .applyMigration" not in models


def test_command_palette_and_cleanup_hide_backend_language() -> None:
    palette = source("CommandPaletteView.swift")
    cleanup = source("CleanupWorkbenchView.swift")

    assert "uv run paperflow" not in palette
    assert "Backend command missing" not in cleanup
