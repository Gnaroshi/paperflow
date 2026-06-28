import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct DropShelfView: View {
    @EnvironmentObject private var state: AppState
    @ObservedObject var controller: FloatingDropShelfController
    @State private var applyConfirmation = ""
    @State private var processingStartedAt: Date?
    @State private var mode: PFWMode = .drop

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
                mode = .drop
                controller.commandStarted()
            case .succeeded:
                mode = .drop
                controller.commandFinished(success: true)
            case .failed, .timedOut, .cancelled:
                mode = .drop
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
        VStack(alignment: .leading, spacing: 0) {
            pfwHeader

            Divider()
                .opacity(0.18)

            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    contentForMode
                }
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .topLeading)
            }
            .scrollIndicators(.automatic)

            Divider()
                .opacity(0.18)

            pfwFooter
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(borderColor.opacity(dragHighlightActive ? 0.95 : 0.35), lineWidth: dragHighlightActive ? 2 : 1)
        )
        .shadow(color: borderColor.opacity(dragHighlightActive ? 0.35 : 0.18), radius: dragHighlightActive ? 22 : 16, x: 0, y: 10)
        .scaleEffect(dragHighlightActive ? 1.015 : 1)
        .animation(.easeOut(duration: 0.16), value: dragHighlightActive)
    }

    private var pfwHeader: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(state.dropShelfPhase.label)
                    .font(.headline)
                Text(state.shelfLastResult)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            Spacer(minLength: 8)
            Picker("PFW mode", selection: $mode) {
                ForEach(PFWMode.allCases) { mode in
                    Label(mode.label, systemImage: mode.symbolName).tag(mode)
                }
            }
            .labelsHidden()
            .pickerStyle(.segmented)
            .frame(width: 330)
            Button {
                controller.hideShelf()
            } label: {
                Image(systemName: "xmark")
            }
            .buttonStyle(.plain)
            .help("Hide PaperFlow Floating Window")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .contentShape(Rectangle())
        .gesture(DragGesture(minimumDistance: 1).onChanged { _ in })
    }

    @ViewBuilder
    private var contentForMode: some View {
        switch mode {
        case .drop:
            contentForPhase
        case .status:
            statusMiniDashboard
        case .recent:
            recentView
        case .zotero:
            zoteroMiniActions
        case .logs:
            logsMiniView
        }
    }

    private var pfwFooter: some View {
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

            Spacer()

            Button("Hide PFW") {
                controller.hideShelf()
            }
        }
        .font(.caption)
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(.thinMaterial)
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
            actionChoiceView
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

    private var actionChoiceView: some View {
        Picker("Target action", selection: $state.dropShelfAction) {
            ForEach(DropShelfAction.allCases) { action in
                Text(action.label).tag(action)
            }
        }
        .pickerStyle(.segmented)
        .font(.caption)
    }

    private var statusMiniDashboard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                MiniStatus(label: "Zotero", value: state.zoteroConnectionStatus)
                MiniStatus(label: "Gemini", value: state.geminiConnectionStatus)
            }
            HStack {
                MiniStatus(label: "Vault", value: state.vaultStatus.exists ? "Ready" : "Missing")
                MiniStatus(label: "Last command", value: state.runner.status.label)
            }
            HStack {
                MiniStatus(label: "Missing abstract", value: "\(state.dashboard.missingAbstractItems)")
                MiniStatus(label: "Duplicates", value: "\(state.dashboard.duplicateCandidates)")
            }
            Text("Data sync and file sync are separate. Local linked PDFs should not consume Zotero Storage.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var recentView: some View {
        VStack(alignment: .leading, spacing: 10) {
            ingestPlanSummary
            HStack {
                Button("Open Report") {
                    NSWorkspace.shared.open(state.dataURL.appendingPathComponent("ingest_report.md"))
                }
                Button("Open Vault") { state.openVault() }
                Button("Open Reports") { state.openReportsFolder() }
            }
            .font(.caption)
        }
    }

    private var zoteroMiniActions: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Zotero organization")
                .font(.subheadline)
                .fontWeight(.semibold)
            Text("Apply Migration requires typed confirmation in the main window. It changes collections/tags only and should not delete notes, annotations, highlights, or attachments.")
                .font(.caption)
                .foregroundStyle(.secondary)
            HStack {
                Button("Backup") { state.runBackupZotero() }
                Button("Plan Migration") { state.runPlanMigration() }
                Button("Dry Run Migration") { state.runDryRunMigration() }
                Button("Open Workbench") {
                    AppServices.shared.openMainWindow(section: .cleanupWorkbench)
                }
            }
            .font(.caption)
            .disabled(state.runner.isRunning)
        }
    }

    private var logsMiniView: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(state.runner.currentCommand.isEmpty ? "No command running." : state.runner.currentCommand)
                    .font(.system(.caption, design: .monospaced))
                    .lineLimit(1)
                    .truncationMode(.middle)
                Spacer()
                Button("Copy") { state.runner.copyOutput() }
                    .disabled(state.runner.output.isEmpty)
                Button("Open Log") { state.runner.openLogFile() }
                    .disabled(state.runner.currentLogFile == nil)
            }
            Text(logTail(maxLines: 12).isEmpty ? "No command output yet." : logTail(maxLines: 12))
                .font(.system(.caption, design: .monospaced))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, minHeight: 160, alignment: .topLeading)
                .padding(8)
                .background(Color.white.opacity(0.46))
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
    }

    private struct MiniStatus: View {
        let label: String
        let value: String

        var body: some View {
            VStack(alignment: .leading, spacing: 4) {
                Text(label)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(value)
                    .font(.caption)
                    .fontWeight(.medium)
                    .lineLimit(2)
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.white.opacity(0.38))
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
    }

    private var cardBackground: some View {
        ZStack {
            LinearGradient(
                colors: theme.background,
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            Rectangle()
                .fill(.regularMaterial)
                .opacity(0.72)
        }
    }

    private var theme: PFWTheme {
        switch state.dropShelfPhase {
        case .hoveringValidPDF:
            return .validDrop
        case .hoveringInvalidFile:
            return .invalidDrop
        case .processing:
            return .processing
        case .success:
            return .success
        case .failure:
            return .failure
        case .reviewNeeded:
            return .warning
        case .queued:
            return .queued
        case .idleCompact:
            return .idle
        }
    }

    private struct PFWTheme {
        let background: [Color]
        let border: Color

        static let idle = PFWTheme(
            background: [Color(red: 0.92, green: 0.94, blue: 0.98), Color(red: 0.98, green: 0.94, blue: 0.97)],
            border: Color(red: 0.52, green: 0.58, blue: 0.68)
        )
        static let queued = PFWTheme(
            background: [Color(red: 0.88, green: 0.94, blue: 1.0), Color(red: 0.95, green: 0.92, blue: 1.0)],
            border: Color(red: 0.32, green: 0.48, blue: 0.88)
        )
        static let validDrop = PFWTheme(
            background: [Color(red: 0.84, green: 0.98, blue: 0.92), Color(red: 0.86, green: 0.94, blue: 1.0)],
            border: Color(red: 0.12, green: 0.66, blue: 0.64)
        )
        static let invalidDrop = PFWTheme(
            background: [Color(red: 1.0, green: 0.90, blue: 0.84), Color(red: 1.0, green: 0.96, blue: 0.78)],
            border: Color(red: 0.92, green: 0.32, blue: 0.24)
        )
        static let processing = PFWTheme(
            background: [Color(red: 0.91, green: 0.90, blue: 1.0), Color(red: 0.86, green: 0.95, blue: 1.0)],
            border: Color(red: 0.44, green: 0.44, blue: 0.92)
        )
        static let success = PFWTheme(
            background: [Color(red: 0.84, green: 0.98, blue: 0.90), Color(red: 0.92, green: 0.98, blue: 0.86)],
            border: Color(red: 0.12, green: 0.64, blue: 0.38)
        )
        static let failure = PFWTheme(
            background: [Color(red: 1.0, green: 0.88, blue: 0.91), Color(red: 0.98, green: 0.90, blue: 0.96)],
            border: Color(red: 0.86, green: 0.22, blue: 0.36)
        )
        static let warning = PFWTheme(
            background: [Color(red: 1.0, green: 0.96, blue: 0.78), Color(red: 1.0, green: 0.90, blue: 0.78)],
            border: Color(red: 0.86, green: 0.52, blue: 0.12)
        )
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
                    .foregroundStyle(success ? Color(red: 0.08, green: 0.56, blue: 0.32) : Color(red: 0.82, green: 0.16, blue: 0.28))
                Text(success ? "Dry Run Complete" : "Command Failed")
                    .fontWeight(.semibold)
                Spacer()
                Button("Copy Log") { state.runner.copyOutput() }
                    .disabled(state.runner.output.isEmpty)
            }
            if success {
                HStack(spacing: 12) {
                    Text(elapsedResultLabel)
                    Text("No files copied")
                    Text("No Zotero writes executed")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                if !state.runner.finalProgressMessage.isEmpty {
                    Text(state.runner.finalProgressMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                ingestPlanSummary
                HStack {
                    Button("Open ingest_report.md") {
                        NSWorkspace.shared.open(state.dataURL.appendingPathComponent("ingest_report.md"))
                    }
                    Button("Copy Summary") { copyIngestSummary() }
                    Button("Open Vault") { state.openVault() }
                    Button("Hide PFW") { controller.hideShelf() }
                }
                .font(.caption)
                if !state.droppedPDFs.isEmpty {
                    HStack {
                        TextField("Type INGEST LOCAL PDFS to enable Apply Ingest", text: $applyConfirmation)
                            .textFieldStyle(.roundedBorder)
                        Button(role: .destructive) {
                            state.dropShelfAction = .applyIngest
                            state.runDropShelfSelectedAction()
                        } label: {
                            Label("Apply Ingest", systemImage: "exclamationmark.triangle")
                        }
                        .disabled(
                            state.runner.isRunning
                            || applyConfirmation != ConfirmationKind.applyIngest.requiredText
                            || !state.shelfStoreInLocalVault
                            || !state.shelfLinkToZoteroNoUpload
                        )
                    }
                    .font(.caption)
                }
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
                    VStack(alignment: .leading, spacing: 3) {
                        Text(row.title)
                            .font(.caption)
                            .fontWeight(.semibold)
                        Text("Source file: \(row.sourceFile)")
                            .font(.caption)
                            .lineLimit(1)
                            .truncationMode(.middle)
                        Text("Planned vault path: \(row.targetPath)")
                            .font(.caption)
                            .lineLimit(1)
                            .truncationMode(.middle)
                        Text("Storage: \(row.storageMode); upload to Zotero Storage: \(row.uploadToZoteroStorage ? "true" : "false")")
                            .font(.caption)
                            .foregroundStyle(.secondary)
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
                        if let operation = row.zoteroOperation {
                            Text("Planned Zotero item: \(operation). \(row.zoteroItemKey ?? "Not created yet - this was a dry run.")")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(10)
                    .background(Color.white.opacity(0.38))
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
            }
        }
    }

    private struct IngestSummaryRow {
        let sourceFile: String
        let title: String
        let targetPath: String
        let storageMode: String
        let uploadToZoteroStorage: Bool
        let collections: [String]
        let tags: [String]
        let zoteroOperation: String?
        let zoteroItemKey: String?
    }

    private func latestIngestRows() -> [IngestSummaryRow] {
        let url = state.dataURL.appendingPathComponent("ingest_plan.json")
        guard let data = try? Data(contentsOf: url),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = json["items"] as? [[String: Any]] else {
            return []
        }
        return items.compactMap { item in
            guard let target = (item["planned_vault_path"] as? String) ?? (item["target_path"] as? String) else {
                return nil
            }
            let zotero = item["zotero"] as? [String: Any]
            return IngestSummaryRow(
                sourceFile: (item["source_file"] as? String) ?? (item["source_path"] as? String) ?? "unknown",
                title: item["title"] as? String ?? URL(fileURLWithPath: target).deletingPathExtension().lastPathComponent,
                targetPath: target,
                storageMode: item["storage_mode"] as? String ?? "linked-local",
                uploadToZoteroStorage: item["upload_to_zotero_storage"] as? Bool ?? false,
                collections: (item["planned_collections"] as? [String]) ?? (item["target_collections"] as? [String]) ?? [],
                tags: (item["planned_tags"] as? [String]) ?? (item["normalized_tags"] as? [String]) ?? [],
                zoteroOperation: (zotero?["operation"] as? String) ?? (item["zotero_action"] as? String),
                zoteroItemKey: zotero?["item_key"] as? String
            )
        }
    }

    private var elapsedResultLabel: String {
        if let elapsed = state.runner.finalProgressElapsedMS {
            return String(format: "Elapsed %.3fs", Double(elapsed) / 1000.0)
        }
        return String(format: "Elapsed %.1fs", state.runner.elapsedSeconds)
    }

    private func copyIngestSummary() {
        let rows = latestIngestRows()
        let summary = rows.map { row in
            """
            \(row.title)
            Source: \(row.sourceFile)
            Planned vault path: \(row.targetPath)
            Collections: \(row.collections.joined(separator: ", "))
            Tags: \(row.tags.joined(separator: ", "))
            """
        }.joined(separator: "\n\n")
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(summary.isEmpty ? state.shelfLastResult : summary, forType: .string)
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
        theme.border
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
