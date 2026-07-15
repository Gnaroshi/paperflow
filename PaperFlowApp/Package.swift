// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "PaperFlowApp",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "PaperFlowApp", targets: ["PaperFlowApp"])
    ],
    targets: [
        .executableTarget(
            name: "PaperFlowApp",
            path: ".",
            exclude: [
                "README.md",
                "UI_UX_CHECKLIST.md",
                "Info.plist",
                "PaperFlow.entitlements",
                "build_app.sh",
                "install_app.sh",
                "distribution_check.sh",
                "dist"
            ],
            sources: [
                "PaperFlowApp.swift",
                "ContentView.swift",
                "SettingsView.swift",
                "AppTheme.swift",
                "CommandRunner.swift",
                "KeychainStore.swift",
                "AppState.swift",
                "Models.swift",
                "MenuBarController.swift",
                "FloatingDropShelfController.swift",
                "HotZoneWindow.swift",
                "DropShelfPanel.swift",
                "DropShelfView.swift",
                "MultiMonitorManager.swift",
                "ScreenPlacementPolicy.swift",
                "GlobalHotkeyManager.swift",
                "CommandPopupWindow.swift",
                "CommandPaletteView.swift",
                "MainWindowView.swift",
                "DashboardView.swift",
                "ZoteroOrganizeView.swift",
                "LocalVaultView.swift",
                "LocalFolderImportView.swift",
                "ExistingAttachmentsView.swift",
                "CleanupWorkbenchView.swift",
                "UserGuideView.swift",
                "ReportsView.swift",
                "ReportParser.swift",
                "PermissionManager.swift"
            ]
        )
    ]
)
