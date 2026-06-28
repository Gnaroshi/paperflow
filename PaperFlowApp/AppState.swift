import AppKit
import Foundation
import ServiceManagement

@MainActor
final class AppState: ObservableObject {
    @Published var selectedSection: AppSection = .dashboard
    @Published var droppedPDFs: [DroppedPDF] = []
    @Published var invalidDropWarnings: [String] = []
    @Published var defaultMode: DefaultRunMode = .dryRun {
        didSet { defaults.set(defaultMode.rawValue, forKey: "defaultMode") }
    }
    @Published var collectionMode: CollectionMode = .replaceAll {
        didSet { defaults.set(collectionMode.rawValue, forKey: "collectionMode") }
    }
    @Published var tagMode: TagMode = .replaceManaged {
        didSet { defaults.set(tagMode.rawValue, forKey: "tagMode") }
    }
    @Published var dropShelfActivationMode: DropShelfActivationMode = .keyboardShortcutOnly {
        didSet {
            defaults.set(dropShelfActivationMode.rawValue, forKey: "dropShelfActivationMode")
            AppServices.shared.reconfigureHotZones()
            AppServices.shared.shelfController?.applyActivationMode()
        }
    }
    @Published var dropShelfPlacement: DropShelfPlacement = .bottomCenter {
        didSet { defaults.set(dropShelfPlacement.rawValue, forKey: "dropShelfPlacement") }
    }
    @Published var displayMode: DisplayMode = .focusedMonitor {
        didSet {
            defaults.set(displayMode.rawValue, forKey: "displayMode")
            AppServices.shared.reconfigureHotZones()
        }
    }
    @Published var focusedMonitorStrategy: FocusedMonitorStrategy = .cursorScreen {
        didSet { defaults.set(focusedMonitorStrategy.rawValue, forKey: "focusedMonitorStrategy") }
    }
    @Published var hotZoneEnabled = false {
        didSet {
            defaults.set(hotZoneEnabled, forKey: "hotZoneEnabled")
            AppServices.shared.reconfigureHotZones()
        }
    }
    @Published var hotZoneEdge: HotZoneEdge = .right {
        didSet {
            defaults.set(hotZoneEdge.rawValue, forKey: "hotZoneEdge")
            AppServices.shared.reconfigureHotZones()
        }
    }
    @Published var hotZoneCorner: HotZoneCorner = .bottomRight {
        didSet {
            defaults.set(hotZoneCorner.rawValue, forKey: "hotZoneCorner")
            AppServices.shared.reconfigureHotZones()
        }
    }
    @Published var hotZoneWidth: Double = 12 {
        didSet {
            defaults.set(hotZoneWidth, forKey: "hotZoneWidth")
            AppServices.shared.reconfigureHotZones()
        }
    }
    @Published var hotZoneHeight: Double = 160 {
        didSet {
            defaults.set(hotZoneHeight, forKey: "hotZoneHeight")
            AppServices.shared.reconfigureHotZones()
        }
    }
    @Published var hotZoneIdleOpacity: Double = 0.12 {
        didSet {
            defaults.set(hotZoneIdleOpacity, forKey: "hotZoneIdleOpacity")
            AppServices.shared.reconfigureHotZones()
        }
    }
    @Published var autoCollapseDelay: Double = 4 {
        didSet { defaults.set(autoCollapseDelay, forKey: "autoCollapseDelay") }
    }
    @Published var autoHideAfterSuccess = true {
        didSet { defaults.set(autoHideAfterSuccess, forKey: "autoHideAfterSuccess") }
    }
    @Published var autoDryRunAfterDrop = false {
        didSet { defaults.set(autoDryRunAfterDrop, forKey: "autoDryRunAfterDrop") }
    }
    @Published var apiKeyStorageMode: APIKeyStorageMode = .keychain {
        didSet { defaults.set(apiKeyStorageMode.rawValue, forKey: "apiKeyStorageMode") }
    }
    @Published var storageModeSetting: StorageModeSetting = .linkedLocalOnly {
        didSet { defaults.set(storageModeSetting.rawValue, forKey: "storageModeSetting") }
    }
    @Published var neverUploadPDFsToZoteroStorage = true {
        didSet { defaults.set(neverUploadPDFsToZoteroStorage, forKey: "neverUploadPDFsToZoteroStorage") }
    }
    @Published var globalShortcutCommand = "Option + Space"
    @Published var dropShelfShortcut = "⌃⇧⌘+"
    @Published var dropShelfPhase: DropShelfPhase = .idleCompact
    @Published var dropShelfAction: DropShelfAction = .dryRunIngest
    @Published var shelfStoreInLocalVault = true
    @Published var shelfLinkToZoteroNoUpload = true
    @Published var shelfLastResult = "Ready"
    @Published var projectPath: String {
        didSet {
            defaults.set(projectPath, forKey: "projectPath")
            refreshStatus()
        }
    }
    @Published var uvPath: String {
        didSet { defaults.set(uvPath, forKey: "uvPath") }
    }
    @Published var vaultPath: String {
        didSet {
            defaults.set(vaultPath, forKey: "vaultPath")
            refreshVaultStatus()
        }
    }
    @Published var zoteroUserID: String {
        didSet { KeychainStore.write(zoteroUserID, account: "ZOTERO_USER_ID") }
    }
    @Published var zoteroAPIKey: String {
        didSet { KeychainStore.write(zoteroAPIKey, account: "ZOTERO_API_KEY") }
    }
    @Published var pendingZoteroAPIKey = ""
    @Published var zoteroUsername: String {
        didSet { defaults.set(zoteroUsername, forKey: "zoteroUsername") }
    }
    @Published var zoteroVerification = ZoteroCredentialStatus()
    @Published var geminiAPIKey: String {
        didSet { KeychainStore.write(geminiAPIKey, account: "GEMINI_API_KEY") }
    }
    @Published var pendingGeminiAPIKey = ""
    @Published var geminiModel: String {
        didSet { defaults.set(geminiModel, forKey: "geminiModel") }
    }
    @Published var customGeminiModel: String {
        didSet { defaults.set(customGeminiModel, forKey: "customGeminiModel") }
    }
    @Published var geminiCleanupEnabled: Bool {
        didSet { defaults.set(geminiCleanupEnabled, forKey: "geminiCleanupEnabled") }
    }
    @Published var stopOnGeminiQuotaHit: Bool {
        didSet { defaults.set(stopOnGeminiQuotaHit, forKey: "stopOnGeminiQuotaHit") }
    }
    @Published var enableGeminiAbstractExtraction: Bool {
        didSet { defaults.set(enableGeminiAbstractExtraction, forKey: "enableGeminiAbstractExtraction") }
    }
    @Published var enableGeminiMetadataExtraction: Bool {
        didSet { defaults.set(enableGeminiMetadataExtraction, forKey: "enableGeminiMetadataExtraction") }
    }
    @Published var enableGeminiClassificationReview: Bool {
        didSet { defaults.set(enableGeminiClassificationReview, forKey: "enableGeminiClassificationReview") }
    }
    @Published var requireManualApprovalForGeminiRepairs: Bool {
        didSet { defaults.set(requireManualApprovalForGeminiRepairs, forKey: "requireManualApprovalForGeminiRepairs") }
    }
    @Published var neverOverwriteExistingAbstract: Bool {
        didSet { defaults.set(neverOverwriteExistingAbstract, forKey: "neverOverwriteExistingAbstract") }
    }
    @Published var neverDeleteDuplicateWithReadingWork: Bool {
        didSet { defaults.set(neverDeleteDuplicateWithReadingWork, forKey: "neverDeleteDuplicateWithReadingWork") }
    }
    @Published var geminiVerification = GeminiCredentialStatus()
    @Published var geminiUsage = GeminiUsageSummary()
    @Published var launchAtLogin = false
    @Published var dashboard = DashboardSummary()
    @Published var vaultStatus: VaultStatus
    @Published var backend = BackendCapability(
        ingestLinkedLocal: true,
        vaultCommands: true,
        localizeAttachmentCommands: true
    )
    @Published var linkedAttachmentInstructionsShown: Bool {
        didSet {
            defaults.set(linkedAttachmentInstructionsShown, forKey: "linkedAttachmentInstructionsShown")
            refreshVaultStatus()
        }
    }

    let runner = CommandRunner()
    private let defaults = UserDefaults.standard

    init() {
        let defaultProject = Self.defaultProjectPath()
        let defaultVault = Self.defaultVaultPath()
        projectPath = defaults.string(forKey: "projectPath") ?? defaultProject
        uvPath = defaults.string(forKey: "uvPath") ?? Self.defaultUVPath()
        vaultPath = defaults.string(forKey: "vaultPath") ?? defaultVault
        linkedAttachmentInstructionsShown = defaults.bool(forKey: "linkedAttachmentInstructionsShown")
        vaultStatus = VaultStatus(path: defaults.string(forKey: "vaultPath") ?? defaultVault)
        zoteroUserID = KeychainStore.read("ZOTERO_USER_ID")
        zoteroAPIKey = KeychainStore.read("ZOTERO_API_KEY")
        zoteroUsername = defaults.string(forKey: "zoteroUsername") ?? ""
        geminiAPIKey = KeychainStore.read("GEMINI_API_KEY")
        geminiModel = defaults.string(forKey: "geminiModel") ?? "gemini-2.5-flash"
        customGeminiModel = defaults.string(forKey: "customGeminiModel") ?? ""
        geminiCleanupEnabled = defaults.object(forKey: "geminiCleanupEnabled") as? Bool ?? false
        stopOnGeminiQuotaHit = defaults.object(forKey: "stopOnGeminiQuotaHit") as? Bool ?? true
        enableGeminiAbstractExtraction = defaults.object(forKey: "enableGeminiAbstractExtraction") as? Bool ?? false
        enableGeminiMetadataExtraction = defaults.object(forKey: "enableGeminiMetadataExtraction") as? Bool ?? false
        enableGeminiClassificationReview = defaults.object(forKey: "enableGeminiClassificationReview") as? Bool ?? false
        requireManualApprovalForGeminiRepairs = defaults.object(forKey: "requireManualApprovalForGeminiRepairs") as? Bool ?? true
        neverOverwriteExistingAbstract = defaults.object(forKey: "neverOverwriteExistingAbstract") as? Bool ?? true
        neverDeleteDuplicateWithReadingWork = defaults.object(forKey: "neverDeleteDuplicateWithReadingWork") as? Bool ?? true

        if let savedMode = defaults.string(forKey: "defaultMode"),
           let mode = DefaultRunMode(rawValue: savedMode) {
            defaultMode = mode
        }
        if let savedCollectionMode = defaults.string(forKey: "collectionMode"),
           let mode = CollectionMode(rawValue: savedCollectionMode) {
            collectionMode = mode
        }
        if let savedTagMode = defaults.string(forKey: "tagMode"),
           let mode = TagMode(rawValue: savedTagMode) {
            tagMode = mode
        }
        if let value = defaults.string(forKey: "displayMode"),
           let mode = DisplayMode(rawValue: value) {
            displayMode = mode
        }
        if let value = defaults.string(forKey: "focusedMonitorStrategy"),
           let strategy = FocusedMonitorStrategy(rawValue: value) {
            focusedMonitorStrategy = strategy
        }
        if defaults.object(forKey: "hotZoneEnabled") != nil {
            hotZoneEnabled = defaults.bool(forKey: "hotZoneEnabled")
        }
        if let value = defaults.string(forKey: "hotZoneEdge"),
           let edge = HotZoneEdge(rawValue: value) {
            hotZoneEdge = edge
        }
        if let value = defaults.string(forKey: "hotZoneCorner"),
           let corner = HotZoneCorner(rawValue: value) {
            hotZoneCorner = corner
        }
        if defaults.object(forKey: "hotZoneWidth") != nil {
            hotZoneWidth = defaults.double(forKey: "hotZoneWidth")
        }
        if defaults.object(forKey: "hotZoneHeight") != nil {
            hotZoneHeight = defaults.double(forKey: "hotZoneHeight")
        }
        if defaults.object(forKey: "hotZoneIdleOpacity") != nil {
            hotZoneIdleOpacity = defaults.double(forKey: "hotZoneIdleOpacity")
        }
        if defaults.object(forKey: "autoCollapseDelay") != nil {
            autoCollapseDelay = defaults.double(forKey: "autoCollapseDelay")
        }
        if let value = defaults.string(forKey: "apiKeyStorageMode"),
           let mode = APIKeyStorageMode(rawValue: value) {
            apiKeyStorageMode = mode
        }
        if let value = defaults.string(forKey: "dropShelfActivationMode"),
           let mode = DropShelfActivationMode(rawValue: value) {
            dropShelfActivationMode = mode
        }
        if let value = defaults.string(forKey: "dropShelfPlacement"),
           let placement = DropShelfPlacement(rawValue: value) {
            dropShelfPlacement = placement
        }
        if let value = defaults.string(forKey: "storageModeSetting"),
           let mode = StorageModeSetting(rawValue: value) {
            storageModeSetting = mode
        }
        if defaults.object(forKey: "neverUploadPDFsToZoteroStorage") != nil {
            neverUploadPDFsToZoteroStorage = defaults.bool(forKey: "neverUploadPDFsToZoteroStorage")
        }
        if defaults.object(forKey: "autoHideAfterSuccess") != nil {
            autoHideAfterSuccess = defaults.bool(forKey: "autoHideAfterSuccess")
        }
        if defaults.object(forKey: "autoDryRunAfterDrop") != nil {
            autoDryRunAfterDrop = defaults.bool(forKey: "autoDryRunAfterDrop")
        }

        restoreZoteroVerification()
        refreshStatus()
    }

    var projectURL: URL {
        URL(fileURLWithPath: NSString(string: projectPath).expandingTildeInPath)
    }

    var dataURL: URL {
        projectURL.appendingPathComponent("data", isDirectory: true)
    }

    var vaultURL: URL {
        URL(fileURLWithPath: NSString(string: vaultPath).expandingTildeInPath)
    }

    var logsURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/PaperFlow", isDirectory: true)
    }

    var redactedAPIKey: String {
        redactSecret(zoteroAPIKey, prefix: "zotero")
    }

    var redactedGeminiAPIKey: String {
        redactSecret(geminiAPIKey, prefix: "gemini")
    }

    var selectedGeminiModel: String {
        geminiModel == "custom" ? customGeminiModel : geminiModel
    }

    var zoteroConnectionStatus: String {
        if zoteroUserID.isEmpty || zoteroAPIKey.isEmpty {
            return "Credentials not configured"
        }
        if !zoteroUserID.allSatisfy(\.isNumber) {
            return "User ID must be numeric"
        }
        return "Configured"
    }

    var geminiConnectionStatus: String {
        if geminiVerification.rateLimited {
            return "Rate-limited"
        }
        if geminiVerification.verified {
            return "Verified"
        }
        return geminiAPIKey.isEmpty ? "Not configured" : "Stored, not verified"
    }

    var statusText: String {
        runner.status.label
    }

    func refreshStatus() {
        refreshDashboard()
        refreshVaultStatus()
        refreshGeminiUsage()
    }

    func refreshDashboard() {
        var summary = DashboardSummary()

        if let migration = readJSON(dataURL.appendingPathComponent("migration_plan.json")) {
            if let stats = migration["stats"] as? [String: Any] {
                summary.sourceItems = stats["source_items"] as? Int ?? 0
                summary.plannedItems = stats["planned_items"] as? Int ?? 0
                summary.missingMetadataItems = stats["missing_metadata"] as? Int ?? 0
                summary.missingAbstractItems = stats["missing_abstract"] as? Int ?? 0
                summary.duplicateCandidates = stats["duplicate_candidates"] as? Int ?? 0
                summary.nonPaperItems = stats["non_paper_items"] as? Int ?? 0
            }
            if let items = migration["items"] as? [[String: Any]] {
                summary.lowConfidenceItems = items.filter { ($0["confidence"] as? Double ?? 1.0) < 0.55 }.count
            }
            summary.latestMigrationStatus = statusLine(for: dataURL.appendingPathComponent("migration_plan.json"))
        }

        if let preview = readJSON(dataURL.appendingPathComponent("apply_preview.json")) {
            summary.itemUpdates = (preview["item_updates"] as? [[String: Any]])?.count ?? 0
            summary.collectionsToCreate = (preview["collections_to_create"] as? [[String: Any]])?.count ?? 0
            summary.oldCollectionsWouldBeEmpty = (preview["old_collections_that_would_be_empty"] as? [[String: Any]])?.count ?? 0
        }

        if let dedupe = readJSON(dataURL.appendingPathComponent("dedupe_plan.json")),
           let groups = dedupe["groups"] as? [[String: Any]] {
            summary.duplicateCandidates = groups.reduce(0) { count, group in
                let items = group["items"] as? [[String: Any]] ?? []
                return count + items.filter { !($0["is_canonical"] as? Bool ?? false) }.count
            }
        }

        summary.latestApplyStatus = latestFileStatus(prefix: "apply_log_", suffix: ".md") ?? "No apply log found"
        summary.latestCleanupStatus = statusLine(for: dataURL.appendingPathComponent("cleanup_report.md"))
        summary.latestMigrationAuditStatus = statusLine(for: dataURL.appendingPathComponent("migration_audit.md"))
        summary.latestStoredPDFLocalizationStatus =
            statusLine(for: dataURL.appendingPathComponent("localize_verify_report.md"))
        dashboard = summary
    }

    func refreshGeminiUsage() {
        let today = todayString()
        let usageURL = dataURL.appendingPathComponent("gemini_usage_\(today).json")
        guard let usage = readJSON(usageURL) else {
            geminiUsage = GeminiUsageSummary(date: today)
            return
        }
        geminiUsage = GeminiUsageSummary(
            date: usage["date"] as? String ?? today,
            requestCount: usage["request_count"] as? Int ?? 0,
            inputTokens: usage["input_tokens"] as? Int ?? 0,
            outputTokens: usage["output_tokens"] as? Int ?? 0,
            totalTokens: usage["total_tokens"] as? Int ?? 0,
            failedRateLimitCalls: usage["failed_rate_limit_calls"] as? Int ?? 0,
            last429Time: usage["last_429_resource_exhausted_time"] as? String
        )
        if geminiUsage.failedRateLimitCalls > 0 {
            geminiVerification.rateLimited = true
            geminiVerification.message = "Gemini Flash is currently rate-limited. Try later or reduce batch size."
        }
    }

    func refreshVaultStatus() {
        var status = VaultStatus(path: vaultPath)
        status.instructionsShown = linkedAttachmentInstructionsShown
        var isDirectory: ObjCBool = false
        status.exists = FileManager.default.fileExists(atPath: vaultURL.path, isDirectory: &isDirectory) && isDirectory.boolValue

        guard status.exists,
              let enumerator = FileManager.default.enumerator(
                at: vaultURL,
                includingPropertiesForKeys: [.isRegularFileKey, .fileSizeKey],
                options: [.skipsHiddenFiles]
              ) else {
            vaultStatus = status
            return
        }

        for case let fileURL as URL in enumerator {
            let values = try? fileURL.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
            if values?.isRegularFile == true {
                status.fileCount += 1
                if fileURL.pathExtension.lowercased() == "pdf" {
                    status.pdfCount += 1
                }
                status.totalBytes += UInt64(values?.fileSize ?? 0)
            }
        }
        status.lastIngest = latestFileStatus(prefix: "ingest", suffix: ".json")
            ?? latestFileStatus(prefix: "ingest_apply_log", suffix: ".json")
            ?? "No ingest log found"
        vaultStatus = status
    }

    func addDroppedURLs(_ urls: [URL]) {
        invalidDropWarnings.removeAll()
        var existing = Set(droppedPDFs.map(\.url))
        for url in urls {
            if url.pathExtension.lowercased() == "pdf" {
                if !existing.contains(url) {
                    droppedPDFs.append(DroppedPDF(url: url))
                    existing.insert(url)
                }
            } else {
                invalidDropWarnings.append("Ignored non-PDF: \(url.lastPathComponent)")
            }
        }
    }

    func removePDFs(at offsets: IndexSet) {
        for index in offsets.sorted(by: >) {
            droppedPDFs.remove(at: index)
        }
    }

    func removePDF(_ pdf: DroppedPDF) {
        droppedPDFs.removeAll { $0.id == pdf.id }
        if droppedPDFs.isEmpty, dropShelfPhase != .processing {
            dropShelfPhase = .idleCompact
        }
    }

    func clearPDFs() {
        droppedPDFs.removeAll()
        invalidDropWarnings.removeAll()
    }

    func chooseProjectDirectory() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.directoryURL = projectURL
        if panel.runModal() == .OK, let url = panel.url {
            projectPath = url.path
        }
    }

    func chooseUVExecutable() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.directoryURL = URL(fileURLWithPath: "/opt/homebrew/bin")
        if panel.runModal() == .OK, let url = panel.url {
            uvPath = url.path
        }
    }

    func chooseVaultDirectory() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.directoryURL = vaultURL
        if panel.runModal() == .OK, let url = panel.url {
            vaultPath = url.path
        }
    }

    func saveUnverifiedZoteroAPIKey() {
        zoteroAPIKey = pendingZoteroAPIKey.trimmingCharacters(in: .whitespacesAndNewlines)
        pendingZoteroAPIKey = ""
        zoteroVerification = ZoteroCredentialStatus(
            verified: false,
            message: "Saved without verification",
            numericUserID: zoteroUserID,
            username: zoteroUsername,
            libraryAccess: false,
            writeAccess: false,
            notesAccess: false,
            filesAccess: false
        )
        persistZoteroVerification(zoteroVerification)
    }

    func verifyAndSaveZoteroAPIKey() {
        let candidate = pendingZoteroAPIKey.trimmingCharacters(in: .whitespacesAndNewlines)
        let key = candidate.isEmpty ? zoteroAPIKey : candidate
        guard !key.isEmpty else {
            zoteroVerification.message = "Enter a Zotero API key first."
            return
        }
        zoteroVerification.message = "Verifying..."
        Task {
            do {
                var request = URLRequest(url: URL(string: "https://api.zotero.org/keys/current")!)
                request.setValue(key, forHTTPHeaderField: "Zotero-API-Key")
                let (data, response) = try await URLSession.shared.data(for: request)
                let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
                guard (200..<300).contains(statusCode) else {
                    zoteroVerification = ZoteroCredentialStatus(
                        verified: false,
                        message: "Verification failed with HTTP \(statusCode)",
                        numericUserID: zoteroUserID,
                        username: zoteroUsername,
                        libraryAccess: false,
                        writeAccess: false,
                        notesAccess: false,
                        filesAccess: false
                    )
                    return
                }
                guard
                    let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                    let parsed = parseZoteroKeyResponse(json)
                else {
                    zoteroVerification.message = "Verification response could not be parsed."
                    return
                }
                zoteroAPIKey = key
                pendingZoteroAPIKey = ""
                zoteroUserID = parsed.numericUserID
                zoteroUsername = parsed.username
                zoteroVerification = parsed
                persistZoteroVerification(parsed)
            } catch {
                zoteroVerification = ZoteroCredentialStatus(
                    verified: false,
                    message: "Verification failed: \(error.localizedDescription)",
                    numericUserID: zoteroUserID,
                    username: zoteroUsername,
                    libraryAccess: false,
                    writeAccess: false,
                    notesAccess: false,
                    filesAccess: false
                )
            }
        }
    }

    func saveUnverifiedGeminiAPIKey() {
        geminiAPIKey = pendingGeminiAPIKey.trimmingCharacters(in: .whitespacesAndNewlines)
        pendingGeminiAPIKey = ""
        geminiVerification = GeminiCredentialStatus(
            verified: false,
            rateLimited: false,
            message: "Saved without verification",
            model: selectedGeminiModel
        )
    }

    func verifyAndSaveGeminiAPIKey() {
        let candidate = pendingGeminiAPIKey.trimmingCharacters(in: .whitespacesAndNewlines)
        let key = candidate.isEmpty ? geminiAPIKey : candidate
        let model = selectedGeminiModel.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else {
            geminiVerification.message = "Enter a Gemini API key first."
            return
        }
        guard !model.isEmpty else {
            geminiVerification.message = "Choose a Gemini model."
            return
        }
        geminiVerification.message = "Verifying..."
        Task {
            do {
                var components = URLComponents(
                    string: "https://generativelanguage.googleapis.com/v1beta/models/\(model):generateContent"
                )!
                components.queryItems = [URLQueryItem(name: "key", value: key)]
                var request = URLRequest(url: components.url!)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = try JSONSerialization.data(withJSONObject: [
                    "contents": [
                        ["parts": [["text": "Reply with the single word OK."]]]
                    ]
                ])
                let (data, response) = try await URLSession.shared.data(for: request)
                let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
                let payload = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
                if statusCode == 429 || geminiStatus(payload) == "RESOURCE_EXHAUSTED" {
                    recordLocalGeminiUsage(errorType: "rate_limited")
                    geminiVerification = GeminiCredentialStatus(
                        verified: false,
                        rateLimited: true,
                        message: "Gemini quota/rate limit reached",
                        model: model
                    )
                    return
                }
                if statusCode == 401 || statusCode == 403 {
                    recordLocalGeminiUsage(errorType: "invalid_key")
                    geminiVerification = GeminiCredentialStatus(
                        verified: false,
                        rateLimited: false,
                        message: "Invalid or unauthorized Gemini API key",
                        model: model
                    )
                    return
                }
                guard (200..<300).contains(statusCode) else {
                    recordLocalGeminiUsage(errorType: statusCode >= 500 ? "service_error" : "request_failed")
                    geminiVerification = GeminiCredentialStatus(
                        verified: false,
                        rateLimited: false,
                        message: statusCode >= 500 ? "Gemini service error" : "Gemini request failed",
                        model: model
                    )
                    return
                }
                recordLocalGeminiUsage(payload: payload)
                geminiAPIKey = key
                pendingGeminiAPIKey = ""
                geminiVerification = GeminiCredentialStatus(
                    verified: true,
                    rateLimited: false,
                    message: "Verified",
                    model: model
                )
            } catch {
                geminiVerification = GeminiCredentialStatus(
                    verified: false,
                    rateLimited: false,
                    message: "Verification failed: \(error.localizedDescription)",
                    model: model
                )
            }
        }
    }

    func setLaunchAtLogin(_ enabled: Bool) {
        launchAtLogin = enabled
        if #available(macOS 13.0, *) {
            do {
                if enabled {
                    try SMAppService.mainApp.register()
                } else {
                    try SMAppService.mainApp.unregister()
                }
            } catch {
                invalidDropWarnings.append("Launch at login could not be changed: \(error.localizedDescription)")
                launchAtLogin = false
            }
        }
    }

    func runBackupZotero() {
        runZotero(arguments: ["backup"], timeoutSeconds: 1800)
    }

    func runEnrichMetadata() {
        runZotero(arguments: ["enrich-metadata"], timeoutSeconds: 1800)
    }

    func runDetectDuplicates() {
        runZotero(arguments: ["detect-duplicates"], timeoutSeconds: 1800)
    }

    func runPlanMigration() {
        runZotero(arguments: ["plan-migration"], timeoutSeconds: 1800)
    }

    func runDryRunMigration() {
        runZotero(arguments: ["dry-run-migration"], timeoutSeconds: 1800)
    }

    func runApplyMigration() {
        runZotero(
            arguments: [
                "apply-migration",
                "--collection-mode", collectionMode.rawValue,
                "--tag-mode", tagMode.rawValue,
                "--apply",
                "--confirm", "REPLACE MY ZOTERO COLLECTIONS"
            ],
            timeoutSeconds: 3600,
            destructive: true
        )
    }

    func runCleanupDeleteEmpty() {
        runZotero(
            arguments: [
                "cleanup-collections",
                "--mode", "delete-empty",
                "--apply",
                "--confirm", "DELETE EMPTY OLD COLLECTIONS"
            ],
            timeoutSeconds: 1800,
            destructive: true
        )
    }

    func runDryRunIngest() {
        guard backend.ingestLinkedLocal else {
            invalidDropWarnings = ["Backend missing: paperflow ingest --storage-mode linked-local is not implemented yet."]
            return
        }
        guard !droppedPDFs.isEmpty else {
            invalidDropWarnings = ["Drop at least one PDF first."]
            return
        }
        let args = ["run", "paperflow", "ingest"] + droppedPDFs.map { $0.url.path } + ["--dry-run", "--storage-mode", "linked-local"]
        runUV(arguments: args, timeoutSeconds: 1800)
    }

    func runApplyIngest() {
        guard backend.ingestLinkedLocal else {
            invalidDropWarnings = ["Backend missing: paperflow ingest --storage-mode linked-local is not implemented yet."]
            return
        }
        guard !droppedPDFs.isEmpty else {
            invalidDropWarnings = ["Drop at least one PDF first."]
            return
        }
        let args = ["run", "paperflow", "ingest"] + droppedPDFs.map { $0.url.path } + ["--apply", "--storage-mode", "linked-local"]
        runUV(arguments: args, timeoutSeconds: 1800, destructive: true)
    }

    func runVaultInit() {
        runUV(arguments: ["run", "paperflow", "vault", "init"], timeoutSeconds: 600)
    }

    func runVaultPlanPaths() {
        runUV(arguments: ["run", "paperflow", "vault", "plan-paths"], timeoutSeconds: 600)
    }

    func runPlanLocalizeAttachments() {
        runZotero(arguments: ["plan-localize-attachments"], timeoutSeconds: 1800)
    }

    func runApplyLocalizeAttachments() {
        runZotero(
            arguments: [
                "apply-localize-attachments",
                "--apply",
                "--confirm", "LOCALIZE ZOTERO PDF ATTACHMENTS"
            ],
            timeoutSeconds: 3600,
            destructive: true
        )
    }

    func runVerifyLocalizedAttachments() {
        runZotero(arguments: ["verify-localized-attachments"], timeoutSeconds: 1800)
    }

    func runCleanupStoredAttachments() {
        runZotero(
            arguments: [
                "cleanup-stored-attachments",
                "--apply",
                "--confirm", "DELETE OLD STORED PDF ATTACHMENTS"
            ],
            timeoutSeconds: 1800,
            destructive: true
        )
    }

    func runRepairAbstractsDryRun() {
        var args = ["run", "paperflow", "cleanup", "repair-abstracts", "--dry-run"]
        if geminiCleanupEnabled && enableGeminiAbstractExtraction {
            args += ["--enable-gemini", "--gemini-model", selectedGeminiModel]
        }
        runUV(arguments: args, timeoutSeconds: 1800)
    }

    func runRepairAbstractDryRun(itemKey: String) {
        let key = itemKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else {
            invalidDropWarnings = ["Select an abstract item first."]
            return
        }
        var args = ["run", "paperflow", "cleanup", "repair-abstracts", "--dry-run", "--item-key", key]
        if geminiCleanupEnabled && enableGeminiAbstractExtraction {
            args += ["--enable-gemini", "--gemini-model", selectedGeminiModel]
        }
        runUV(arguments: args, timeoutSeconds: 1800)
    }

    func runApplyAbstractRepairs() {
        var args = [
            "run", "paperflow", "cleanup", "repair-abstracts",
            "--apply",
            "--confirm", "APPLY ABSTRACT REPAIRS"
        ]
        if geminiCleanupEnabled && enableGeminiAbstractExtraction {
            args += ["--enable-gemini", "--gemini-model", selectedGeminiModel]
        }
        runUV(arguments: args, timeoutSeconds: 3600, destructive: true)
    }

    func runApplyAbstractRepair(itemKey: String) {
        let key = itemKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else {
            invalidDropWarnings = ["Select an abstract item first."]
            return
        }
        var args = [
            "run", "paperflow", "cleanup", "repair-abstracts",
            "--apply",
            "--confirm", "APPLY ABSTRACT REPAIRS",
            "--item-key", key
        ]
        if geminiCleanupEnabled && enableGeminiAbstractExtraction {
            args += ["--enable-gemini", "--gemini-model", selectedGeminiModel]
        }
        runUV(arguments: args, timeoutSeconds: 3600, destructive: true)
    }

    func runRepairMetadataDryRun() {
        runUV(
            arguments: ["run", "paperflow", "cleanup", "repair-metadata", "--dry-run"],
            timeoutSeconds: 1800
        )
    }

    func runRepairMetadataDryRun(itemKey: String) {
        let key = itemKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else {
            invalidDropWarnings = ["Select a metadata item first."]
            return
        }
        runUV(
            arguments: ["run", "paperflow", "cleanup", "repair-metadata", "--dry-run", "--item-key", key],
            timeoutSeconds: 1800
        )
    }

    func runApplyMetadataRepairs() {
        runUV(
            arguments: [
                "run", "paperflow", "cleanup", "repair-metadata",
                "--apply",
                "--confirm", "APPLY METADATA REPAIRS"
            ],
            timeoutSeconds: 3600,
            destructive: true
        )
    }

    func runApplyMetadataRepair(itemKey: String, approvedFields: [String]) {
        let key = itemKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else {
            invalidDropWarnings = ["Select a metadata item first."]
            return
        }
        var args = [
            "run", "paperflow", "cleanup", "repair-metadata",
            "--apply",
            "--confirm", "APPLY METADATA REPAIRS",
            "--item-key", key
        ]
        for field in approvedFields {
            args += ["--approved-field", field]
        }
        runUV(arguments: args, timeoutSeconds: 3600, destructive: true)
    }

    func runPlanDuplicateResolution() {
        runUV(
            arguments: ["run", "paperflow", "cleanup", "plan-duplicates"],
            timeoutSeconds: 600
        )
    }

    func runMigrationAudit() {
        runZotero(arguments: ["migration-audit"], timeoutSeconds: 600)
    }

    func runExplainItem(_ itemKey: String) {
        let key = itemKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else {
            invalidDropWarnings = ["Enter an item key to explain."]
            return
        }
        runZotero(arguments: ["explain-item", key], timeoutSeconds: 120)
    }

    func runDropShelfSelectedAction() {
        switch dropShelfAction {
        case .dryRunIngest:
            runDryRunIngest()
        case .applyIngest:
            runApplyIngest()
        case .addToZoteroInbox:
            invalidDropWarnings = ["Backend missing: add-to-Zotero-Inbox ingest mode is not implemented yet."]
            dropShelfPhase = .reviewNeeded
            shelfLastResult = "Add to Zotero Inbox requires a backend command."
        case .organizeWithAILibrary:
            invalidDropWarnings = ["Run dry-run ingest first, then use Zotero Organize to plan migration."]
            dropShelfPhase = .reviewNeeded
            shelfLastResult = "AI Library organization is handled by the Zotero migration workflow."
        }
    }

    func openZotero() {
        if let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "org.zotero.zotero") {
            NSWorkspace.shared.openApplication(at: url, configuration: NSWorkspace.OpenConfiguration())
        } else {
            invalidDropWarnings = ["Could not open Zotero. Install Zotero or open it manually."]
        }
    }

    func openProjectFolder() {
        NSWorkspace.shared.open(projectURL)
    }

    func openReportsFolder() {
        NSWorkspace.shared.open(dataURL)
    }

    func openAppLogsFolder() {
        try? FileManager.default.createDirectory(at: logsURL, withIntermediateDirectories: true)
        NSWorkspace.shared.open(logsURL)
    }

    func openVault() {
        NSWorkspace.shared.open(vaultURL)
    }

    func openReport(_ relativePath: String) {
        NSWorkspace.shared.open(dataURL.appendingPathComponent(relativePath))
    }

    func openLatestApplyLog() {
        if let url = latestFile(prefix: "apply_log_", suffix: ".md") {
            NSWorkspace.shared.open(url)
        } else {
            openReportsFolder()
        }
    }

    private func runZotero(
        arguments: [String],
        timeoutSeconds: TimeInterval,
        destructive: Bool = false
    ) {
        runUV(
            arguments: ["run", "paperflow", "zotero"] + arguments,
            timeoutSeconds: timeoutSeconds,
            destructive: destructive
        )
    }

    private func runUV(
        arguments: [String],
        timeoutSeconds: TimeInterval,
        destructive: Bool = false
    ) {
        let executable = NSString(string: uvPath).expandingTildeInPath
        let environment = commandEnvironment()
        let zoteroSecret = zoteroAPIKey.isEmpty ? (environment["ZOTERO_API_KEY"] ?? "") : zoteroAPIKey
        let geminiSecret = geminiAPIKey.isEmpty ? (environment["GEMINI_API_KEY"] ?? "") : geminiAPIKey
        let spec = CommandSpec(
            executable: executable,
            arguments: arguments,
            workingDirectory: projectURL,
            environment: environment,
            timeoutSeconds: timeoutSeconds,
            redactedSecrets: [zoteroSecret, geminiSecret],
            isDestructive: destructive
        )
        runner.run(spec)
    }

    private func runMissingBackend(_ message: String) {
        invalidDropWarnings = [message]
    }

    private func restoreZoteroVerification() {
        let verified = defaults.bool(forKey: "zoteroVerified")
        zoteroVerification = ZoteroCredentialStatus(
            verified: verified,
            message: verified ? "Verified" : (zoteroAPIKey.isEmpty ? "Not verified" : "Stored, not verified"),
            numericUserID: zoteroUserID,
            username: zoteroUsername,
            libraryAccess: defaults.bool(forKey: "zoteroLibraryAccess"),
            writeAccess: defaults.bool(forKey: "zoteroWriteAccess"),
            notesAccess: defaults.bool(forKey: "zoteroNotesAccess"),
            filesAccess: defaults.bool(forKey: "zoteroFilesAccess")
        )
    }

    private func persistZoteroVerification(_ status: ZoteroCredentialStatus) {
        defaults.set(status.verified, forKey: "zoteroVerified")
        defaults.set(status.libraryAccess, forKey: "zoteroLibraryAccess")
        defaults.set(status.writeAccess, forKey: "zoteroWriteAccess")
        defaults.set(status.notesAccess, forKey: "zoteroNotesAccess")
        defaults.set(status.filesAccess, forKey: "zoteroFilesAccess")
        defaults.set(status.username, forKey: "zoteroUsername")
    }

    private func recordLocalGeminiUsage(payload: [String: Any]? = nil, errorType: String? = nil) {
        let today = todayString()
        let usageURL = dataURL.appendingPathComponent("gemini_usage_\(today).json")
        var current = readJSON(usageURL) ?? [
            "date": today,
            "request_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "failed_rate_limit_calls": 0,
            "last_429_resource_exhausted_time": NSNull()
        ]

        current["date"] = current["date"] as? String ?? today
        current["request_count"] = (current["request_count"] as? Int ?? 0) + 1

        if let usage = payload?["usageMetadata"] as? [String: Any] {
            let prompt = usage["promptTokenCount"] as? Int ?? 0
            let candidates = usage["candidatesTokenCount"] as? Int ?? 0
            let total = usage["totalTokenCount"] as? Int ?? 0
            current["input_tokens"] = (current["input_tokens"] as? Int ?? 0) + prompt
            current["output_tokens"] = (current["output_tokens"] as? Int ?? 0) + candidates
            current["total_tokens"] = (current["total_tokens"] as? Int ?? 0) + total
        }

        if errorType == "rate_limited" {
            current["failed_rate_limit_calls"] = (current["failed_rate_limit_calls"] as? Int ?? 0) + 1
            current["last_429_resource_exhausted_time"] = ISO8601DateFormatter().string(from: Date())
        }

        do {
            try FileManager.default.createDirectory(at: dataURL, withIntermediateDirectories: true)
            let data = try JSONSerialization.data(withJSONObject: current, options: [.prettyPrinted, .sortedKeys])
            try data.write(to: usageURL)
            refreshGeminiUsage()
        } catch {
            invalidDropWarnings = ["Could not write Gemini usage status: \(error.localizedDescription)"]
        }
    }

    private func todayString() -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: Date())
    }

    private func parseZoteroKeyResponse(_ json: [String: Any]) -> ZoteroCredentialStatus? {
        guard let rawID = json["userID"] ?? json["userId"] ?? json["user_id"] else {
            return nil
        }
        let userID = String(describing: rawID)
        guard userID.allSatisfy(\.isNumber) else {
            return nil
        }
        let access = json["access"] as? [String: Any]
        let userAccess = access?["user"] as? [String: Any] ?? [:]
        return ZoteroCredentialStatus(
            verified: true,
            message: "Verified",
            numericUserID: userID,
            username: json["username"] as? String ?? "",
            libraryAccess: userAccess["library"] as? Bool ?? false,
            writeAccess: userAccess["write"] as? Bool ?? false,
            notesAccess: userAccess["notes"] as? Bool ?? false,
            filesAccess: userAccess["files"] as? Bool ?? false
        )
    }

    private func geminiStatus(_ payload: [String: Any]) -> String {
        let error = payload["error"] as? [String: Any]
        return error?["status"] as? String ?? ""
    }

    private func redactSecret(_ value: String, prefix: String) -> String {
        guard !value.isEmpty else {
            return "\(prefix)_not_set"
        }
        return "\(prefix)_********\(value.suffix(4))"
    }

    private func commandEnvironment() -> [String: String] {
        var environment = ProcessInfo.processInfo.environment
        let pathParts = [
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
            NSString(string: "~/.local/bin").expandingTildeInPath
        ]
        let currentPath = environment["PATH"] ?? ""
        environment["PATH"] = (pathParts + [currentPath]).filter { !$0.isEmpty }.joined(separator: ":")
        if !zoteroUserID.isEmpty {
            environment["ZOTERO_USER_ID"] = zoteroUserID
        }
        if apiKeyStorageMode == .keychain && !zoteroAPIKey.isEmpty {
            environment["ZOTERO_API_KEY"] = zoteroAPIKey
        }
        if apiKeyStorageMode == .keychain && !geminiAPIKey.isEmpty {
            environment["GEMINI_API_KEY"] = geminiAPIKey
        }
        return environment
    }

    private func readJSON(_ url: URL) -> [String: Any]? {
        guard let data = try? Data(contentsOf: url),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        return object
    }

    private func latestFile(prefix: String, suffix: String) -> URL? {
        guard let files = try? FileManager.default.contentsOfDirectory(
            at: dataURL,
            includingPropertiesForKeys: [.contentModificationDateKey]
        ) else {
            return nil
        }
        return files
            .filter { $0.lastPathComponent.hasPrefix(prefix) && $0.lastPathComponent.hasSuffix(suffix) }
            .max { lhs, rhs in modificationDate(lhs) < modificationDate(rhs) }
    }

    private func latestFileStatus(prefix: String, suffix: String) -> String? {
        guard let url = latestFile(prefix: prefix, suffix: suffix) else {
            return nil
        }
        return "\(url.lastPathComponent) • \(formatDate(modificationDate(url)))"
    }

    private func statusLine(for url: URL) -> String {
        guard FileManager.default.fileExists(atPath: url.path) else {
            return "Missing \(url.lastPathComponent)"
        }
        return "\(url.lastPathComponent) • \(formatDate(modificationDate(url)))"
    }

    private func modificationDate(_ url: URL) -> Date {
        let values = try? url.resourceValues(forKeys: [.contentModificationDateKey])
        return values?.contentModificationDate ?? .distantPast
    }

    private func formatDate(_ date: Date) -> String {
        if date == .distantPast {
            return "unknown date"
        }
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }

    private static func defaultProjectPath() -> String {
        let candidate = NSString(string: "~/Desktop/project/paperflow").expandingTildeInPath
        if FileManager.default.fileExists(atPath: candidate) {
            return candidate
        }
        return FileManager.default.homeDirectoryForCurrentUser.path
    }

    private static func defaultVaultPath() -> String {
        NSString(string: "~/Papers/Paperflow/Library").expandingTildeInPath
    }

    private static func defaultUVPath() -> String {
        let candidates = [
            "/opt/homebrew/bin/uv",
            "/usr/local/bin/uv",
            NSString(string: "~/.local/bin/uv").expandingTildeInPath
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) } ?? "/opt/homebrew/bin/uv"
    }
}
