import SwiftUI

struct ReportsView: View {
    @EnvironmentObject private var state: AppState

    private var numbers: ReportNumbers {
        ReportParser.numbers(dataURL: state.dataURL)
    }

    private struct ReportDefinition: Identifiable {
        let title: String
        let file: String
        var id: String { file }
    }

    private var availableReports: [ReportDefinition] {
        [
            ReportDefinition(title: "Migration Report", file: "migration_report.md"),
            ReportDefinition(title: "Apply Preview", file: "apply_preview.md"),
            ReportDefinition(title: "Cleanup Report", file: "cleanup_report.md"),
            ReportDefinition(title: "Dedupe Report", file: "dedupe_report.md"),
            ReportDefinition(title: "Abstract Repair Report", file: "abstract_repair_report.md"),
            ReportDefinition(title: "Metadata Repair Report", file: "metadata_repair_report.md"),
            ReportDefinition(title: "Duplicate Resolution Report", file: "duplicate_resolution_report.md"),
            ReportDefinition(title: "Migration Audit", file: "migration_audit.md"),
            ReportDefinition(title: "Local Scan Report", file: "local_scan_report.md"),
            ReportDefinition(title: "Local Match Report", file: "local_zotero_match_report.md"),
            ReportDefinition(title: "Local Classification Report", file: "local_classification_report.md"),
            ReportDefinition(title: "Local Import Report", file: "local_import_report.md"),
            ReportDefinition(title: "Local Import Audit", file: "local_import_audit.md"),
            ReportDefinition(title: "Move Existing PDFs Report", file: "localize_attachments_report.md"),
            ReportDefinition(title: "PDF Verification Report", file: "localize_verify_report.md")
        ].filter { state.artifactExists("data/\($0.file)") }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionTitle("Reports")

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 210), spacing: 12)], spacing: 12) {
                if numbers.plannedItems > 0 {
                    InfoTile(title: "Planned items", value: "\(numbers.plannedItems)")
                }
                if numbers.duplicateCandidates > 0 {
                    InfoTile(title: "Duplicate candidates", value: "\(numbers.duplicateCandidates)")
                }
                if numbers.missingMetadata > 0 {
                    InfoTile(title: "Missing metadata", value: "\(numbers.missingMetadata)")
                }
                if numbers.missingAbstracts > 0 {
                    InfoTile(title: "Missing abstracts", value: "\(numbers.missingAbstracts)")
                }
                if state.showTechnicalDetails {
                    InfoTile(title: "Source items", value: "\(numbers.sourceItems)")
                    InfoTile(title: "Item updates", value: "\(numbers.itemUpdates)")
                    InfoTile(title: "Collections to create", value: "\(numbers.collectionsToCreate)")
                    InfoTile(title: "Old collections empty", value: "\(numbers.oldCollectionsWouldBeEmpty)")
                }
            }

            if availableReports.isEmpty && !state.hasGeneratedArtifact(prefix: "apply_log_", suffix: ".md") {
                SurfaceSection(title: "No reports yet") {
                    Text("Complete a Preview or Check Result action to create a report.")
                        .foregroundStyle(PaperFlowTheme.muted)
                }
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 230), spacing: 12)], spacing: 12) {
                    ForEach(availableReports) { report in
                        reportButton(report.title, file: report.file)
                    }
                    if state.hasGeneratedArtifact(prefix: "apply_log_", suffix: ".md") {
                        ReportButton(title: "Latest Apply Record", available: true, action: state.openLatestApplyLog)
                    }
                    if state.showTechnicalDetails {
                        ReportButton(title: "Reports Folder", available: true) { state.openReportsFolder() }
                    }
                }
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
