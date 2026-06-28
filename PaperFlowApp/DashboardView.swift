import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SectionTitle("Dashboard")

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 12)], spacing: 12) {
                InfoTile(title: "Project", value: state.projectPath)
                InfoTile(title: "Zotero API", value: state.zoteroVerification.verified ? "Verified: \(state.zoteroUserID)" : state.zoteroConnectionStatus)
                InfoTile(title: "Zotero Write Access", value: state.zoteroVerification.writeAccessLabel)
                InfoTile(title: "Gemini", value: "\(state.geminiConnectionStatus) • \(state.selectedGeminiModel)")
                InfoTile(title: "Gemini Usage", value: "\(state.geminiUsage.quotaStatus), \(state.geminiUsage.totalTokens) tokens today")
                InfoTile(title: "Local Vault", value: state.vaultStatus.exists ? "\(state.vaultStatus.pdfCount) PDFs, \(state.vaultStatus.totalSizeLabel)" : "Not initialized")
                InfoTile(title: "Source Items", value: "\(state.dashboard.sourceItems)")
                InfoTile(title: "Planned Items", value: "\(state.dashboard.plannedItems)")
                InfoTile(title: "Duplicate Candidates", value: "\(state.dashboard.duplicateCandidates)")
                InfoTile(title: "Missing Metadata", value: "\(state.dashboard.missingMetadataItems)")
                InfoTile(title: "Missing Abstracts", value: "\(state.dashboard.missingAbstractItems)")
                InfoTile(title: "Low Confidence", value: "\(state.dashboard.lowConfidenceItems)")
                InfoTile(title: "Non-paper", value: "\(state.dashboard.nonPaperItems)")
                InfoTile(title: "Item Updates", value: "\(state.dashboard.itemUpdates)")
                InfoTile(title: "Collections to Create", value: "\(state.dashboard.collectionsToCreate)")
            }

            VStack(alignment: .leading, spacing: 8) {
                StatusLine(label: "Latest migration", value: state.dashboard.latestMigrationStatus)
                StatusLine(label: "Latest apply", value: state.dashboard.latestApplyStatus)
                StatusLine(label: "Latest cleanup", value: state.dashboard.latestCleanupStatus)
                StatusLine(label: "Migration audit", value: state.dashboard.latestMigrationAuditStatus)
                StatusLine(label: "Stored PDF localization", value: state.dashboard.latestStoredPDFLocalizationStatus)
                StatusLine(label: "Last ingest", value: state.vaultStatus.lastIngest)
            }

            if state.geminiUsage.failedRateLimitCalls > 0 {
                WarningBox(text: "Gemini Flash is currently rate-limited. Try later or reduce batch size.")
            }

            SyncWarningBox()
        }
    }
}

struct SyncWarningBox: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Zotero sync warning")
                .font(.headline)
            Text("Data sync and file sync are separate.")
            Text("For a local-only PDF workflow, file sync should be off so PDFs do not consume Zotero Storage.")
            Text("If Web API is used, Zotero Desktop may need data sync before changes are visible.")
            Text("Turning off file sync prevents PDF attachments from consuming Zotero Storage.")
        }
        .font(.callout)
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.yellow.opacity(0.14))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}
