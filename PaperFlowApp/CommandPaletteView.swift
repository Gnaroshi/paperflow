import SwiftUI

struct CommandPaletteView: View {
    @EnvironmentObject private var state: AppState
    let onClose: () -> Void

    @State private var query = ""
    @State private var selectedID = "dry-run-migration"
    @State private var confirmation = ""
    @FocusState private var searchFocused: Bool

    private var actions: [PaletteAction] {
        [
            PaletteAction(id: "ingest", title: "Ingest PDFs", subtitle: "Show floating drop shelf", destructive: false) {
                AppServices.shared.shelfController?.showExpanded()
            },
            PaletteAction(id: "backup", title: "Backup Zotero", subtitle: "uv run paperflow zotero backup", destructive: false) {
                state.runBackupZotero()
            },
            PaletteAction(id: "enrich", title: "Enrich Metadata", subtitle: "uv run paperflow zotero enrich-metadata", destructive: false) {
                state.runEnrichMetadata()
            },
            PaletteAction(id: "dedupe", title: "Detect Duplicates", subtitle: "uv run paperflow zotero detect-duplicates", destructive: false) {
                state.runDetectDuplicates()
            },
            PaletteAction(id: "plan", title: "Plan Migration", subtitle: "uv run paperflow zotero plan-migration", destructive: false) {
                state.runPlanMigration()
            },
            PaletteAction(id: "dry-run-migration", title: "Dry Run Migration", subtitle: "uv run paperflow zotero dry-run-migration", destructive: false) {
                state.runDryRunMigration()
            },
            PaletteAction(id: "cleanup-workbench", title: "Open Cleanup Workbench", subtitle: "Review Missing Abstract, Missing Metadata, Duplicates", destructive: false) {
                state.selectedSection = .cleanupWorkbench
                AppServices.shared.openMainWindow()
            },
            PaletteAction(id: "repair-abstracts", title: "Repair Abstracts Dry Run", subtitle: "uv run paperflow cleanup repair-abstracts --dry-run", destructive: false) {
                state.runRepairAbstractsDryRun()
            },
            PaletteAction(id: "repair-metadata", title: "Repair Metadata Dry Run", subtitle: "uv run paperflow cleanup repair-metadata --dry-run", destructive: false) {
                state.runRepairMetadataDryRun()
            },
            PaletteAction(id: "migration-audit", title: "Migration Audit", subtitle: "uv run paperflow zotero migration-audit", destructive: false) {
                state.runMigrationAudit()
            },
            PaletteAction(id: "apply-migration", title: "Apply Migration", subtitle: "Requires typed confirmation", destructive: true) {
                state.runApplyMigration()
            },
            PaletteAction(id: "latest-report", title: "Open Latest Report", subtitle: "Open latest apply log or reports folder", destructive: false) {
                state.openLatestApplyLog()
            },
            PaletteAction(id: "vault", title: "Open Vault", subtitle: state.vaultPath, destructive: false) {
                state.openVault()
            },
            PaletteAction(id: "zotero", title: "Open Zotero", subtitle: "Launch Zotero Desktop", destructive: false) {
                state.openZotero()
            }
        ]
    }

    private var filteredActions: [PaletteAction] {
        guard !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return actions
        }
        let lowered = query.lowercased()
        return actions.filter {
            $0.title.lowercased().contains(lowered) || $0.subtitle.lowercased().contains(lowered)
        }
    }

    private var selectedAction: PaletteAction? {
        filteredActions.first { $0.id == selectedID } ?? filteredActions.first
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField("Search PaperFlow actions", text: $query)
                    .textFieldStyle(.plain)
                    .focused($searchFocused)
                    .onSubmit {
                        runSelected()
                    }
            }
            .padding(16)

            Divider()

            ScrollView {
                LazyVStack(spacing: 4) {
                    ForEach(filteredActions) { action in
                        Button {
                            selectedID = action.id
                            if !action.destructive {
                                action.run()
                                onClose()
                            }
                        } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(action.title)
                                        .fontWeight(action.id == selectedID ? .semibold : .regular)
                                    Text(action.subtitle)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                if action.destructive {
                                    Image(systemName: "exclamationmark.triangle")
                                        .foregroundStyle(.orange)
                                }
                            }
                            .padding(10)
                            .background(action.id == selectedID ? Color.accentColor.opacity(0.14) : Color.clear)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                        }
                        .buttonStyle(.plain)
                        .onHover { hovering in
                            if hovering {
                                selectedID = action.id
                            }
                        }
                    }
                }
                .padding(10)
            }

            if selectedAction?.destructive == true {
                Divider()
                VStack(alignment: .leading, spacing: 8) {
                    Text("Apply Migration requires confirmation")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextField("REPLACE MY ZOTERO COLLECTIONS", text: $confirmation)
                        .textFieldStyle(.roundedBorder)
                }
                .padding(12)
            }

            Divider()
            HStack {
                Text("Enter runs selected dry-run action. Escape closes.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Button("Close", action: onClose)
            }
            .padding(12)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .onAppear {
            searchFocused = true
            selectedID = filteredActions.first?.id ?? selectedID
        }
        .onChange(of: query) { _ in
            selectedID = filteredActions.first?.id ?? selectedID
        }
    }

    private func runSelected() {
        guard let action = selectedAction else {
            return
        }
        if action.destructive {
            guard confirmation == ConfirmationKind.applyMigration.requiredText else {
                return
            }
        }
        action.run()
        onClose()
    }
}

private struct PaletteAction: Identifiable {
    let id: String
    let title: String
    let subtitle: String
    let destructive: Bool
    let run: () -> Void
}
