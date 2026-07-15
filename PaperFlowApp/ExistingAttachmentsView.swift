import SwiftUI

struct ExistingAttachmentsView: View {
    @EnvironmentObject private var state: AppState
    let confirm: (ConfirmationKind) -> Void
    @State private var cleanupConfirmation = ""

    private var planState: WorkflowStepState {
        guard state.backend.localizeAttachmentCommands else {
            return .blocked("This option is unavailable. Open Advanced & Diagnostics in Settings.")
        }
        return state.workflowStepState(
            commandFragment: "zotero plan-localize-attachments",
            outputs: ["data/localize_attachments_plan.json", "data/localize_attachments_report.md"]
        )
    }

    private var applyState: WorkflowStepState {
        guard state.backend.localizeAttachmentCommands else {
            return .blocked("This option is unavailable. Open Advanced & Diagnostics in Settings.")
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
                SectionTitle("Move Existing PDFs")
                Text("기존 Zotero PDF를 로컬 library로 옮기면서 메모와 읽기 기록을 보존합니다.")
                    .foregroundStyle(PaperFlowTheme.muted)
            }

            SurfaceSection(
                title: "Move workflow",
                subtitle: "Plan → Apply → Verify 순서가 충족되지 않으면 다음 단계는 실행되지 않습니다."
            ) {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 12)], spacing: 12) {
                    WorkflowStepCard(number: 1, title: "Plan Stored PDFs", detail: "옮길 PDF와 보존할 읽기 기록 확인", icon: "map", state: planState, actionTitle: "Build Plan", action: state.runPlanLocalizeAttachments)
                    WorkflowStepCard(number: 2, title: "Move PDFs", detail: "PDF를 복사하고 Zotero에서 열 수 있는지 확인", icon: "arrow.down.doc", state: applyState, actionTitle: "Review & Apply") {
                        confirm(.localizeAttachments)
                    }
                    WorkflowStepCard(number: 3, title: "Verify Attachments", detail: "새 PDF와 기존 읽기 기록이 정상인지 확인", icon: "checkmark.seal", state: verifyState, actionTitle: "Verify", action: state.runVerifyLocalizedAttachments)
                }
            }

            SurfaceSection(
                title: "Stored attachment cleanup",
                subtitle: "검증에 성공한 뒤, 보존할 읽기 기록이 없는 경우에만 사용합니다."
            ) {
                WorkflowStateBadge(state: cleanupState)
                WarningBox(text: "새 PDF가 정상적으로 열리는지 확인된 경우에만 기존 복사본을 정리합니다. 메모, 하이라이트 또는 주석이 있으면 삭제하지 않습니다.")
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
