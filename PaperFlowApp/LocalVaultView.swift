import SwiftUI

struct LocalVaultView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: PaperFlowSpacing.md) {
            SectionTitle("Storage & Sources")
            Text("새 PDF의 write destination, 기존 Zotero attachment source, Downloads import source를 구분해 관리합니다.")
                .foregroundStyle(PaperFlowTheme.muted)

            SurfaceSection(
                title: "PaperFlow Managed Vault",
                subtitle: "새 PDF를 복사·정리하는 기본 목적지입니다. Zotero에는 이 파일의 linked attachment를 생성합니다."
            ) {
                locationHeader(
                    title: "Active write destination",
                    path: state.vaultPath,
                    summary: state.vaultStatus.exists
                        ? "\(state.vaultStatus.pdfCount) PDFs · \(state.vaultStatus.totalSizeLabel)"
                        : "Not initialized",
                    symbol: "externaldrive.fill",
                    color: state.vaultStatus.exists ? PaperFlowTheme.mint : PaperFlowTheme.amber
                )
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: PaperFlowSpacing.xs)], spacing: PaperFlowSpacing.xs) {
                    InfoTile(title: "Storage mode", value: "linked-local")
                    InfoTile(title: "Zotero Storage upload", value: "Never")
                    InfoTile(title: "Last ingest", value: state.vaultStatus.lastIngest)
                }
                Label(
                    "Zotero Linked Attachment Base Directory는 하나이므로 기본 write destination도 하나를 유지합니다. 다른 폴더는 import source로 등록합니다.",
                    systemImage: "info.circle"
                )
                .font(.caption)
                .foregroundStyle(PaperFlowTheme.muted)
                SettingsActionBar {
                    Button("Init Vault") { state.runVaultInit() }
                        .disabled(!state.backend.vaultCommands || state.runner.isRunning)
                    Button("Choose Destination") { state.chooseVaultDirectory() }
                    Button("Plan Vault Paths") { state.runVaultPlanPaths() }
                        .disabled(
                            !state.backend.vaultCommands
                            || state.runner.isRunning
                            || !state.artifactExists("data/migration_plan.json")
                        )
                    Button("Open Vault") { state.openVault() }
                    Button("Refresh") { state.refreshStatus() }
                }
                if !state.artifactExists("data/migration_plan.json") {
                    Label("Plan Vault Paths requires data/migration_plan.json. Run Zotero Organize → Plan Migration first.", systemImage: "lock.fill")
                        .font(.caption)
                        .foregroundStyle(PaperFlowTheme.amber)
                }
                SettingsToggleRow(
                    "Base directory configured",
                    detail: "Zotero → Settings → Advanced → Files and Folders에서 위 경로를 선택",
                    isOn: $state.linkedAttachmentInstructionsShown
                )
            }

            SurfaceSection(
                title: "Existing Zotero Storage",
                subtitle: "Zotero가 관리하는 stored attachment 영역입니다. PaperFlow는 이 폴더를 직접 수정하지 않습니다."
            ) {
                locationHeader(
                    title: "Zotero managed · read-only source",
                    path: state.zoteroStorageStatus.path,
                    summary: state.zoteroStorageStatus.summary,
                    symbol: "books.vertical.fill",
                    color: PaperFlowTheme.sky
                )
                WarningBox(text: "Stored PDF를 local vault로 옮길 때는 Existing Attachments의 Plan → Apply → Verify workflow를 사용합니다. 기존 attachment, note, highlight, annotation은 자동 삭제하지 않습니다.")
                SettingsActionBar {
                    Button("Open Zotero Storage") { state.openFolder(path: state.zoteroStoragePath) }
                        .disabled(!state.zoteroStorageStatus.exists)
                    Button("Choose Location") { state.chooseZoteroStorageDirectory() }
                    Button("Index Zotero Attachments") { state.runIndexZoteroStorage() }
                        .disabled(state.runner.isRunning)
                    Button("Plan Localization") { state.runPlanLocalizeAttachments() }
                        .disabled(state.runner.isRunning || !state.backend.localizeAttachmentCommands)
                }
            }

            SurfaceSection(
                title: "Import Sources",
                subtitle: "Downloads나 다른 폴더는 임시 source입니다. 새 논문은 vault에 복사한 뒤 Zotero item과 linked attachment로 추가합니다."
            ) {
                locationHeader(
                    title: "Downloads",
                    path: state.downloadsStatus.path,
                    summary: state.downloadsStatus.summary,
                    symbol: "arrow.down.circle.fill",
                    color: PaperFlowTheme.lilac
                )
                Label(
                    "Scan은 dry-run이며 파일을 복사하거나 Zotero에 쓰지 않습니다. Local Folder Import의 Apply Import에서만 vault copy와 Zotero write가 실행됩니다.",
                    systemImage: "checkmark.shield"
                )
                .font(.caption)
                .foregroundStyle(PaperFlowTheme.muted)
                SettingsActionBar {
                    Button("Scan Downloads") { state.scanDownloadsForImport() }
                        .disabled(state.runner.isRunning || !state.downloadsStatus.exists)
                    Button("Open Import Workflow") { state.openDownloadsImport() }
                    Button("Choose Another Folder") {
                        state.chooseLocalImportFolder()
                        state.selectedSection = .localFolderImport
                    }
                    Button("Open Downloads") { state.openFolder(path: state.downloadsStatus.path) }
                        .disabled(!state.downloadsStatus.exists)
                }
            }

            if !state.backend.vaultCommands {
                WarningBox(text: "Backend missing: paperflow vault init / plan-paths.")
            }
        }
    }

    private func locationHeader(
        title: String,
        path: String,
        summary: String,
        symbol: String,
        color: Color
    ) -> some View {
        HStack(alignment: .top, spacing: PaperFlowSpacing.sm) {
            Image(systemName: symbol)
                .font(.title3)
                .foregroundStyle(color)
                .frame(width: 28)
            VStack(alignment: .leading, spacing: PaperFlowSpacing.xxs) {
                Text(title)
                    .font(.callout.weight(.semibold))
                Text(path)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(PaperFlowTheme.muted)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: PaperFlowSpacing.sm)
            Text(summary)
                .font(.caption.weight(.medium))
                .foregroundStyle(color)
                .multilineTextAlignment(.trailing)
        }
        .padding(.vertical, PaperFlowSpacing.xxs)
    }
}
