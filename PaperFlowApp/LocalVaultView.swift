import SwiftUI

struct LocalVaultView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: PaperFlowSpacing.md) {
            SectionTitle("PDF Library")
            Text("새 PDF를 저장할 곳, 기존 Zotero PDF와 가져올 폴더를 관리합니다.")
                .foregroundStyle(PaperFlowTheme.muted)

            SurfaceSection(
                title: "PDF Library on This Mac",
                subtitle: "새 PDF를 보관하고 Zotero에서 바로 열 수 있도록 연결합니다."
            ) {
                locationHeader(
                    title: "Current PDF library",
                    path: state.vaultPath,
                    summary: state.vaultStatus.exists
                        ? "\(state.vaultStatus.pdfCount) PDFs · \(state.vaultStatus.totalSizeLabel)"
                        : "Not initialized",
                    symbol: "externaldrive.fill",
                    color: state.vaultStatus.exists ? PaperFlowTheme.mint : PaperFlowTheme.amber
                )
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: PaperFlowSpacing.xs)], spacing: PaperFlowSpacing.xs) {
                    InfoTile(title: "PDF location", value: "On this Mac")
                    InfoTile(title: "Cloud PDF upload", value: "Off")
                    InfoTile(title: "Last ingest", value: state.vaultStatus.lastIngest)
                }
                Label(
                    "새 PDF는 이 위치에 저장됩니다. 다른 폴더의 PDF는 Import에서 가져올 수 있습니다.",
                    systemImage: "info.circle"
                )
                .font(.caption)
                .foregroundStyle(PaperFlowTheme.muted)
                SettingsActionBar {
                    Button("Set Up Library") { state.runVaultInit() }
                        .disabled(!state.backend.vaultCommands || state.runner.isRunning)
                    Button("Choose Location") { state.chooseVaultDirectory() }
                    Button("Preview File Locations") { state.runVaultPlanPaths() }
                        .disabled(
                            !state.backend.vaultCommands
                            || state.runner.isRunning
                            || !state.artifactExists("data/migration_plan.json")
                        )
                    Button("Open PDF Library") { state.openVault() }
                    Button("Refresh") { state.refreshStatus() }
                }
                if !state.artifactExists("data/migration_plan.json") {
                    Label("파일 위치를 미리 보려면 Zotero Organize에서 Plan Migration을 먼저 실행하세요.", systemImage: "lock.fill")
                        .font(.caption)
                        .foregroundStyle(PaperFlowTheme.amber)
                }
                SettingsToggleRow(
                    "Zotero can open this location",
                    detail: "Zotero → Settings → Advanced → Files and Folders에서 위 경로를 선택",
                    isOn: $state.linkedAttachmentInstructionsShown
                )
            }

            SurfaceSection(
                title: "Existing Zotero PDFs",
                subtitle: "Zotero가 이미 관리하는 PDF입니다. PaperFlow는 원본을 직접 수정하지 않습니다."
            ) {
                locationHeader(
                    title: "Existing Zotero PDF location",
                    path: state.zoteroStorageStatus.path,
                    summary: state.zoteroStorageStatus.summary,
                    symbol: "books.vertical.fill",
                    color: PaperFlowTheme.sky
                )
                WarningBox(text: "기존 PDF를 옮길 때는 Move Existing PDFs의 Plan → Apply → Verify 순서를 사용합니다. 읽기 기록은 자동으로 삭제하지 않습니다.")
                SettingsActionBar {
                    Button("Open Zotero Storage") { state.openFolder(path: state.zoteroStoragePath) }
                        .disabled(!state.zoteroStorageStatus.exists)
                    Button("Choose Location") { state.chooseZoteroStorageDirectory() }
                    Button("Check Existing PDFs") { state.runIndexZoteroStorage() }
                        .disabled(state.runner.isRunning)
                    Button("Plan Move") { state.runPlanLocalizeAttachments() }
                        .disabled(state.runner.isRunning || !state.backend.localizeAttachmentCommands)
                }
            }

            SurfaceSection(
                title: "Import Folders",
                subtitle: "Downloads나 선택한 폴더에서 새 논문을 찾아 PDF library와 Zotero에 추가합니다."
            ) {
                locationHeader(
                    title: "Downloads",
                    path: state.downloadsStatus.path,
                    summary: state.downloadsStatus.summary,
                    symbol: "arrow.down.circle.fill",
                    color: PaperFlowTheme.lilac
                )
                Label(
                    "Scan은 원본과 Zotero를 변경하지 않습니다. Apply Import를 선택할 때만 논문을 추가합니다.",
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
                WarningBox(text: "Storage tools are unavailable. Open Advanced diagnostics in Settings for recovery details.")
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
                if state.showTechnicalDetails {
                    Text(path)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(PaperFlowTheme.muted)
                        .textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                }
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
