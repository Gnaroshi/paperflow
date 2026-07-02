import SwiftUI

struct ExistingAttachmentsView: View {
    @EnvironmentObject private var state: AppState
    let confirm: (ConfirmationKind) -> Void
    @State private var cleanupConfirmation = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionTitle("Existing Attachments")
            Text("Migrate existing stored Zotero PDFs into local linked PDFs while preserving notes, highlights, underlines, annotations, and child notes.")
                .foregroundStyle(PaperFlowTheme.muted)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 240), spacing: 12)], spacing: 12) {
                WorkflowButton(title: "Plan Localize Stored PDFs", icon: "map") {
                    state.runPlanLocalizeAttachments()
                }
                .disabled(!state.backend.localizeAttachmentCommands || state.runner.isRunning)

                WorkflowButton(title: "Verify Localized Attachments", icon: "checkmark.seal") {
                    state.runVerifyLocalizedAttachments()
                }
                .disabled(!state.backend.localizeAttachmentCommands || state.runner.isRunning)
            }

            Divider()

            VStack(alignment: .leading, spacing: 8) {
                Text("Danger zone")
                    .font(.headline)
                Text("Cleanup should run only after the verify report succeeded.")
                    .foregroundStyle(PaperFlowTheme.muted)
                Text("Cleanup must never delete attachments with notes, highlights, or annotations unless explicitly reviewed.")
                    .foregroundStyle(PaperFlowTheme.muted)
                TextField("DELETE OLD STORED PDF ATTACHMENTS", text: $cleanupConfirmation)
                    .paperFlowTextInput()

                HStack {
                    Button(role: .destructive) {
                        confirm(.localizeAttachments)
                    } label: {
                        Label("Apply Localize Stored PDFs", systemImage: "arrow.down.doc")
                    }
                    .disabled(!state.backend.localizeAttachmentCommands || state.runner.isRunning)

                    Button(role: .destructive) {
                        state.runCleanupStoredAttachments()
                    } label: {
                        Label("Cleanup Old Stored Attachments", systemImage: "trash")
                    }
                    .disabled(
                        !state.backend.localizeAttachmentCommands
                        || state.runner.isRunning
                        || cleanupConfirmation != ConfirmationKind.cleanupStoredAttachments.requiredText
                    )
                }
            }
        }
    }
}
