import SwiftUI

struct ZoteroOrganizeView: View {
    @EnvironmentObject private var state: AppState
    let confirm: (ConfirmationKind) -> Void
    @State private var applyConfirmation = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionTitle("Zotero Organize")
            SyncWarningBox()

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 12)], spacing: 12) {
                WorkflowButton(title: "Backup Zotero", icon: "externaldrive.badge.timemachine") {
                    state.runBackupZotero()
                }
                WorkflowButton(title: "Enrich Metadata", icon: "wand.and.stars") {
                    state.runEnrichMetadata()
                }
                WorkflowButton(title: "Detect Duplicates", icon: "doc.on.doc") {
                    state.runDetectDuplicates()
                }
                WorkflowButton(title: "Plan Migration", icon: "list.bullet.rectangle") {
                    state.runPlanMigration()
                }
                WorkflowButton(title: "Dry Run Migration", icon: "play.circle") {
                    state.runDryRunMigration()
                }
            }

            Divider()

            VStack(alignment: .leading, spacing: 8) {
                Text("Apply Migration")
                    .font(.headline)
                Text("This changes Zotero collections/tags only. It does not move PDFs.")
                    .foregroundStyle(.secondary)
                Text("If Web API is used, Zotero Desktop may need data sync before changes are visible.")
                    .foregroundStyle(.secondary)
                Text("This should not delete notes, annotations, highlights, or attachments.")
                    .foregroundStyle(.secondary)
                if !state.zoteroVerification.writeAccess {
                    Text("Zotero API key write access is not verified. Use Settings > Accounts & API Keys before applying.")
                        .foregroundStyle(.red)
                }
                TextField("REPLACE MY ZOTERO COLLECTIONS", text: $applyConfirmation)
                    .textFieldStyle(.roundedBorder)

                HStack {
                    Button(role: .destructive) {
                        state.runApplyMigration()
                    } label: {
                        Label("Apply Migration", systemImage: "exclamationmark.triangle")
                    }
                    .disabled(
                        state.runner.isRunning
                        || applyConfirmation != ConfirmationKind.applyMigration.requiredText
                        || !state.zoteroVerification.writeAccess
                    )

                    Button(role: .destructive) {
                        confirm(.cleanupDeleteEmpty)
                    } label: {
                        Label("Cleanup Empty Old Collections", systemImage: "trash")
                    }
                    .disabled(state.runner.isRunning)
                }
            }
        }
    }
}
