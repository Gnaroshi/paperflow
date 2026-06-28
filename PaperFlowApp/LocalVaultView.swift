import SwiftUI

struct LocalVaultView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionTitle("Local Vault")
            Text("PDFs live in the local PaperFlow vault to avoid Zotero Storage usage. Zotero keeps metadata, collections, tags, notes, and annotations.")
                .foregroundStyle(.secondary)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 240), spacing: 12)], spacing: 12) {
                InfoTile(title: "Vault path", value: state.vaultPath)
                InfoTile(title: "Exists", value: state.vaultStatus.exists ? "Yes" : "No")
                InfoTile(title: "Total PDF count", value: "\(state.vaultStatus.pdfCount)")
                InfoTile(title: "Total size", value: state.vaultStatus.totalSizeLabel)
                InfoTile(title: "Last ingest", value: state.vaultStatus.lastIngest)
                InfoTile(title: "Local storage mode", value: "linked-local only")
            }

            HStack {
                Button("Init Vault") { state.runVaultInit() }
                    .disabled(!state.backend.vaultCommands || state.runner.isRunning)
                Button("Plan Vault Paths") { state.runVaultPlanPaths() }
                    .disabled(!state.backend.vaultCommands || state.runner.isRunning)
                Button("Open Vault") { state.openVault() }
                Button("Refresh") { state.refreshVaultStatus() }
            }

            Toggle("I have reviewed Zotero linked attachment base directory instructions", isOn: $state.linkedAttachmentInstructionsShown)

            if !state.backend.vaultCommands {
                WarningBox(text: "Backend missing: paperflow vault init / plan-paths.")
            }
        }
    }
}
