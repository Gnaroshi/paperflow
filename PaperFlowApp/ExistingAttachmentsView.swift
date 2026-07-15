import SwiftUI

struct ExistingAttachmentsView: View {
    @EnvironmentObject private var state: AppState
    let confirm: (ConfirmationKind) -> Void
    @State private var cleanupConfirmation = ""

    private var planState: WorkflowStepState {
        guard state.backend.localizeAttachmentCommands else {
            return .blocked("Backend command missing")
        }
        return state.workflowStepState(
            commandFragment: "zotero plan-localize-attachments",
            outputs: ["data/localize_attachments_plan.json", "data/localize_attachments_report.md"]
        )
    }

    private var applyState: WorkflowStepState {
        guard state.backend.localizeAttachmentCommands else {
            return .blocked("Backend command missing")
        }
        guard state.zoteroVerification.writeAccess else {
            return .blocked("Verify Zotero write access in Settings")
        }
        return state.workflowStepState(
            commandFragment: "zotero apply-localize-attachments",
            prerequisiteGroups: [["data/localize_attachments_plan.json"]]
        )
    }

    private var verifyState: WorkflowStepState {
        guard state.hasGeneratedArtifact(prefix: "localize_apply_log_", suffix: ".json") else {
            return .blocked("Apply localization successfully before verification")
        }
        return state.workflowStepState(
            commandFragment: "zotero verify-localized-attachments",
            prerequisiteGroups: [["data/localize_attachments_plan.json"]],
            outputs: ["data/localize_verify_report.json", "data/localize_verify_report.md"]
        )
    }

    private var cleanupState: WorkflowStepState {
        state.workflowStepState(
            commandFragment: "zotero cleanup-stored-attachments",
            prerequisiteGroups: [
                ["data/localize_attachments_plan.json"],
                ["data/localize_verify_report.json"]
            ]
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 6) {
                SectionTitle("Existing Attachments")
                Text("Stored Zotero PDF를 local vault의 linked PDF로 전환하되 reading work와 원본 attachment를 보존합니다.")
                    .foregroundStyle(PaperFlowTheme.muted)
            }

            SurfaceSection(
                title: "Localization workflow",
                subtitle: "Plan → Apply → Verify 순서가 충족되지 않으면 다음 단계는 실행되지 않습니다."
            ) {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 12)], spacing: 12) {
                    WorkflowStepCard(number: 1, title: "Plan Stored PDFs", detail: "stored PDF와 annotation 안전성, vault destination 계획", icon: "map", state: planState, actionTitle: "Build Plan", action: state.runPlanLocalizeAttachments)
                    WorkflowStepCard(number: 2, title: "Apply Localization", detail: "vault copy와 checksum 확인 후 linked attachment 생성", icon: "arrow.down.doc", state: applyState, actionTitle: "Review & Apply") {
                        confirm(.localizeAttachments)
                    }
                    WorkflowStepCard(number: 3, title: "Verify Attachments", detail: "linked file, checksum, parent item, old stored file 확인", icon: "checkmark.seal", state: verifyState, actionTitle: "Verify", action: state.runVerifyLocalizedAttachments)
                }
            }

            SurfaceSection(
                title: "Stored attachment cleanup",
                subtitle: "검증 성공 후에만 사용합니다. reading work가 있는 attachment는 backend가 거부해야 합니다."
            ) {
                WorkflowStateBadge(state: cleanupState)
                WarningBox(text: "Stored attachment 삭제는 verify report가 성공했고 linked file/checksum이 확인된 경우에만 허용됩니다. Note, highlight, underline, annotation이 있으면 자동 삭제하지 않습니다.")
                TextField("DELETE OLD STORED PDF ATTACHMENTS", text: $cleanupConfirmation)
                    .paperFlowTextInput()
                Button(role: .destructive) {
                    state.runCleanupStoredAttachments()
                } label: {
                    Label("Cleanup Old Stored Attachments", systemImage: "trash")
                }
                .disabled(
                    cleanupConfirmation != ConfirmationKind.cleanupStoredAttachments.requiredText
                    || !cleanupState.allowsExecution
                )
            }
        }
    }
}
