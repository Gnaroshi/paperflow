import SwiftUI
import UniformTypeIdentifiers

struct DropShelfView: View {
    @EnvironmentObject private var state: AppState
    @ObservedObject var controller: FloatingDropShelfController
    @State private var applyConfirmation = ""
    @State private var isTargeted = false

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
        .onChange(of: state.runner.status) { status in
            switch status {
            case .running:
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
    }

    private var expandedCard: some View {
        VStack(alignment: .leading, spacing: 14) {
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

            dropTarget

            if !state.droppedPDFs.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("\(state.droppedPDFs.count) PDF file(s)")
                        .font(.subheadline)
                        .fontWeight(.medium)
                    ForEach(state.droppedPDFs.prefix(5)) { file in
                        Text(file.name)
                            .font(.caption)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                    if state.droppedPDFs.count > 5 {
                        Text("+ \(state.droppedPDFs.count - 5) more")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            if !state.invalidDropWarnings.isEmpty {
                ForEach(state.invalidDropWarnings, id: \.self) { warning in
                    Text(warning)
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
            }

            Picker("Target action", selection: $state.dropShelfAction) {
                ForEach(DropShelfAction.allCases) { action in
                    Text(action.label).tag(action)
                }
            }

            Toggle("Store in local vault", isOn: $state.shelfStoreInLocalVault)
            Toggle("Link to Zotero, do not upload", isOn: $state.shelfLinkToZoteroNoUpload)

            if state.dropShelfAction == .applyIngest {
                TextField("Type INGEST LOCAL PDFS", text: $applyConfirmation)
                    .textFieldStyle(.roundedBorder)
            }

            HStack {
                Button {
                    state.dropShelfAction = .dryRunIngest
                    state.runDropShelfSelectedAction()
                } label: {
                    Label("Run Dry Run", systemImage: "play.circle")
                }
                .buttonStyle(.borderedProminent)
                .disabled(state.droppedPDFs.isEmpty || state.runner.isRunning)

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

                Button("Clear") {
                    state.clearPDFs()
                    state.dropShelfPhase = .idleCompact
                    state.shelfLastResult = "Ready"
                    applyConfirmation = ""
                }
                .disabled(state.runner.isRunning)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(borderColor.opacity(0.55), lineWidth: 1)
        )
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
