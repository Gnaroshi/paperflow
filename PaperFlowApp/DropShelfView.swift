import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct DropShelfView: View {
    @EnvironmentObject private var state: AppState
    @ObservedObject var controller: FloatingDropShelfController
    @State private var applyConfirmation = ""
    @State private var processingStartedAt: Date?

    var body: some View {
        Group {
            if controller.isExpanded || state.dropShelfPhase != .idleCompact {
                expandedCard
            } else {
                compactPill
            }
        }
        .onDrop(of: [UTType.fileURL], delegate: PDFDropDelegate(state: state, controller: controller))
        .onChange(of: state.runner.status) { status in
            switch status {
            case .running:
                processingStartedAt = Date()
                controller.commandStarted()
            case .succeeded:
                controller.commandFinished(success: true)
            case .failed, .timedOut, .cancelled:
                controller.commandFinished(success: false)
            case .idle:
                break
            }
        }
    }

    private var compactPill: some View {
        HStack(spacing: 8) {
            Image(systemName: "tray.and.arrow.down")
            Text("Drop PDFs")
                .fontWeight(.semibold)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.regularMaterial)
        .clipShape(Capsule())
        .overlay(Capsule().stroke(Color.accentColor.opacity(0.35)))
        .contentShape(Rectangle())
        .onTapGesture(count: 2) {
            controller.compactLeftClick(clickCount: 2)
        }
        .onTapGesture {
            controller.compactLeftClick(clickCount: 1)
        }
        .contextMenu {
            Button("Expand Shelf") { controller.showExpanded() }
            Button("Open Main Window") { AppServices.shared.openMainWindow() }
            Button("Hide Shelf") { controller.hideShelf() }
        }
    }

    private var expandedCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text(state.dropShelfPhase.label)
                        .font(.headline)
                    Text(state.shelfLastResult)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    controller.hideShelf()
                } label: {
                    Image(systemName: "xmark")
                }
                .buttonStyle(.plain)
                .disabled(state.dropShelfPhase == .processing)
            }

            contentForPhase

            HStack {
                Button {
                    state.dropShelfAction = .dryRunIngest
                    state.runDropShelfSelectedAction()
                } label: {
                    Label("Run Dry Run", systemImage: "play.circle")
                }
                .buttonStyle(.borderedProminent)
                .disabled(state.droppedPDFs.isEmpty || state.runner.isRunning || state.dropShelfPhase == .hoveringInvalidFile)

                Button(role: .destructive) {
                    state.dropShelfAction = .applyIngest
                    state.runDropShelfSelectedAction()
                } label: {
                    Label("Apply", systemImage: "exclamationmark.triangle")
                }
                .disabled(
                    state.droppedPDFs.isEmpty
                    || state.runner.isRunning
                    || applyConfirmation != ConfirmationKind.applyIngest.requiredText
                    || !state.shelfStoreInLocalVault
                    || !state.shelfLinkToZoteroNoUpload
                )

                Button("Open in Finder") {
                    if !state.droppedPDFs.isEmpty {
                        NSWorkspace.shared.activateFileViewerSelecting(state.droppedPDFs.map(\.url))
                    }
                }
                .disabled(state.droppedPDFs.isEmpty)

                Button("Clear") {
                    state.clearPDFs()
                    state.dropShelfPhase = .idleCompact
                    state.shelfLastResult = "Ready"
                    applyConfirmation = ""
                }
                .disabled(state.runner.isRunning)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(borderColor.opacity(dragHighlightActive ? 0.95 : 0.65), lineWidth: dragHighlightActive ? 2 : 1)
        )
        .shadow(color: borderColor.opacity(dragHighlightActive ? 0.35 : 0.12), radius: dragHighlightActive ? 18 : 8)
        .scaleEffect(dragHighlightActive ? 1.015 : 1)
        .animation(.easeOut(duration: 0.16), value: dragHighlightActive)
    }

    @ViewBuilder
    private var contentForPhase: some View {
        switch state.dropShelfPhase {
        case .processing:
            processingView
        case .success:
            resultView(success: true)
        case .failure:
            resultView(success: false)
        default:
            dropTarget
            queuedFilesView
            warningsView
            safetyOptionsView
            if state.dropShelfAction == .applyIngest {
                TextField("Type INGEST LOCAL PDFS", text: $applyConfirmation)
                    .textFieldStyle(.roundedBorder)
            }
        }
    }

    private var queuedFilesView: some View {
        Group {
            if !state.droppedPDFs.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(state.droppedPDFs.count) PDF file(s)")
                        .font(.subheadline)
                        .fontWeight(.medium)
                    ForEach(state.droppedPDFs.prefix(3)) { file in
                        HStack {
                            Text(file.name)
                                .font(.caption)
                                .lineLimit(1)
                                .truncationMode(.middle)
                            Spacer()
                            Button("Open") {
                                NSWorkspace.shared.activateFileViewerSelecting([file.url])
                            }
                            .font(.caption)
                            Button("Remove") {
                                state.removePDF(file)
                            }
                            .font(.caption)
                        }
                    }
                    if state.droppedPDFs.count > 3 {
                        Text("+ \(state.droppedPDFs.count - 3) more")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .frame(maxHeight: 76)
            }
        }
    }

    private var warningsView: some View {
        Group {
            if !state.invalidDropWarnings.isEmpty {
                ForEach(state.invalidDropWarnings.prefix(2), id: \.self) { warning in
                    Text(warning)
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
            }
        }
    }

    private var safetyOptionsView: some View {
        HStack(spacing: 14) {
            Toggle("local vault", isOn: $state.shelfStoreInLocalVault)
            Toggle("linked attachment only", isOn: $state.shelfLinkToZoteroNoUpload)
            Toggle("auto dry-run", isOn: $state.autoDryRunAfterDrop)
        }
        .font(.caption)
    }

    private var processingView: some View {
        VStack(alignment: .leading, spacing: 8) {
            ProgressTimeline(
                currentStage: state.runner.currentStage,
                completedStages: state.runner.completedStages
            )
            TimelineView(.periodic(from: processingStartedAt ?? Date(), by: 1)) { context in
                HStack(spacing: 10) {
                    Text("Elapsed: \(elapsedLabel(now: context.date))")
                    if let pid = state.runner.currentPID {
                        Text("PID: \(pid)")
                    }
                    Text("Stage: \(stageLabel(state.runner.currentStage))")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(state.runner.currentCommand.isEmpty ? "paperflow command is running" : state.runner.currentCommand)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Text(state.runner.currentWorkingDirectory)
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                if !state.runner.lastHeartbeat.isEmpty {
                    Text(state.runner.lastHeartbeat)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                if let warning = state.runner.noOutputWarning {
                    Text(warning)
                        .font(.caption)
                        .foregroundStyle(state.runner.stalledWarning ? .red : .orange)
                }
            }
            Text(logTail(maxLines: 5).isEmpty ? "Waiting for command output..." : logTail(maxLines: 5))
                .font(.system(.caption, design: .monospaced))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, minHeight: 54, alignment: .topLeading)
                .padding(8)
                .background(Color(nsColor: .textBackgroundColor).opacity(0.8))
                .clipShape(RoundedRectangle(cornerRadius: 8))
            HStack {
                Button("Open Debug Log") { state.runner.openLogFile() }
                    .disabled(state.runner.currentLogFile == nil)
                Button("Copy Log") { state.runner.copyOutput() }
                    .disabled(state.runner.output.isEmpty)
                Spacer()
                if state.runner.stalledWarning {
                    Button("Run offline-fast") {
                        state.runner.cancel()
                        DispatchQueue.main.asyncAfter(deadline: .now() + 3.5) {
                            state.runDryRunIngestOfflineFast()
                        }
                    }
                }
                Button("Cancel") { state.runner.cancel() }
                    .keyboardShortcut(.cancelAction)
            }
            .font(.caption)
        }
    }

    private func resultView(success: Bool) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Image(systemName: success ? "checkmark.circle.fill" : "xmark.octagon.fill")
                    .foregroundStyle(success ? .green : .red)
                Text(success ? "Command completed" : "Command failed")
                    .fontWeight(.semibold)
                Spacer()
                Button("Copy Log") { state.runner.copyOutput() }
                    .disabled(state.runner.output.isEmpty)
            }
            if success {
                ingestPlanSummary
            } else {
                Text("Command: \(state.runner.currentCommand.isEmpty ? "paperflow" : state.runner.currentCommand)")
                    .font(.system(.caption, design: .monospaced))
                    .lineLimit(1)
                    .truncationMode(.middle)
                Text(logTail(maxLines: 5).isEmpty ? state.shelfLastResult : logTail(maxLines: 5))
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.red)
                    .textSelection(.enabled)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var ingestPlanSummary: some View {
        VStack(alignment: .leading, spacing: 4) {
            let rows = latestIngestRows()
            if rows.isEmpty {
                Text(state.shelfLastResult)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(rows.prefix(2), id: \.targetPath) { row in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(row.title)
                            .font(.caption)
                            .fontWeight(.semibold)
                        Text("Planned filename: \(URL(fileURLWithPath: row.targetPath).lastPathComponent)")
                            .font(.caption)
                            .lineLimit(1)
                            .truncationMode(.middle)
                        Text("Planned collections: \(row.collections.isEmpty ? "not available" : row.collections.joined(separator: ", "))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                        Text("Planned tags: \(row.tags.isEmpty ? "not available" : row.tags.joined(separator: ", "))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }
            }
        }
    }

    private struct IngestSummaryRow {
        let title: String
        let targetPath: String
        let collections: [String]
        let tags: [String]
    }

    private func latestIngestRows() -> [IngestSummaryRow] {
        let url = state.dataURL.appendingPathComponent("ingest_plan.json")
        guard let data = try? Data(contentsOf: url),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = json["items"] as? [[String: Any]] else {
            return []
        }
        return items.compactMap { item in
            guard let target = item["target_path"] as? String else {
                return nil
            }
            return IngestSummaryRow(
                title: item["title"] as? String ?? URL(fileURLWithPath: target).deletingPathExtension().lastPathComponent,
                targetPath: target,
                collections: item["target_collections"] as? [String] ?? [],
                tags: item["normalized_tags"] as? [String] ?? []
            )
        }
    }

    private func logTail(maxLines: Int) -> String {
        state.runner.output
            .split(separator: "\n")
            .suffix(maxLines)
            .joined(separator: "\n")
    }

    private func elapsedLabel(now: Date) -> String {
        let seconds = max(0, Int(state.runner.elapsedSeconds > 0 ? state.runner.elapsedSeconds : now.timeIntervalSince(processingStartedAt ?? now)))
        return "\(seconds / 60)m \(seconds % 60)s"
    }

    private struct ProgressTimeline: View {
        let currentStage: String
        let completedStages: Set<String>

        private let stages = [
            ("validate_files", "Validate"),
            ("extract_first_page_text", "Text"),
            ("extract_arxiv_id", "arXiv ID"),
            ("fetch_arxiv_metadata", "Metadata"),
            ("classify", "Classify"),
            ("plan_filename", "Filename"),
            ("write_dry_run_report", "Report")
        ]

        var body: some View {
            HStack(spacing: 8) {
                ForEach(Array(stages.enumerated()), id: \.offset) { index, stage in
                    TimelineStep(
                        label: stage.1,
                        filled: completedStages.contains(stage.0) || currentStage == stage.0,
                        active: currentStage == stage.0
                    )
                    if index < stages.count - 1 {
                        Rectangle()
                            .fill(completedStages.contains(stage.0) ? Color.accentColor.opacity(0.55) : Color.secondary.opacity(0.25))
                            .frame(height: 2)
                    }
                }
            }
        }
    }

    private struct TimelineStep: View {
        let label: String
        let filled: Bool
        var active: Bool = false

        var body: some View {
            HStack(spacing: 4) {
                Circle()
                    .fill(filled ? Color.accentColor : Color.secondary.opacity(0.3))
                    .frame(width: active ? 11 : 9, height: active ? 11 : 9)
                Text(label)
                    .font(.caption2)
                    .foregroundStyle(filled ? .primary : .secondary)
            }
        }
    }

    private func stageLabel(_ stage: String) -> String {
        switch stage {
        case "validate_files":
            return "validating files"
        case "inspect_pdf":
            return "inspecting PDF"
        case "extract_filename_identifiers":
            return "reading filename identifiers"
        case "extract_first_page_text":
            return "extracting first page text"
        case "extract_arxiv_id":
            return "extracting arXiv ID"
        case "fetch_arxiv_metadata":
            return "fetching arXiv metadata"
        case "detect_doi":
            return "detecting DOI"
        case "fetch_doi_metadata":
            return "fetching DOI metadata"
        case "classify":
            return "classifying"
        case "plan_filename":
            return "planning vault filename"
        case "plan_zotero_actions":
            return "planning Zotero actions"
        case "write_dry_run_report":
            return "writing report"
        case "done":
            return "done"
        default:
            return stage.isEmpty ? "starting" : stage
        }
    }
    private var dropTarget: some View {
        VStack(spacing: 6) {
            Image(systemName: "doc.badge.plus")
                .font(.title2)
            Text(dropTargetTitle)
                .font(.subheadline)
                .fontWeight(.medium)
            Text(dropTargetSubtitle)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, minHeight: 92)
        .background(dropTargetBackground)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(borderColor.opacity(dragHighlightActive ? 0.8 : 0.35), style: StrokeStyle(lineWidth: dragHighlightActive ? 2 : 1, dash: [5]))
        )
    }

    private var dragHighlightActive: Bool {
        state.dropShelfPhase == .hoveringValidPDF || state.dropShelfPhase == .hoveringInvalidFile
    }

    private var dropTargetTitle: String {
        switch state.dropShelfPhase {
        case .hoveringValidPDF:
            return "Release to preview PDFs"
        case .hoveringInvalidFile:
            return "Only PDF files are accepted"
        default:
            return "Drop PDFs here"
        }
    }

    private var dropTargetSubtitle: String {
        switch state.dropShelfPhase {
        case .hoveringValidPDF:
            return "\(state.shelfLastResult) linked-local only; no Zotero Storage upload"
        case .hoveringInvalidFile:
            return state.invalidDropWarnings.first ?? "Non-PDF files will be rejected"
        default:
            return "linked-local only; no Zotero Storage upload"
        }
    }

    private var dropTargetBackground: Color {
        switch state.dropShelfPhase {
        case .hoveringInvalidFile:
            return Color.red.opacity(0.14)
        case .hoveringValidPDF:
            return Color.accentColor.opacity(0.18)
        default:
            return Color.accentColor.opacity(0.08)
        }
    }

    private var borderColor: Color {
        switch state.dropShelfPhase {
        case .failure, .hoveringInvalidFile:
            return .red
        case .success:
            return .green
        case .hoveringValidPDF, .queued, .processing:
            return .accentColor
        case .reviewNeeded:
            return .orange
        case .idleCompact:
            return .secondary
        }
    }

    fileprivate static func loadFileURLs(from providers: [NSItemProvider], completion: @escaping ([URL]) -> Void) {
        let group = DispatchGroup()
        let lock = NSLock()
        var urls: [URL] = []

        for provider in providers {
            group.enter()
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
                defer { group.leave() }
                var resolvedURL: URL?
                if let url = item as? URL {
                    resolvedURL = url
                } else if let data = item as? Data {
                    resolvedURL = URL(dataRepresentation: data, relativeTo: nil)
                } else if let string = item as? String {
                    resolvedURL = URL(string: string)
                }
                if let resolvedURL {
                    lock.lock()
                    urls.append(resolvedURL)
                    lock.unlock()
                }
            }
        }

        group.notify(queue: .main) {
            completion(urls)
        }
    }
}

private struct PDFDropDelegate: DropDelegate {
    let state: AppState
    let controller: FloatingDropShelfController

    func validateDrop(info: DropInfo) -> Bool {
        !info.itemProviders(for: [UTType.fileURL]).isEmpty
    }

    func dropEntered(info: DropInfo) {
        let providers = info.itemProviders(for: [UTType.fileURL])
        guard !providers.isEmpty else {
            state.invalidDropWarnings = ["Only PDF files are accepted."]
            controller.dragHover(valid: false, fileCount: 0)
            return
        }
        DropShelfView.loadFileURLs(from: providers) { urls in
            let pdfs = urls.filter { $0.pathExtension.lowercased() == "pdf" }
            let invalids = urls.filter { $0.pathExtension.lowercased() != "pdf" }
            state.invalidDropWarnings = invalids.map { "Ignored non-PDF: \($0.lastPathComponent)" }
            controller.dragHover(valid: !pdfs.isEmpty && invalids.isEmpty, fileCount: pdfs.count)
        }
    }

    func dropUpdated(info: DropInfo) -> DropProposal? {
        DropProposal(operation: .copy)
    }

    func dropExited(info: DropInfo) {
        controller.dragExited()
    }

    func performDrop(info: DropInfo) -> Bool {
        let providers = info.itemProviders(for: [UTType.fileURL])
        DropShelfView.loadFileURLs(from: providers) { urls in
            controller.handleDropped(urls)
        }
        return true
    }
}
