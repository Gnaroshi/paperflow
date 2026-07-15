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
                Text("각 단계는 필요한 입력 파일과 결과 파일을 검사합니다. 이전 단계가 실패하면 종속 단계는 실행되지 않습니다.")
                    .foregroundStyle(PaperFlowTheme.muted)
            }

            SyncWarningBox()

            SurfaceSection(
                title: "Migration workflow",
                subtitle: "완료된 단계도 입력 파일이 더 새로우면 Update required로 표시됩니다."
            ) {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 12)], spacing: 12) {
                    WorkflowStepCard(
                        number: 1,
                        title: "Backup Zotero",
                        detail: "변경 전 items, collections, tags, memberships snapshot 생성",
                        icon: "externaldrive.badge.timemachine",
                        state: backupState,
                        actionTitle: "Run Backup",
                        action: state.runBackupZotero
                    )
                    WorkflowStepCard(
                        number: 2,
                        title: "Enrich Metadata",
                        detail: "스캔 JSONL에서 DOI, arXiv ID, metadata quality 보강",
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
                        detail: "taxonomy 기준 collection/tag migration plan 생성",
                        icon: "list.bullet.rectangle",
                        state: planState,
                        actionTitle: "Build Plan",
                        action: state.runPlanMigration
                    )
                    WorkflowStepCard(
                        number: 5,
                        title: "Dry Run Migration",
                        detail: "Zotero write 없이 정확한 API operation preview 생성",
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
                Text("Web API로 적용한 변경은 Zotero Desktop data sync 후 표시될 수 있습니다.")
                    .font(.callout)
                    .foregroundStyle(PaperFlowTheme.muted)
                Label(
                    "Backup과 현재 plan의 dry-run preview가 확인된 경우에만 실행됩니다. Apply log와 data/backups는 rollback 근거로 보존됩니다.",
                    systemImage: "checkmark.shield"
                )
                .font(.caption)
                .foregroundStyle(PaperFlowTheme.muted)
                FlowLayout(spacing: 8) {
                    Button(role: .destructive) {
                        state.runApplyMigration()
                    } label: {
                        Label("Apply Reviewed Migration", systemImage: "exclamationmark.triangle")
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
