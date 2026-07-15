import SwiftUI

struct LocalFolderImportView: View {
    @EnvironmentObject private var state: AppState
    let confirm: (ConfirmationKind) -> Void

    @State private var selectedFilter: LocalImportFilter = .newOnly
    @State private var manualActions: [String: String] = [:]
    @State private var manualCollections: [String: String] = [:]
    @State private var manualTags: [String: String] = [:]
    @State private var detailRow: LocalImportRow?
    @State private var editRow: LocalImportRow?
    @State private var editMode: EditMode?
    @State private var editText = ""
    @State private var correctRow: LocalImportRow?
    @State private var correctCollectionText = ""
    @State private var correctTagsText = ""

    private enum EditMode {
        case collection
        case tags
    }

    private var filteredRows: [LocalImportRow] {
        state.localImportData.rows.filter { row in
            switch selectedFilter {
            case .all:
                return true
            case .newOnly:
                return row.status == "new" || effectiveAction(for: row) == "import" || row.action == "create"
            case .alreadyInZotero:
                return row.status == "exact_existing" || row.status == "likely_existing"
            case .possibleDuplicates:
                return row.status == "possible_existing" || row.status == "local_duplicate"
            case .updateCandidates:
                return row.status == "update_candidate" || effectiveAction(for: row) == "update existing"
            case .reviewNeeded:
                return row.action == "review"
                    || row.tags.contains("status/review-needed")
                    || row.primaryCollection.contains("/05 Review Queue/")
                    || row.secondaryCollections.contains { $0.contains("/05 Review Queue/") }
            case .lowConfidence:
                return row.confidence > 0 && row.confidence < 0.55 || row.tags.contains("cleanup/low-confidence")
            case .missingMetadata:
                return row.metadataIssues.contains("missing-doi-or-arxiv")
                    || row.tags.contains("cleanup/missing-metadata")
                    || row.primaryCollection.contains("Missing Metadata")
                    || row.secondaryCollections.contains { $0.contains("Missing Metadata") }
            case .missingAbstract:
                return !row.abstractPresent
                    || row.tags.contains("cleanup/missing-abstract")
                    || row.primaryCollection.contains("Missing Abstract")
                    || row.secondaryCollections.contains { $0.contains("Missing Abstract") }
            }
        }
    }

    private var scanState: WorkflowStepState {
        state.workflowStepState(
            commandFragment: "local scan",
            outputs: ["data/local_scan.json"]
        )
    }

    private var matchState: WorkflowStepState {
        state.workflowStepState(
            commandFragment: "local match-zotero",
            prerequisiteGroups: [["data/local_scan.json"]],
            outputs: ["data/zotero_index.json", "data/local_zotero_match_plan.json"]
        )
    }

    private var classifyState: WorkflowStepState {
        state.workflowStepState(
            commandFragment: "local classify-new",
            prerequisiteGroups: [["data/local_scan.json"], ["data/local_zotero_match_plan.json"]],
            outputs: ["data/local_classification_plan.json"]
        )
    }

    private var planState: WorkflowStepState {
        state.workflowStepState(
            commandFragment: "local plan-import",
            prerequisiteGroups: [["data/local_classification_plan.json"]],
            outputs: ["data/local_import_plan.json"]
        )
    }

    private var applyState: WorkflowStepState {
        guard state.zoteroVerification.writeAccess else {
            return .blocked("Verify Zotero write access in Settings")
        }
        return state.workflowStepState(
            commandFragment: "local apply-import",
            prerequisiteGroups: [["data/local_import_plan.json"]]
        )
    }

    private var auditState: WorkflowStepState {
        guard state.hasGeneratedArtifact(prefix: "local_import_apply_log_", suffix: ".json") else {
            return .blocked("Requires a successful local import apply log")
        }
        return state.workflowStepState(
            commandFragment: "local audit-import",
            outputs: ["data/local_import_audit.json", "data/local_import_audit.md"]
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionTitle("Local Folder Import")
            Text("Downloads나 선택한 폴더의 PDF를 검사하고, Zotero에 없는 새 논문만 local vault로 복사한 뒤 Zotero item과 linked attachment로 추가합니다.")
                .foregroundStyle(PaperFlowTheme.muted)

            WarningBox(text: "Scan, match, classify, plan은 dry-run입니다. Add to Zotero 단계에서만 PDF를 vault로 복사하고 Zotero parent item, collection, tag, linked attachment를 생성합니다. Zotero Storage upload는 항상 false입니다.")

            folderControls
            settingsControls
            workflowButtons
            summaryGrid
            filterControls
            localEditNotice
            resultsTable
        }
        .onAppear {
            state.refreshLocalImportStatus()
        }
        .sheet(item: $detailRow) { row in
            explanationSheet(row)
        }
        .sheet(item: $editRow) { row in
            editSheet(row)
        }
        .sheet(item: $correctRow) { row in
            correctClassificationSheet(row)
        }
    }

    private var folderControls: some View {
        SurfaceSection(title: "Source folder", subtitle: "PDF만 재귀적으로 스캔하며 원본 파일은 dry-run에서 변경하지 않습니다.") {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 8) {
                    Button {
                        state.chooseLocalImportFolder()
                    } label: {
                        Label("Choose Folder", systemImage: "folder")
                    }
                    TextField("Terminal path", text: $state.localImportPath)
                        .paperFlowTextInput()
                        .font(.system(.body, design: .monospaced))
                    Button("Refresh") {
                        state.refreshLocalImportStatus()
                    }
                }
                VStack(alignment: .leading, spacing: 8) {
                    TextField("Terminal path", text: $state.localImportPath)
                        .paperFlowTextInput()
                        .font(.system(.body, design: .monospaced))
                    FlowLayout(spacing: 8) {
                        Button("Choose Folder") { state.chooseLocalImportFolder() }
                        Button("Refresh Results") { state.refreshLocalImportStatus() }
                    }
                }
            }
            StatusLine(label: "Project", value: state.projectPath)
        }
    }

    private var settingsControls: some View {
        SurfaceSection(title: "Import policy") {
            FlowLayout(spacing: 14) {
                Toggle("Recursive", isOn: $state.localImportRecursive)
                TextField("Max depth", text: $state.localImportMaxDepth)
                    .paperFlowTextInput()
                    .frame(width: 92)
                Toggle("Exclude existing Zotero items", isOn: $state.localImportExcludeExistingZotero)
                Toggle("Use Gemini for ambiguous classification", isOn: $state.localImportUseGemini)
                Toggle("Stop on Gemini quota hit", isOn: $state.localImportStopOnGeminiQuota)
            }
            FlowLayout(spacing: 18) {
                StatusLine(label: "Storage mode", value: "linked-local")
                StatusLine(label: "Zotero Storage upload", value: "false")
                StatusLine(label: "Latest data", value: state.localImportData.generatedStatus)
            }
        }
    }

    private var workflowButtons: some View {
        SurfaceSection(
            title: "Import workflow",
            subtitle: "각 단계는 이전 산출물을 검사합니다. Match Zotero의 두 backend 명령은 첫 명령 성공 시에만 이어서 실행됩니다."
        ) {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 12)], spacing: 12) {
                WorkflowStepCard(number: 1, title: "Scan Folder", detail: "PDF hash, first pages, identifiers를 수집", icon: "magnifyingglass", state: scanState, actionTitle: "Scan", action: state.runLocalFolderScan)
                WorkflowStepCard(number: 2, title: "Match Zotero", detail: "Zotero index 생성 후 existing/update candidate 판별", icon: "link", state: matchState, actionTitle: "Index & Match", action: state.runLocalFolderMatchZotero)
                WorkflowStepCard(number: 3, title: "Classify New Papers", detail: "new 상태인 PDF만 taxonomy로 분류", icon: "sparkles", state: classifyState, actionTitle: "Classify", action: state.runLocalFolderClassifyNew)
                WorkflowStepCard(number: 4, title: "Plan Import", detail: "vault 경로와 linked-local Zotero operation 생성", icon: "list.bullet.rectangle", state: planState, actionTitle: "Build Plan", action: state.runLocalFolderPlanImport)
                WorkflowStepCard(number: 5, title: "Add to Zotero", detail: "확인 후 vault copy, Zotero item, collection/tag, linked attachment 생성", icon: "square.and.arrow.down", state: applyState, actionTitle: "Review & Add") {
                    confirm(.applyLocalImport)
                }
                WorkflowStepCard(number: 6, title: "Audit Import", detail: "vault file, Zotero item, linked attachment를 검증", icon: "checkmark.seal", state: auditState, actionTitle: "Run Audit", action: state.runLocalFolderAuditImport)
            }
        }
    }

    private var summaryGrid: some View {
        let summary = state.localImportData.summary
        return LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 10)], spacing: 10) {
            InfoTile(title: "PDFs scanned", value: "\(summary.totalPDFsScanned)")
            InfoTile(title: "Skipped files", value: "\(summary.skippedFiles)")
            InfoTile(title: "Already in Zotero", value: "\(summary.alreadyInZotero)")
            InfoTile(title: "Likely existing", value: "\(summary.likelyExisting)")
            InfoTile(title: "Possible existing", value: "\(summary.possibleExisting)")
            InfoTile(title: "Update candidates", value: "\(summary.updateCandidates)")
            InfoTile(title: "New papers", value: "\(summary.newPapers)")
            InfoTile(title: "Classified", value: "\(summary.classifiedPapers)")
            InfoTile(title: "Review needed", value: "\(summary.reviewNeededPapers)")
            InfoTile(title: "Planned imports", value: "\(summary.plannedImports)")
            InfoTile(title: "Copied to vault", value: "\(summary.copiedToVault)")
            InfoTile(title: "Linked attachments", value: "\(summary.zoteroLinkedAttachmentsCreated)")
        }
    }

    private var filterControls: some View {
        ViewThatFits(in: .horizontal) {
            Picker("Filter", selection: $selectedFilter) {
                ForEach(LocalImportFilter.allCases) { filter in
                    Text(filter.rawValue).tag(filter)
                }
            }
            .pickerStyle(.segmented)
            Picker("Filter", selection: $selectedFilter) {
                ForEach(LocalImportFilter.allCases) { filter in
                    Text(filter.rawValue).tag(filter)
                }
            }
            .pickerStyle(.menu)
            .frame(maxWidth: 260, alignment: .leading)
        }
    }

    private var localEditNotice: some View {
        WarningBox(text: "Correct classification saves a reusable YAML rule and re-runs classification. The Edit/Mark menu remains a local review override; re-run plan commands before applying.")
    }

    private var resultsTable: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("\(filteredRows.count) rows")
                .font(.headline)
            ScrollView([.horizontal, .vertical]) {
                VStack(alignment: .leading, spacing: 0) {
                    tableHeader
                    Divider()
                    ForEach(filteredRows) { row in
                        rowView(row)
                        Divider()
                    }
                }
                .frame(minWidth: 1900, alignment: .leading)
            }
            .frame(minHeight: 360)
            .background(PaperFlowTheme.panel0.opacity(0.92))
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(PaperFlowTheme.line, lineWidth: 1)
            )
        }
    }

    private var tableHeader: some View {
        HStack(spacing: 0) {
            headerCell("status", width: 120)
            headerCell("title", width: 220)
            headerCell("local path", width: 260)
            headerCell("matched Zotero item", width: 150)
            headerCell("match reason", width: 220)
            headerCell("primary collection", width: 240)
            headerCell("secondary collections", width: 260)
            headerCell("tags", width: 260)
            headerCell("confidence", width: 90)
            headerCell("planned vault path", width: 260)
            headerCell("action", width: 180)
            headerCell("row actions", width: 620)
        }
        .background(PaperFlowTheme.panel1.opacity(0.92))
    }

    private func rowView(_ row: LocalImportRow) -> some View {
        HStack(spacing: 0) {
            textCell(row.status, width: 120)
            textCell(row.title, width: 220)
            textCell(row.localPath, width: 260, monospaced: true)
            textCell(row.matchedZoteroItem.isEmpty ? "-" : row.matchedZoteroItem, width: 150, monospaced: true)
            textCell(row.matchReason, width: 220)
            textCell(effectivePrimaryCollection(for: row), width: 240)
            textCell(row.secondaryCollections.joined(separator: "; "), width: 260)
            textCell(effectiveTags(for: row), width: 260)
            textCell(row.confidence > 0 ? String(format: "%.2f", row.confidence) : "-", width: 90)
            textCell(row.plannedVaultPath.isEmpty ? row.copiedFilePath : row.plannedVaultPath, width: 260, monospaced: true)
            textCell(effectiveAction(for: row), width: 180)
            actionCell(row, width: 620)
        }
    }

    private func headerCell(_ text: String, width: CGFloat) -> some View {
        Text(text)
            .font(.caption)
            .fontWeight(.semibold)
            .foregroundStyle(PaperFlowTheme.muted)
            .frame(width: width, alignment: .leading)
            .padding(8)
    }

    private func textCell(_ text: String, width: CGFloat, monospaced: Bool = false) -> some View {
        Text(text.isEmpty ? "-" : text)
            .font(monospaced ? .system(.caption, design: .monospaced) : .caption)
            .lineLimit(3)
            .textSelection(.enabled)
            .frame(width: width, alignment: .leading)
            .padding(8)
    }

    private func actionCell(_ row: LocalImportRow, width: CGFloat) -> some View {
        HStack(spacing: 6) {
            Button("Open") { state.openLocalPDF(path: row.localPath) }
                .disabled(row.localPath.isEmpty)
            Button("Reveal") { state.revealInFinder(path: row.localPath) }
                .disabled(row.localPath.isEmpty)
            Button("Zotero") { state.openZoteroItem(itemKey: row.matchedZoteroItem) }
                .disabled(row.matchedZoteroItem.isEmpty)
            Button("Explain") { detailRow = row }
            Button("Correct classification") {
                correctCollectionText = effectivePrimaryCollection(for: row)
                correctTagsText = effectiveTags(for: row)
                correctRow = row
            }
            Menu("Edit") {
                Button("Edit target collection") {
                    editMode = .collection
                    editText = effectivePrimaryCollection(for: row)
                    editRow = row
                }
                Button("Edit tags") {
                    editMode = .tags
                    editText = effectiveTags(for: row)
                    editRow = row
                }
            }
            Menu("Mark") {
                Button("skip") { manualActions[row.id] = "skip" }
                Button("import") { manualActions[row.id] = "import" }
                Button("update existing") { manualActions[row.id] = "update existing" }
                Button("review queue") { manualActions[row.id] = "review" }
            }
        }
        .font(.caption)
        .frame(width: width, alignment: .leading)
        .padding(8)
    }

    private func explanationSheet(_ row: LocalImportRow) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(row.title)
                .font(.title3)
                .fontWeight(.semibold)
            StatusLine(label: "Status", value: row.status)
            StatusLine(label: "Match reason", value: row.matchReason.isEmpty ? "-" : row.matchReason)
            StatusLine(label: "Primary collection", value: effectivePrimaryCollection(for: row))
            StatusLine(label: "Tags", value: effectiveTags(for: row))
            StatusLine(label: "Confidence", value: row.confidence > 0 ? String(format: "%.2f", row.confidence) : "-")
            Text(row.rationale.isEmpty ? "No rationale was found in the current reports." : row.rationale)
                .foregroundStyle(PaperFlowTheme.muted)
                .textSelection(.enabled)
            if !row.copiedFilePath.isEmpty || !row.zoteroItemKey.isEmpty || !row.linkedAttachmentStatus.isEmpty {
                Divider()
                StatusLine(label: "Copied file path", value: row.copiedFilePath.isEmpty ? "-" : row.copiedFilePath)
                StatusLine(label: "Zotero item key", value: row.zoteroItemKey.isEmpty ? "-" : row.zoteroItemKey)
                StatusLine(label: "Linked attachment", value: row.linkedAttachmentStatus.isEmpty ? "-" : row.linkedAttachmentStatus)
            }
            HStack {
                Spacer()
                Button("Close") { detailRow = nil }
            }
        }
        .padding()
        .frame(width: 620)
    }

    private func editSheet(_ row: LocalImportRow) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(editMode == .tags ? "Edit Tags" : "Edit Target Collection")
                .font(.title3)
                .fontWeight(.semibold)
            Text("This is a local UI review override only; backend row-edit persistence is not implemented yet.")
                .foregroundStyle(PaperFlowTheme.muted)
            TextField("Value", text: $editText, axis: .vertical)
                .paperFlowTextInput()
                .lineLimit(3...6)
            HStack {
                Spacer()
                Button("Cancel") { editRow = nil }
                Button("Save Override") {
                    if editMode == .tags {
                        manualTags[row.id] = editText
                    } else {
                        manualCollections[row.id] = editText
                    }
                    editRow = nil
                }
            }
        }
        .padding()
        .frame(width: 560)
    }

    private func correctClassificationSheet(_ row: LocalImportRow) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Correct Classification")
                .font(.title3)
                .fontWeight(.semibold)
            Text(row.title)
                .font(.headline)
                .textSelection(.enabled)
            Text("Save this correction as a reusable user taxonomy rule. PaperFlow will append it to `config/user_taxonomy_overrides.yaml` and re-run local pending classification.")
                .foregroundStyle(PaperFlowTheme.muted)
            TextField("Target collection", text: $correctCollectionText, axis: .vertical)
                .paperFlowTextInput()
                .lineLimit(2...4)
            TextField("Tags separated by semicolons or commas", text: $correctTagsText, axis: .vertical)
                .paperFlowTextInput()
                .lineLimit(3...6)
            HStack {
                Spacer()
                Button("Cancel") { correctRow = nil }
                Button("Save as Rule") {
                    manualCollections[row.id] = correctCollectionText
                    manualTags[row.id] = correctTagsText
                    state.saveUserClassificationOverrideRule(
                        row: row,
                        collection: correctCollectionText,
                        tagsText: correctTagsText
                    )
                    correctRow = nil
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding()
        .frame(width: 640)
    }

    private func effectiveAction(for row: LocalImportRow) -> String {
        manualActions[row.id] ?? row.action
    }

    private func effectivePrimaryCollection(for row: LocalImportRow) -> String {
        manualCollections[row.id] ?? row.primaryCollection
    }

    private func effectiveTags(for row: LocalImportRow) -> String {
        manualTags[row.id] ?? row.tags.joined(separator: "; ")
    }
}
