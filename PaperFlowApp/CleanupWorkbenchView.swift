import AppKit
import SwiftUI

struct CleanupWorkbenchView: View {
    @EnvironmentObject private var state: AppState
    let confirm: (ConfirmationKind) -> Void
    @State private var data = CleanupWorkbenchData()
    @State private var explainQuery = ""
    @State private var selectedAbstractItemKey = ""
    @State private var selectedMetadataItemKey = ""
    @State private var approvedMetadataFields: [String: Set<String>] = [:]

    private var explainedItems: [CleanupWorkbenchItem] {
        ReportParser.explainItems(dataURL: state.dataURL, query: explainQuery)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            ViewThatFits(in: .horizontal) {
                HStack {
                    SectionTitle("Review & Cleanup")
                    Spacer()
                    Button("Refresh") { reload() }
                    Button("Check Library") { state.runMigrationAudit() }
                    Button("Review Duplicates") { state.runPlanDuplicateResolution() }
                }
                VStack(alignment: .leading, spacing: 10) {
                    SectionTitle("Review & Cleanup")
                    FlowLayout(spacing: 8) {
                        Button("Refresh") { reload() }
                        Button("Check Library") { state.runMigrationAudit() }
                        Button("Review Duplicates") { state.runPlanDuplicateResolution() }
                    }
                }
            }

            WarningBox(text: "Review comes first. This screen does not automatically delete papers, PDFs, notes, highlights, or annotations.")

            summaryTiles

            whereDidThisPaperGo

            TabView {
                MissingAbstractPane(
                    items: data.missingAbstract,
                    selectedItemKey: $selectedAbstractItemKey,
                    repairSelected: selectedAbstractRepair,
                    repairAllDryRun: state.runRepairAbstractsDryRun,
                    applySelected: selectedAbstractApply,
                    applyAll: { confirm(.applyAbstractRepairs) }
                )
                .tabItem { Text("Missing Abstract") }

                MissingMetadataPane(
                    items: data.missingMetadata,
                    selectedItemKey: $selectedMetadataItemKey,
                    approvedFields: $approvedMetadataFields,
                    repairSelected: selectedMetadataRepair,
                    repairAllDryRun: state.runRepairMetadataDryRun,
                    applySelected: selectedMetadataApply,
                    applyAll: { confirm(.applyMetadataRepairs) }
                )
                .tabItem { Text("Missing Metadata") }

                DuplicateCandidatesPane(groups: data.duplicateGroups)
                    .tabItem { Text("Duplicate Candidates") }

                CleanupItemList(title: "Low Confidence", items: data.lowConfidence)
                    .tabItem { Text("Low Confidence") }

                CleanupItemList(title: "Non-paper Items", items: data.nonPaper)
                    .tabItem { Text("Non-paper Items") }
            }
            .frame(minHeight: 620)
        }
        .onAppear { reload() }
        .onChange(of: state.runner.status) { status in
            if status != .running {
                reload()
            }
        }
    }

    private var summaryTiles: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 12)], spacing: 12) {
            if data.missingAbstract.count > 0 { InfoTile(title: "Missing Abstract", value: "\(data.missingAbstract.count)") }
            if data.missingMetadata.count > 0 { InfoTile(title: "Missing Metadata", value: "\(data.missingMetadata.count)") }
            if data.duplicateGroups.count > 0 { InfoTile(title: "Duplicate Groups", value: "\(data.duplicateGroups.count)") }
            if data.lowConfidence.count > 0 { InfoTile(title: "Low Confidence", value: "\(data.lowConfidence.count)") }
            if data.nonPaper.count > 0 { InfoTile(title: "Non-paper", value: "\(data.nonPaper.count)") }
            if data.missingAbstract.isEmpty && data.missingMetadata.isEmpty && data.duplicateGroups.isEmpty && data.lowConfidence.isEmpty && data.nonPaper.isEmpty {
                InfoTile(title: "Library review", value: "Nothing needs attention")
            }
        }
    }

    private var whereDidThisPaperGo: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Where did this paper go?")
                .font(.headline)
            ViewThatFits(in: .horizontal) {
                HStack {
                    explainField
                    explainButton
                }
                VStack(alignment: .leading, spacing: 8) {
                    explainField
                    explainButton
                }
            }
            ForEach(explainedItems.prefix(explainQuery.isEmpty ? 0 : 5)) { item in
                VStack(alignment: .leading, spacing: 6) {
                    ViewThatFits(in: .horizontal) {
                        HStack {
                            Text(item.title)
                                .fontWeight(.semibold)
                            Spacer()
                            if state.showTechnicalDetails { itemKey(item.itemKey) }
                        }
                        VStack(alignment: .leading, spacing: 4) {
                            Text(item.title)
                                .fontWeight(.semibold)
                            if state.showTechnicalDetails { itemKey(item.itemKey) }
                        }
                    }
                    WorkbenchFlowRow(label: "Before", values: item.currentCollections)
                    WorkbenchFlowRow(label: "After", values: item.plannedCollections)
                    WorkbenchFlowRow(label: "Tags", values: item.normalizedTags)
                    Text("Why: \(item.rationale)")
                        .foregroundStyle(PaperFlowTheme.muted)
                    FlowLayout(spacing: 8) {
                        Button("Open in Zotero") { openZoteroItem(item.itemKey) }
                        Button("Reveal PDF") { revealFirstPDF(item.localPDFPaths) }
                            .disabled(item.localPDFPaths.isEmpty)
                    }
                }
                .padding(10)
                .paperFlowCard(tint: PaperFlowTheme.sky, radius: 12)
            }
        }
    }

    private var explainField: some View {
        TextField(state.showTechnicalDetails ? "Search title, DOI, arXiv ID, or item key" : "Search title, DOI, or arXiv ID", text: $explainQuery)
            .paperFlowTextInput()
    }

    private var explainButton: some View {
        Button("Explain") {
            if let first = explainedItems.first {
                state.runExplainItem(first.itemKey)
            } else {
                state.invalidDropWarnings = ["No matching paper was found in the current review results."]
            }
        }
        .disabled(explainedItems.isEmpty)
    }

    private func itemKey(_ value: String) -> some View {
        Text(value)
            .font(.system(.caption, design: .monospaced))
            .foregroundStyle(PaperFlowTheme.muted)
    }

    private func reload() {
        data = ReportParser.cleanupWorkbenchData(dataURL: state.dataURL)
        for item in data.missingMetadata where approvedMetadataFields[item.itemKey] == nil {
            approvedMetadataFields[item.itemKey] = Set(item.metadataDiffs.map(\.field))
        }
    }

    private func selectedAbstractRepair() {
        guard !selectedAbstractItemKey.isEmpty else {
            state.invalidDropWarnings = ["Select an abstract item first."]
            return
        }
        state.runRepairAbstractDryRun(itemKey: selectedAbstractItemKey)
    }

    private func selectedAbstractApply() {
        guard !selectedAbstractItemKey.isEmpty else {
            state.invalidDropWarnings = ["Select an abstract item first."]
            return
        }
        confirm(.applySelectedAbstractRepair(selectedAbstractItemKey))
    }

    private func selectedMetadataRepair() {
        guard !selectedMetadataItemKey.isEmpty else {
            state.invalidDropWarnings = ["Select a metadata item first."]
            return
        }
        state.runRepairMetadataDryRun(itemKey: selectedMetadataItemKey)
    }

    private func selectedMetadataApply() {
        guard !selectedMetadataItemKey.isEmpty else {
            state.invalidDropWarnings = ["Select a metadata item first."]
            return
        }
        let availableFields = data.missingMetadata
            .first { $0.itemKey == selectedMetadataItemKey }?
            .metadataDiffs
            .map(\.field) ?? []
        let selectedFields = approvedMetadataFields[selectedMetadataItemKey, default: Set(availableFields)]
        let approvedFields = availableFields.filter { selectedFields.contains($0) }
        confirm(.applySelectedMetadataRepair(selectedMetadataItemKey, approvedFields))
    }
}

private struct MissingAbstractPane: View {
    @EnvironmentObject private var state: AppState
    let items: [CleanupWorkbenchItem]
    @Binding var selectedItemKey: String
    let repairSelected: () -> Void
    let repairAllDryRun: () -> Void
    let applySelected: () -> Void
    let applyAll: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Picker("Selected", selection: $selectedItemKey) {
                Text("None").tag("")
                ForEach(items) { item in
                    Text(state.showTechnicalDetails ? "\(item.title) (\(item.itemKey))" : item.title).tag(item.itemKey)
                }
            }
            .frame(maxWidth: 520)
            FlowLayout(spacing: 8) {
                Button("Repair Selected") { repairSelected() }
                Button("Repair All Dry Run") { repairAllDryRun() }
                Button("Apply Selected Repairs") { applySelected() }
                Button { applyAll() } label: {
                    Text("Apply All High-confidence")
                }
            }
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(items) { item in
                        CleanupItemCard(item: item) {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Abstract repair")
                                    .font(.headline)
                                Text("Before")
                                    .font(.caption)
                                    .foregroundStyle(PaperFlowTheme.muted)
                                Text(item.currentAbstract.isEmpty ? "Missing in Zotero" : item.currentAbstract)
                                    .lineLimit(5)
                                    .textSelection(.enabled)
                                Text("After")
                                    .font(.caption)
                                    .foregroundStyle(PaperFlowTheme.muted)
                                Text(item.proposedAbstract.isEmpty ? "No proposed abstract yet. Run Repair All Dry Run." : item.proposedAbstract)
                                    .lineLimit(8)
                                    .textSelection(.enabled)
                                StatusLine(label: "Evidence source", value: item.abstractEvidenceSource.isEmpty ? "not planned" : item.abstractEvidenceSource)
                                StatusLine(label: "Repair confidence", value: String(format: "%.2f", item.abstractRepairConfidence))
                            }
                        }
                    }
                }
            }
        }
        .padding(.top, 12)
    }
}

private struct MissingMetadataPane: View {
    @EnvironmentObject private var state: AppState
    let items: [CleanupWorkbenchItem]
    @Binding var selectedItemKey: String
    @Binding var approvedFields: [String: Set<String>]
    let repairSelected: () -> Void
    let repairAllDryRun: () -> Void
    let applySelected: () -> Void
    let applyAll: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Picker("Selected", selection: $selectedItemKey) {
                Text("None").tag("")
                ForEach(items) { item in
                    Text(state.showTechnicalDetails ? "\(item.title) (\(item.itemKey))" : item.title).tag(item.itemKey)
                }
            }
            .frame(maxWidth: 520)
            FlowLayout(spacing: 8) {
                Button("Repair Selected") { repairSelected() }
                Button("Repair All Dry Run") { repairAllDryRun() }
                Button("Apply Selected Repairs") { applySelected() }
                Button { applyAll() } label: {
                    Text("Apply All Approved")
                }
            }
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(items) { item in
                        CleanupItemCard(item: item) {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Field-level diffs")
                                    .font(.headline)
                                if item.metadataDiffs.isEmpty {
                                    Text("No repair proposal yet. Run Repair All Dry Run.")
                                        .foregroundStyle(PaperFlowTheme.muted)
                                } else {
                                    ForEach(item.metadataDiffs) { diff in
                                        HStack(alignment: .top) {
                                            Text(diff.field)
                                                .frame(width: 150, alignment: .leading)
                                                .fontWeight(.medium)
                                            VStack(alignment: .leading, spacing: 3) {
                                                Text("Before: \(diff.before.isEmpty ? "(empty)" : diff.before)")
                                                    .foregroundStyle(PaperFlowTheme.muted)
                                                Text("After: \(diff.after)")
                                            }
                                            Toggle(
                                                "Approve",
                                                isOn: Binding(
                                                    get: {
                                                        approvedFields[item.itemKey, default: Set(item.metadataDiffs.map(\.field))]
                                                            .contains(diff.field)
                                                    },
                                                    set: { enabled in
                                                        var fields = approvedFields[item.itemKey, default: Set(item.metadataDiffs.map(\.field))]
                                                        if enabled {
                                                            fields.insert(diff.field)
                                                        } else {
                                                            fields.remove(diff.field)
                                                        }
                                                        approvedFields[item.itemKey] = fields
                                                    }
                                                )
                                            )
                                        }
                                    }
                                    Text("Only approved fields will be changed.")
                                        .font(.caption)
                                        .foregroundStyle(PaperFlowTheme.muted)
                                }
                            }
                        }
                    }
                }
            }
        }
        .padding(.top, 12)
    }
}

private struct DuplicateCandidatesPane: View {
    @EnvironmentObject private var state: AppState
    let groups: [DuplicateWorkbenchGroup]

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                ForEach(groups) { group in
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(alignment: .firstTextBaseline) {
                            Text(group.normalizedTitle)
                                .font(.headline)
                            Spacer()
                            Text(group.matchType)
                                .font(.caption)
                                .foregroundStyle(PaperFlowTheme.muted)
                        }
                        if state.showTechnicalDetails {
                            StatusLine(label: "Canonical item key", value: group.canonicalItemKey)
                        }
                        StatusLine(label: "Canonical reason", value: group.canonicalReason.isEmpty ? "(not provided)" : group.canonicalReason)
                        StatusLine(label: "Recommended", value: group.recommendedAction)
                        if group.metadataMergeSuggested {
                            WarningBox(text: state.showTechnicalDetails
                                ? "Metadata merge suggested from \(group.suggestedMetadataSourceItemKey). Keep reading work on the canonical item."
                                : "Metadata from another copy may be useful. Keep reading work on the canonical paper.")
                        }
                        ForEach(group.items) { item in
                            DuplicateItemCard(item: item)
                        }
                    }
                    .padding(12)
                    .paperFlowCard(tint: PaperFlowTheme.lilac, radius: 14)
                }
            }
            .padding(.top, 12)
        }
    }
}

private struct CleanupItemList: View {
    let title: String
    let items: [CleanupWorkbenchItem]

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 12) {
                ForEach(items) { item in
                    CleanupItemCard(item: item)
                }
            }
            .padding(.top, 12)
        }
    }
}

private struct CleanupItemCard<Extra: View>: View {
    let item: CleanupWorkbenchItem
    let extra: Extra
    @EnvironmentObject private var state: AppState

    init(item: CleanupWorkbenchItem, @ViewBuilder extra: () -> Extra) {
        self.item = item
        self.extra = extra()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Text(item.title)
                    .font(.headline)
                Spacer()
                if state.showTechnicalDetails {
                    Text(item.itemKey)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(PaperFlowTheme.muted)
                }
            }
            WorkbenchFlowRow(label: "Current Zotero collections", values: item.currentCollections)
            WorkbenchFlowRow(label: "Planned target collections", values: item.plannedCollections)
            WorkbenchFlowRow(label: "Normalized tags", values: item.normalizedTags)
            WorkbenchFlowRow(label: "Metadata issues", values: item.metadataIssues)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 8)], alignment: .leading, spacing: 6) {
                SmallFact(label: "Confidence", value: String(format: "%.2f", item.confidence))
                SmallFact(label: "DOI", value: item.doi.isEmpty ? "(missing)" : item.doi)
                SmallFact(label: "arXiv ID", value: item.arxivID.isEmpty ? "(missing)" : item.arxivID)
                SmallFact(label: "Year", value: item.year.isEmpty ? "(missing)" : item.year)
                SmallFact(label: "Publication", value: item.publicationTitle.isEmpty ? "(missing)" : item.publicationTitle)
                SmallFact(label: "Abstract", value: item.abstractStatus)
                SmallFact(label: "PDF", value: item.pdfAttachmentStatus)
                SmallFact(label: "PDF storage", value: item.pdfStorageState)
                SmallFact(label: "Reading work", value: item.readingWorkPresent ? "yes" : "no")
                SmallFact(label: "Notes", value: "\(item.noteCount)")
                SmallFact(label: "Annotations", value: "\(item.annotationCount)")
                SmallFact(label: "Highlights", value: "\(item.highlightCount)")
                SmallFact(label: "Underlines", value: "\(item.underlineCount)")
                SmallFact(label: "Comments", value: "\(item.commentCount)")
                SmallFact(label: "Child notes", value: "\(item.childNoteCount)")
            }
            Text("Rationale: \(item.rationale)")
                .foregroundStyle(PaperFlowTheme.muted)
            extra
            FlowLayout(spacing: 8) {
                Button("Open in Zotero") { openZoteroItem(item.itemKey) }
                Button("Reveal PDF") { revealFirstPDF(item.localPDFPaths) }
                    .disabled(item.localPDFPaths.isEmpty)
                Button("Explain item") { state.runExplainItem(item.itemKey) }
                Button("Repair metadata") { state.runRepairMetadataDryRun(itemKey: item.itemKey) }
                Button("Repair abstract") { state.runRepairAbstractDryRun(itemKey: item.itemKey) }
            }
        }
        .padding(12)
        .paperFlowCard(tint: PaperFlowTheme.sky, radius: 14)
    }
}

private extension CleanupItemCard where Extra == EmptyView {
    init(item: CleanupWorkbenchItem) {
        self.init(item: item) { EmptyView() }
    }
}

private struct DuplicateItemCard: View {
    let item: DuplicateWorkbenchItem
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(item.title)
                    .fontWeight(.semibold)
                if item.isCanonical {
                    Text("canonical")
                        .font(.caption)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.green.opacity(0.16))
                        .clipShape(Capsule())
                }
                if item.unsafeToDelete {
                    Text("UNSAFE TO DELETE")
                        .font(.caption)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.red.opacity(0.16))
                        .clipShape(Capsule())
                }
                Spacer()
                if state.showTechnicalDetails {
                    Text(item.itemKey)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(PaperFlowTheme.muted)
                }
            }
            WorkbenchFlowRow(label: "Before", values: item.currentCollections)
            WorkbenchFlowRow(label: "After", values: item.plannedCollections)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 170), spacing: 8)], alignment: .leading, spacing: 6) {
                SmallFact(label: "DOI", value: item.doi.isEmpty ? "(missing)" : item.doi)
                SmallFact(label: "arXiv ID", value: item.arxivID.isEmpty ? "(missing)" : item.arxivID)
                SmallFact(label: "Year", value: item.year.isEmpty ? "(missing)" : item.year)
                SmallFact(label: "Publication", value: item.publicationTitle.isEmpty ? "(missing)" : item.publicationTitle)
                SmallFact(label: "Metadata score", value: item.metadataScore)
                SmallFact(label: "Notes", value: "\(item.noteCount)")
                SmallFact(label: "Annotations", value: "\(item.annotationCount)")
                SmallFact(label: "Highlights", value: "\(item.highlightCount)")
                SmallFact(label: "Underlines", value: "\(item.underlineCount)")
                SmallFact(label: "Comments", value: "\(item.commentCount)")
                SmallFact(label: "PDFs", value: item.pdfStatus)
            }
            FlowLayout(spacing: 8) {
                Button("Open in Zotero") { openZoteroItem(item.itemKey) }
                Button("Reveal PDF") { revealFirstPDF(item.localPDFPaths) }
                    .disabled(item.localPDFPaths.isEmpty)
            }
        }
        .padding(10)
        .background(Color(nsColor: .windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

private struct WorkbenchFlowRow: View {
    let label: String
    let values: [String]

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Text(label)
                .font(.caption)
                .foregroundStyle(PaperFlowTheme.muted)
                .frame(width: 150, alignment: .leading)
            FlowPills(values: values)
        }
    }
}

private struct FlowPills: View {
    let values: [String]

    var body: some View {
        if values.isEmpty {
            Text("(none)")
                .foregroundStyle(PaperFlowTheme.muted)
        } else {
            Text(values.joined(separator: "  •  "))
                .font(.caption)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct SmallFact: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(PaperFlowTheme.muted)
            Text(value.isEmpty ? "(empty)" : value)
                .font(.caption)
                .lineLimit(2)
                .textSelection(.enabled)
        }
    }
}

private func openZoteroItem(_ itemKey: String) {
    guard let url = URL(string: "zotero://select/library/items/\(itemKey)") else {
        return
    }
    NSWorkspace.shared.open(url)
}

private func revealFirstPDF(_ paths: [String]) {
    guard let first = paths.first else {
        return
    }
    NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: first)])
}
