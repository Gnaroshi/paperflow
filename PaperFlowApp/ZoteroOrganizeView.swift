import SwiftUI

struct ZoteroOrganizeView: View {
    @EnvironmentObject private var state: AppState
    let confirm: (ConfirmationKind) -> Void

    private var backupState: WorkflowStepState {
        state.workflowStepState(
            commandFragment: "zotero backup",
            outputs: ["data/backups"]
        )
    }

    private var enrichState: WorkflowStepState {
        state.workflowStepState(
            commandFragment: "zotero enrich-metadata",
            prerequisiteGroups: [["data/zotero_items.jsonl"]],
            outputs: ["data/zotero_items_enriched.jsonl"]
        )
    }

    private var duplicateState: WorkflowStepState {
        state.workflowStepState(
            commandFragment: "zotero detect-duplicates",
            prerequisiteGroups: [["data/zotero_items_enriched.jsonl", "data/zotero_items.jsonl"]],
            outputs: ["data/dedupe_plan.json", "data/dedupe_report.md"]
        )
    }

    private var planState: WorkflowStepState {
        state.workflowStepState(
            commandFragment: "zotero plan-migration",
            prerequisiteGroups: [["data/zotero_items_enriched.jsonl", "data/zotero_items.jsonl"]],
            outputs: ["data/migration_plan.json"]
        )
    }

    private var previewState: WorkflowStepState {
        state.workflowStepState(
            commandFragment: "zotero dry-run-migration",
            prerequisiteGroups: [["data/migration_plan.json"]],
            outputs: ["data/apply_preview.json", "data/apply_preview.md"]
        )
    }

    private var applyState: WorkflowStepState {
        if state.runner.isRunning {
            if state.runner.currentCommand.contains("zotero apply-migration") {
                return .running
            }
            return .blocked("Another PaperFlow command is running")
        }
        if let blocker = state.migrationApplyBlocker {
            return .blocked(blocker)
        }
        return .ready
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 6) {
                SectionTitle("Zotero Organize")
                Text("위에서 아래 순서로 진행합니다. 완료되지 않은 단계가 있으면 다음 단계는 자동으로 잠깁니다.")
                    .foregroundStyle(PaperFlowTheme.muted)
            }

            SurfaceSection(
                title: "Migration workflow",
                subtitle: "Library가 바뀌면 필요한 단계만 다시 실행하도록 안내합니다."
            ) {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 12)], spacing: 12) {
                    WorkflowStepCard(
                        number: 1,
                        title: "Backup Zotero",
                        detail: "변경 전 library 상태를 안전하게 보관",
                        icon: "externaldrive.badge.timemachine",
                        state: backupState,
                        actionTitle: "Run Backup",
                        action: state.runBackupZotero
                    )
                    WorkflowStepCard(
                        number: 2,
                        title: "Enrich Metadata",
                        detail: "논문 식별자와 누락된 서지정보 확인",
                        icon: "wand.and.stars",
                        state: enrichState,
                        actionTitle: "Run Enrichment",
                        action: state.runEnrichMetadata
                    )
                    WorkflowStepCard(
                        number: 3,
                        title: "Detect Duplicates",
                        detail: "reading work를 우선 보존하는 duplicate review plan 생성",
                        icon: "doc.on.doc",
                        state: duplicateState,
                        actionTitle: "Detect Duplicates",
                        action: state.runDetectDuplicates
                    )
                    WorkflowStepCard(
                        number: 4,
                        title: "Plan Migration",
                        detail: "collection과 tag 변경안을 검토 가능한 형태로 준비",
                        icon: "list.bullet.rectangle",
                        state: planState,
                        actionTitle: "Build Plan",
                        action: state.runPlanMigration
                    )
                    WorkflowStepCard(
                        number: 5,
                        title: "Preview Migration",
                        detail: "Zotero를 변경하지 않고 최종 결과 미리 확인",
                        icon: "play.circle",
                        state: previewState,
                        actionTitle: "Run Preview",
                        action: state.runDryRunMigration
                    )
                }
            }

            SurfaceSection(
                title: "Apply migration",
                subtitle: "Collection/tag만 변경하며 PDF, note, annotation, highlight, attachment는 삭제하지 않습니다."
            ) {
                WorkflowStateBadge(state: applyState)
                if let detail = applyState.detail {
                    Label(detail, systemImage: "lock.fill")
                        .font(.caption)
                        .foregroundStyle(PaperFlowTheme.rose)
                }
                Label(
                    "현재 backup과 preview가 확인된 경우에만 실행됩니다. 문제가 생기면 이전 상태로 복구할 수 있습니다.",
                    systemImage: "checkmark.shield"
                )
                .font(.caption)
                .foregroundStyle(PaperFlowTheme.muted)
                FlowLayout(spacing: 8) {
                    Button {
                        state.runApplyMigration()
                    } label: {
                        Label("Apply Reviewed Migration", systemImage: "checkmark.circle")
                    }
                    .disabled(!applyState.allowsExecution)

                    Button(role: .destructive) {
                        confirm(.cleanupDeleteEmpty)
                    } label: {
                        Label("Cleanup Empty Old Collections", systemImage: "trash")
                    }
                    .disabled(
                        state.runner.isRunning
                        || !state.artifactExists("data/cleanup_report.md")
                    )
                }
            }
        }
    }
}
