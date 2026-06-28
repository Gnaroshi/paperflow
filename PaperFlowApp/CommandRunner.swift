import AppKit
import Darwin
import Foundation
import UserNotifications

@MainActor
final class CommandRunner: ObservableObject {
    @Published private(set) var status: RunStatus = .idle
    @Published private(set) var output: String = ""
    @Published private(set) var currentCommand: String = ""
    @Published private(set) var currentLogFile: URL?
    @Published private(set) var queuedCount: Int = 0
    @Published private(set) var currentPID: Int32?
    @Published private(set) var currentWorkingDirectory: String = ""
    @Published private(set) var startedAt: Date?
    @Published private(set) var elapsedSeconds: TimeInterval = 0
    @Published private(set) var currentStage: String = ""
    @Published private(set) var lastHeartbeat: String = ""
    @Published private(set) var lastOutputAt: Date?
    @Published private(set) var noOutputWarning: String?
    @Published private(set) var stalledWarning = false
    @Published private(set) var completedStages: Set<String> = []
    @Published private(set) var stageMessages: [String: String] = [:]

    private var process: Process?
    private var timeoutTask: DispatchWorkItem?
    private var silenceTimer: DispatchSourceTimer?
    private var currentSpec: CommandSpec?
    private var queuedSpecs: [CommandSpec] = []
    private var progressLineBuffer = ""

    var isRunning: Bool {
        process != nil || status == .running
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
        progressLineBuffer = ""
        currentSpec = spec
        currentCommand = spec.redactedDisplayCommand
        currentWorkingDirectory = spec.workingDirectory.path
        currentLogFile = makeLogFileURL()
        currentPID = nil
        startedAt = Date()
        elapsedSeconds = 0
        lastOutputAt = Date()
        currentStage = ""
        lastHeartbeat = ""
        noOutputWarning = nil
        stalledWarning = false
        completedStages = []
        stageMessages = [:]
        append("$ \(currentCommand)\n\n")
        append("Working directory: \(currentWorkingDirectory)\n")
        status = .running

        let process = Process()
        self.process = process
        process.executableURL = URL(fileURLWithPath: spec.executable)
        process.arguments = spec.arguments
        process.currentDirectoryURL = spec.workingDirectory
        process.environment = spec.environment

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        stdoutPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else {
                return
            }
            DispatchQueue.main.async {
                self?.processOutput(text)
            }
        }

        stderrPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else {
                return
            }
            DispatchQueue.main.async {
                self?.processOutput(text)
            }
        }

        process.terminationHandler = { [weak self] finishedProcess in
            stdoutPipe.fileHandleForReading.readabilityHandler = nil
            stderrPipe.fileHandleForReading.readabilityHandler = nil
            DispatchQueue.main.async {
                self?.timeoutTask?.cancel()
                self?.timeoutTask = nil
                self?.silenceTimer?.cancel()
                self?.silenceTimer = nil
                self?.elapsedSeconds = Date().timeIntervalSince(self?.startedAt ?? Date())
                let finalStatus = self?.status
                self?.process = nil
                self?.currentSpec = nil
                self?.currentPID = nil
                if finalStatus == .cancelled {
                    self?.notify(title: "PaperFlow cancelled", body: "Command was cancelled.")
                } else if finalStatus == .timedOut {
                    self?.notify(title: "PaperFlow timed out", body: "Command was terminated after timeout.")
                } else if finishedProcess.terminationReason == .exit && finishedProcess.terminationStatus == 0 {
                    self?.status = .succeeded(finishedProcess.terminationStatus)
                    self?.notify(title: "PaperFlow finished", body: "Command succeeded.")
                } else {
                    self?.status = .failed(finishedProcess.terminationStatus)
                    self?.notify(title: "PaperFlow failed", body: "Exit code \(finishedProcess.terminationStatus).")
                }
                self?.runNextQueuedIfNeeded()
            }
        }

        do {
            try process.run()
            currentPID = process.processIdentifier
            append("PID: \(process.processIdentifier)\n\n")
            startSilenceTimer()
        } catch {
            status = .failed(127)
            self.process = nil
            self.currentSpec = nil
            self.currentPID = nil
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
                self.terminateThenKill(process)
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
        terminateThenKill(process)
        timeoutTask?.cancel()
        timeoutTask = nil
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

    private func processOutput(_ text: String) {
        lastOutputAt = Date()
        noOutputWarning = nil
        stalledWarning = false
        parseProgressJSONL(text)
        append(currentSpec?.redact(text) ?? text)
    }

    private func parseProgressJSONL(_ text: String) {
        progressLineBuffer += text
        while let newlineRange = progressLineBuffer.range(of: "\n") {
            let line = String(progressLineBuffer[..<newlineRange.lowerBound])
            progressLineBuffer.removeSubrange(progressLineBuffer.startIndex...newlineRange.lowerBound)
            parseProgressLine(line.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        if progressLineBuffer.count > 200_000 {
            progressLineBuffer = ""
        }
    }

    private func parseProgressLine(_ line: String) {
        guard line.hasPrefix("{"), line.hasSuffix("}"),
              let data = line.data(using: .utf8),
              let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let event = payload["event"] as? String else {
            return
        }
        let stage = payload["stage"] as? String ?? currentStage
        let message = payload["message"] as? String ?? ""
        if !stage.isEmpty {
            currentStage = stage
            if !message.isEmpty {
                stageMessages[stage] = message
            }
        }
        switch event {
        case "stage_finished", "stage_skipped":
            if !stage.isEmpty {
                completedStages.insert(stage)
            }
        case "heartbeat":
            lastHeartbeat = message
        case "done":
            completedStages.insert("done")
            currentStage = "done"
            lastHeartbeat = message
        default:
            break
        }
    }

    private func startSilenceTimer() {
        silenceTimer?.cancel()
        let timer = DispatchSource.makeTimerSource(queue: DispatchQueue.main)
        timer.schedule(deadline: .now() + 1, repeating: 1)
        timer.setEventHandler { [weak self] in
            Task { @MainActor in
                self?.refreshSilenceWarning()
            }
        }
        timer.resume()
        silenceTimer = timer
    }

    private func refreshSilenceWarning() {
        guard status == .running else {
            return
        }
        let now = Date()
        elapsedSeconds = now.timeIntervalSince(startedAt ?? now)
        let silence = now.timeIntervalSince(lastOutputAt ?? startedAt ?? now)
        if silence >= 30 {
            stalledWarning = true
            noOutputWarning = "No output for 30s. Process may be blocked in stage: \(currentStage.isEmpty ? "unknown" : currentStage)."
        } else if silence >= 10 {
            stalledWarning = false
            noOutputWarning = "No output for 10s. Process may be blocked in stage: \(currentStage.isEmpty ? "unknown" : currentStage)."
        }
    }

    private func terminateThenKill(_ runningProcess: Process?) {
        guard let runningProcess else {
            return
        }
        runningProcess.terminate()
        DispatchQueue.global().asyncAfter(deadline: .now() + 3) {
            if runningProcess.isRunning {
                kill(runningProcess.processIdentifier, SIGKILL)
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
        let prefix = currentSpec?.arguments.contains("ingest") == true ? "ingest" : "paperflow"
        return directory.appendingPathComponent("\(prefix)_\(formatter.string(from: Date())).log")
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
