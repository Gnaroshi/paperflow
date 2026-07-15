import SwiftUI

struct ReportsView: View {
    @EnvironmentObject private var state: AppState

    private var numbers: ReportNumbers {
        ReportParser.numbers(dataURL: state.dataURL)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionTitle("Reports")

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 210), spacing: 12)], spacing: 12) {
                InfoTile(title: "Source items", value: "\(numbers.sourceItems)")
                InfoTile(title: "Planned items", value: "\(numbers.plannedItems)")
                InfoTile(title: "Duplicate candidates", value: "\(numbers.duplicateCandidates)")
                InfoTile(title: "Missing metadata", value: "\(numbers.missingMetadata)")
                InfoTile(title: "Missing abstracts", value: "\(numbers.missingAbstracts)")
                InfoTile(title: "Item updates", value: "\(numbers.itemUpdates)")
                InfoTile(title: "Collections to create", value: "\(numbers.collectionsToCreate)")
                InfoTile(title: "Old collections empty", value: "\(numbers.oldCollectionsWouldBeEmpty)")
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 230), spacing: 12)], spacing: 12) {
                reportButton("Migration Report", file: "migration_report.md")
                reportButton("Apply Preview", file: "apply_preview.md")
                reportButton("Cleanup Report", file: "cleanup_report.md")
                reportButton("Dedupe Report", file: "dedupe_report.md")
                reportButton("Abstract Repair Report", file: "abstract_repair_report.md")
                reportButton("Metadata Repair Report", file: "metadata_repair_report.md")
                reportButton("Duplicate Resolution Report", file: "duplicate_resolution_report.md")
                reportButton("Migration Audit", file: "migration_audit.md")
                reportButton("Local Scan Report", file: "local_scan_report.md")
                reportButton("Local Match Report", file: "local_zotero_match_report.md")
                reportButton("Local Classification Report", file: "local_classification_report.md")
                reportButton("Local Import Report", file: "local_import_report.md")
                reportButton("Local Import Audit", file: "local_import_audit.md")
                reportButton("Localize Attachments Report", file: "localize_attachments_report.md")
                reportButton("Localize Verify Report", file: "localize_verify_report.md")
                ReportButton(
                    title: "Latest Apply Log",
                    available: state.hasGeneratedArtifact(prefix: "apply_log_", suffix: ".md"),
                    action: state.openLatestApplyLog
                )
                ReportButton(title: "Reports Folder", available: true) { state.openReportsFolder() }
            }
        }
    }

    private func reportButton(_ title: String, file: String) -> some View {
        ReportButton(
            title: title,
            available: state.artifactExists("data/\(file)")
        ) {
            state.openReport(file)
        }
    }
}

struct ReportButton: View {
    let title: String
    let available: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: available ? "doc.text.fill" : "doc.text")
                Text(title)
                    .lineLimit(1)
                Spacer(minLength: 4)
                Text(available ? "Ready" : "Missing")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(available ? PaperFlowTheme.mint : PaperFlowTheme.faint)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .buttonStyle(.bordered)
        .disabled(!available)
    }
}
