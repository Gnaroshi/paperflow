import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                SectionTitle("Dashboard")
                Spacer()
                Picker("Gemini model", selection: $state.geminiModel) {
                    Text("2.5 Flash").tag("gemini-2.5-flash")
                    Text("2.5 Flash Lite").tag("gemini-2.5-flash-lite")
                    Text("2.0 Flash").tag("gemini-2.0-flash")
                    Text("Custom").tag("custom")
                }
                .labelsHidden()
                .frame(width: 210)
            }

            HStack(alignment: .top, spacing: 12) {
                heroStatusCard
                VStack(spacing: 12) {
                    compactStatus(title: "Zotero", value: state.zoteroVerification.verified ? "Verified" : "Unverified", detail: "Write: \(state.zoteroVerification.writeAccess ? "yes" : "no")", icon: "books.vertical")
                    compactStatus(title: "Gemini", value: state.geminiVerification.verified ? "Verified" : state.geminiConnectionStatus, detail: state.selectedGeminiModel, icon: "sparkles")
                }
                .frame(width: 240)
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 158), spacing: 10)], spacing: 10) {
                MetricTile(title: "Planned", value: "\(state.dashboard.plannedItems)", tint: .blue)
                MetricTile(title: "Duplicates", value: "\(state.dashboard.duplicateCandidates)", tint: .purple)
                MetricTile(title: "Missing metadata", value: "\(state.dashboard.missingMetadataItems)", tint: .orange)
                MetricTile(title: "Missing abstracts", value: "\(state.dashboard.missingAbstractItems)", tint: .pink)
                MetricTile(title: "Low confidence", value: "\(state.dashboard.lowConfidenceItems)", tint: .mint)
                MetricTile(title: "Non-paper", value: "\(state.dashboard.nonPaperItems)", tint: .gray)
                MetricTile(title: "Updates", value: "\(state.dashboard.itemUpdates)", tint: .indigo)
                MetricTile(title: "Collections", value: "\(state.dashboard.collectionsToCreate)", tint: .teal)
            }

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
                StatusCard(title: "Gemini quota", rows: [
                    ("Status", state.geminiUsage.quotaStatus),
                    ("Requests", "\(state.geminiUsage.requestCount)"),
                    ("Tokens", "\(state.geminiUsage.totalTokens)")
                ])
            }

            if state.geminiUsage.failedRateLimitCalls > 0 {
                WarningBox(text: "Gemini Flash is currently rate-limited. Try later or reduce batch size.")
            }

            SyncWarningBox()
        }
    }

    private var heroStatusCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("PaperFlow Local Library", systemImage: "doc.text.magnifyingglass")
                .font(.headline)
            Text(state.projectPath)
                .font(.system(.caption, design: .monospaced))
                .lineLimit(1)
                .truncationMode(.middle)
                .foregroundStyle(PaperFlowTheme.muted)
            HStack {
                Label(state.vaultStatus.exists ? "Vault ready" : "Vault missing", systemImage: state.vaultStatus.exists ? "externaldrive.fill" : "externaldrive.badge.xmark")
                Spacer()
                Text(state.vaultStatus.exists ? "\(state.vaultStatus.pdfCount) PDFs · \(state.vaultStatus.totalSizeLabel)" : "Init Vault 필요")
                    .foregroundStyle(PaperFlowTheme.muted)
            }
            .font(.callout)
            HStack {
                Button("Open Vault") { state.openVault() }
                Button("Open Reports") { state.openReportsFolder() }
                Button("Refresh") { state.refreshStatus() }
            }
            .buttonStyle(.bordered)
        }
        .padding(16)
        .frame(maxWidth: .infinity, minHeight: 168, alignment: .topLeading)
        .paperFlowCard(tint: PaperFlowTheme.mint, radius: 18, emphasize: true)
    }

    private func compactStatus(title: String, value: String, detail: String, icon: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: icon)
                .font(.caption)
                .foregroundStyle(PaperFlowTheme.muted)
            Text(value)
                .font(.headline)
            Text(detail)
                .font(.caption)
                .foregroundStyle(PaperFlowTheme.muted)
                .lineLimit(1)
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 78, alignment: .leading)
        .paperFlowCard(tint: icon == "sparkles" ? PaperFlowTheme.lilac : PaperFlowTheme.sky, radius: 14)
    }
}

struct SyncWarningBox: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Zotero sync warning")
                .font(.headline)
            Text("Data sync과 file sync는 별개입니다. 로컬 PDF workflow에서는 file sync를 꺼야 Zotero Storage 300MB 제한을 피할 수 있습니다.")
            Text("Web API로 migration을 apply했다면 Zotero Desktop에서 data sync가 필요할 수 있습니다.")
        }
        .font(.callout)
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .paperFlowCard(tint: PaperFlowTheme.amber, radius: 12)
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
