import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct DropShelfView: View {
    @EnvironmentObject private var state: AppState
    @ObservedObject var controller: FloatingDropShelfController
    @State private var applyConfirmation = ""
    @State private var isTargeted = false
    @State private var processingStartedAt: Date?

    var body: some View {
        Group {
            if controller.isExpanded || state.dropShelfPhase != .idleCompact {
                expandedCard
            } else {
                compactPill
            }
        }
        .onDrop(of: [UTType.fileURL.identifier], isTargeted: $isTargeted) { providers in
            loadFileURLs(from: providers)
            return true
        }
        .onChange(of: isTargeted) { targeted in
            if targeted {
                controller.dragHover(valid: true)
            } else if state.dropShelfPhase == .hoveringValidPDF || state.dropShelfPhase == .hoveringInvalidFile {
                controller.dragExited()
            }
        }
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
                .stroke(borderColor.opacity(isTargeted ? 0.95 : 0.65), lineWidth: isTargeted ? 2 : 1)
        )
        .shadow(color: borderColor.opacity(isTargeted ? 0.35 : 0.12), radius: isTargeted ? 18 : 8)
        .scaleEffect(isTargeted ? 1.015 : 1)
        .animation(.easeOut(duration: 0.16), value: isTargeted)
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
            ProgressTimeline()
            TimelineView(.periodic(from: processingStartedAt ?? Date(), by: 1)) { context in
                Text("Elapsed: \(elapsedLabel(now: context.date))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(state.runner.currentCommand.isEmpty ? "paperflow command is running" : state.runner.currentCommand)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .truncationMode(.middle)
            Text(logTail(maxLines: 5).isEmpty ? "Waiting for command output..." : logTail(maxLines: 5))
                .font(.system(.caption, design: .monospaced))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, minHeight: 54, alignment: .topLeading)
                .padding(8)
                .background(Color(nsColor: .textBackgroundColor).opacity(0.8))
                .clipShape(RoundedRectangle(cornerRadius: 8))
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
                        Text("Planned collections: set by Zotero Organize after ingest")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text("Planned tags: set by Zotero Organize after ingest")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private struct IngestSummaryRow {
        let title: String
        let targetPath: String
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
                targetPath: target
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
        let seconds = max(0, Int(now.timeIntervalSince(processingStartedAt ?? now)))
        return "\(seconds / 60)m \(seconds % 60)s"
    }

    private struct ProgressTimeline: View {
        var body: some View {
            HStack(spacing: 8) {
                TimelineStep(label: "Queued", filled: true)
                Rectangle().fill(Color.accentColor.opacity(0.5)).frame(height: 2)
                TimelineStep(label: "Running", filled: true)
                Rectangle().fill(Color.secondary.opacity(0.35)).frame(height: 2)
                TimelineStep(label: "Report", filled: false)
            }
        }
    }

    private struct TimelineStep: View {
        let label: String
        let filled: Bool

        var body: some View {
            HStack(spacing: 4) {
                Circle()
                    .fill(filled ? Color.accentColor : Color.secondary.opacity(0.3))
                    .frame(width: 9, height: 9)
                Text(label)
                    .font(.caption2)
                    .foregroundStyle(filled ? .primary : .secondary)
            }
        }
    }
    private var dropTarget: some View {
        VStack(spacing: 6) {
            Image(systemName: "doc.badge.plus")
                .font(.title2)
            Text("Drop PDFs here")
                .font(.subheadline)
                .fontWeight(.medium)
            Text("linked-local only; no Zotero Storage upload")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, minHeight: 92)
        .background(Color.accentColor.opacity(isTargeted ? 0.16 : 0.08))
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.accentColor.opacity(0.35), style: StrokeStyle(lineWidth: 1, dash: [5]))
        )
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

    private func loadFileURLs(from providers: [NSItemProvider]) {
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
            controller.handleDropped(urls)
        }
    }
}
