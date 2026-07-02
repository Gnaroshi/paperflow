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
                ReportButton(title: "Migration Report") { state.openReport("migration_report.md") }
                ReportButton(title: "Apply Preview") { state.openReport("apply_preview.md") }
                ReportButton(title: "Cleanup Report") { state.openReport("cleanup_report.md") }
                ReportButton(title: "Dedupe Report") { state.openReport("dedupe_report.md") }
                ReportButton(title: "Abstract Repair Report") { state.openReport("abstract_repair_report.md") }
                ReportButton(title: "Metadata Repair Report") { state.openReport("metadata_repair_report.md") }
                ReportButton(title: "Duplicate Resolution Report") { state.openReport("duplicate_resolution_report.md") }
                ReportButton(title: "Migration Audit") { state.openReport("migration_audit.md") }
                ReportButton(title: "Local Scan Report") { state.openReport("local_scan_report.md") }
                ReportButton(title: "Local Match Report") { state.openReport("local_zotero_match_report.md") }
                ReportButton(title: "Local Classification Report") { state.openReport("local_classification_report.md") }
                ReportButton(title: "Local Import Report") { state.openReport("local_import_report.md") }
                ReportButton(title: "Local Import Audit") { state.openReport("local_import_audit.md") }
                ReportButton(title: "Localize Attachments Report") { state.openReport("localize_attachments_report.md") }
                ReportButton(title: "Localize Verify Report") { state.openReport("localize_verify_report.md") }
                ReportButton(title: "Latest Apply Log") { state.openLatestApplyLog() }
                ReportButton(title: "Reports Folder") { state.openReportsFolder() }
            }
        }
    }
}

struct ReportButton: View {
    let title: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Label(title, systemImage: "doc.text")
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .buttonStyle(.bordered)
    }
}
