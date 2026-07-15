import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionTitle("Library")
            heroStatusCard

            if reviewItemCount == 0 {
                SurfaceSection(title: "Review") {
                    Label("Nothing needs your attention", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(PaperFlowTheme.mint)
                }
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 158), spacing: 10)], spacing: 10) {
                    if state.dashboard.duplicateCandidates > 0 {
                        MetricTile(title: "Duplicates", value: "\(state.dashboard.duplicateCandidates)", tint: .purple)
                    }
                    if state.dashboard.missingMetadataItems > 0 {
                        MetricTile(title: "Missing metadata", value: "\(state.dashboard.missingMetadataItems)", tint: .orange)
                    }
                    if state.dashboard.missingAbstractItems > 0 {
                        MetricTile(title: "Missing abstracts", value: "\(state.dashboard.missingAbstractItems)", tint: .pink)
                    }
                    if state.dashboard.lowConfidenceItems > 0 {
                        MetricTile(title: "Needs classification", value: "\(state.dashboard.lowConfidenceItems)", tint: .mint)
                    }
                }
            }

            if state.showTechnicalDetails {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 280), spacing: 10)], spacing: 10) {
                    StatusCard(title: "Migration", rows: [
                        ("Latest", state.dashboard.latestMigrationStatus),
                        ("Apply", state.dashboard.latestApplyStatus),
                        ("Audit", state.dashboard.latestMigrationAuditStatus)
                    ])
                    StatusCard(title: "Cleanup", rows: [
                        ("Cleanup", state.dashboard.latestCleanupStatus),
                        ("Stored PDFs", state.dashboard.latestStoredPDFLocalizationStatus),
                        ("Last ingest", state.vaultStatus.lastIngest)
                    ])
                }
            }

            if state.geminiUsage.failedRateLimitCalls > 0 {
                WarningBox(text: "Optional AI assistance is temporarily unavailable. PaperFlow can continue without it.")
            }
        }
    }

    private var reviewItemCount: Int {
        state.dashboard.duplicateCandidates
            + state.dashboard.missingMetadataItems
            + state.dashboard.missingAbstractItems
            + state.dashboard.lowConfidenceItems
    }

    private var heroStatusCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Paper library", systemImage: "doc.text.magnifyingglass")
                .font(.headline)
            HStack {
                Label(state.vaultStatus.exists ? "PDF library ready" : "Choose a PDF library", systemImage: state.vaultStatus.exists ? "externaldrive.fill" : "externaldrive.badge.xmark")
                Spacer()
                Text(state.vaultStatus.exists ? "\(state.vaultStatus.pdfCount) PDFs · \(state.vaultStatus.totalSizeLabel)" : "로컬 PDF 저장 폴더 없음")
                    .foregroundStyle(PaperFlowTheme.muted)
            }
            .font(.callout)
            Label(
                state.zoteroVerification.writeAccess ? "Zotero is connected" : "Zotero setup is required before Apply",
                systemImage: state.zoteroVerification.writeAccess ? "checkmark.circle.fill" : "exclamationmark.circle"
            )
            .font(.callout)
            .foregroundStyle(state.zoteroVerification.writeAccess ? PaperFlowTheme.mint : PaperFlowTheme.amber)
            HStack {
                if state.vaultStatus.exists {
                    Button("Open PDF Library") { state.openVault() }
                } else {
                    Button("Choose PDF Library") { state.chooseVaultDirectory() }
                }
                if !state.zoteroVerification.writeAccess {
                    Button("Set Up Zotero") { state.selectedSection = .settings }
                }
                Button("Refresh") { state.refreshStatus() }
            }
            .buttonStyle(.bordered)
        }
        .padding(16)
        .frame(maxWidth: .infinity, minHeight: 168, alignment: .topLeading)
        .paperFlowCard(tint: PaperFlowTheme.mint, radius: 18, emphasize: true)
    }

}

private struct MetricTile: View {
    let title: String
    let value: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption)
                .foregroundStyle(PaperFlowTheme.muted)
            Text(value)
                .font(.title2)
                .fontWeight(.semibold)
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 78, alignment: .leading)
        .paperFlowCard(tint: tint, radius: 14)
    }
}

private struct StatusCard: View {
    let title: String
    let rows: [(String, String)]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
            ForEach(rows, id: \.0) { row in
                HStack(alignment: .firstTextBaseline) {
                    Text(row.0)
                        .font(.caption)
                        .foregroundStyle(PaperFlowTheme.muted)
                        .frame(width: 78, alignment: .leading)
                    Text(row.1)
                        .font(.caption)
                        .lineLimit(2)
                        .truncationMode(.middle)
                        .textSelection(.enabled)
                    Spacer(minLength: 0)
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 126, alignment: .topLeading)
        .paperFlowCard(tint: PaperFlowTheme.lilac, radius: 14)
    }
}
