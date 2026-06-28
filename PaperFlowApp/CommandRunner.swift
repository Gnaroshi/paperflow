import AppKit
import Foundation
import UserNotifications

@MainActor
final class CommandRunner: ObservableObject {
    @Published private(set) var status: RunStatus = .idle
    @Published private(set) var output: String = ""
    @Published private(set) var currentCommand: String = ""
    @Published private(set) var currentLogFile: URL?
    @Published private(set) var queuedCount: Int = 0

    private var process: Process?
    private var timeoutTask: DispatchWorkItem?
    private var currentSpec: CommandSpec?
    private var queuedSpecs: [CommandSpec] = []

    var isRunning: Bool {
        status == .running
    }

    func run(_ spec: CommandSpec) {
        guard !isRunning else {
            if spec.isDestructive {
                append("Refusing destructive command while another command is running.\n")
            } else {
                queuedSpecs.append(spec)
                queuedCount = queuedSpecs.count
                append("Queued non-destructive command: \(spec.redactedDisplayCommand)\n")
            }
            return
        }
        runNow(spec)
    }

    private func runNow(_ spec: CommandSpec) {
        output = ""
        currentSpec = spec
        currentCommand = spec.redactedDisplayCommand
        currentLogFile = makeLogFileURL()
        append("$ \(currentCommand)\n\n")
        status = .running

        let process = Process()
        self.process = process
        process.executableURL = URL(fileURLWithPath: spec.executable)
        process.arguments = spec.arguments
        process.currentDirectoryURL = spec.workingDirectory
        process.environment = spec.environment

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe

        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else {
                return
            }
            DispatchQueue.main.async {
                self?.append(self?.currentSpec?.redact(text) ?? text)
            }
        }

        process.terminationHandler = { [weak self] finishedProcess in
            pipe.fileHandleForReading.readabilityHandler = nil
            DispatchQueue.main.async {
                self?.timeoutTask?.cancel()
                self?.timeoutTask = nil
                self?.process = nil
                self?.currentSpec = nil
                if finishedProcess.terminationReason == .exit && finishedProcess.terminationStatus == 0 {
                    self?.status = .succeeded(finishedProcess.terminationStatus)
                    self?.notify(title: "PaperFlow finished", body: "Command succeeded.")
                } else if self?.status == .timedOut {
                    self?.notify(title: "PaperFlow timed out", body: "Command was terminated after timeout.")
                } else {
                    self?.status = .failed(finishedProcess.terminationStatus)
                    self?.notify(title: "PaperFlow failed", body: "Exit code \(finishedProcess.terminationStatus).")
                }
                self?.runNextQueuedIfNeeded()
            }
        }

        do {
            try process.run()
        } catch {
            status = .failed(127)
            self.process = nil
            self.currentSpec = nil
            append("Failed to start process: \(error.localizedDescription)\n")
            notify(title: "PaperFlow failed to start", body: error.localizedDescription)
            runNextQueuedIfNeeded()
            return
        }

        let task = DispatchWorkItem { [weak self, weak process] in
            DispatchQueue.main.async {
                guard let self, self.status == .running else {
                    return
                }
                self.status = .timedOut
                self.append("\nCommand timed out and was terminated.\n")
                process?.terminate()
            }
        }
        timeoutTask = task
        DispatchQueue.global().asyncAfter(deadline: .now() + spec.timeoutSeconds, execute: task)
    }

    func cancel() {
        guard isRunning else {
            return
        }
        status = .cancelled
        append("\nCommand cancelled by user.\n")
        process?.terminate()
        process = nil
        currentSpec = nil
        timeoutTask?.cancel()
        timeoutTask = nil
        runNextQueuedIfNeeded()
    }

    func copyOutput() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(output, forType: .string)
    }

    func openLogFile() {
        guard let currentLogFile else {
            return
        }
        NSWorkspace.shared.open(currentLogFile)
    }

    private func append(_ text: String) {
        output += text
        guard let currentLogFile else {
            return
        }
        if let data = text.data(using: .utf8) {
            if FileManager.default.fileExists(atPath: currentLogFile.path),
               let handle = try? FileHandle(forWritingTo: currentLogFile) {
                defer { try? handle.close() }
                _ = try? handle.seekToEnd()
                _ = try? handle.write(contentsOf: data)
            } else {
                try? data.write(to: currentLogFile)
            }
        }
    }

    private func runNextQueuedIfNeeded() {
        guard !isRunning, process == nil, !queuedSpecs.isEmpty else {
            queuedCount = queuedSpecs.count
            return
        }
        let next = queuedSpecs.removeFirst()
        queuedCount = queuedSpecs.count
        runNow(next)
    }

    private func makeLogFileURL() -> URL {
        let directory = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/PaperFlow", isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd_HHmmss"
        return directory.appendingPathComponent("paperflow_\(formatter.string(from: Date())).log")
    }

    private func notify(title: String, body: String) {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }
}
