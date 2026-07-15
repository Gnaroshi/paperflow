import AppKit
import Foundation
import ServiceManagement

@MainActor
final class AppState: ObservableObject {
    private var suppressServiceCallbacks = true
    private var dryRunIngestScope: [String] = []

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
            guard !suppressServiceCallbacks else { return }
            AppServices.shared.reconfigureHotZones()
            AppServices.shared.shelfController?.applyActivationMode()
        }
    }
    @Published var dropShelfPlacement: DropShelfPlacement = .bottomRight {
        didSet { defaults.set(dropShelfPlacement.rawValue, forKey: "dropShelfPlacement") }
    }
    @Published var displayMode: DisplayMode = .focusedMonitor {
        didSet {
            defaults.set(displayMode.rawValue, forKey: "displayMode")
            guard !suppressServiceCallbacks else { return }
            AppServices.shared.reconfigureHotZones()
        }
    }
    @Published var focusedMonitorStrategy: FocusedMonitorStrategy = .cursorScreen {
        didSet { defaults.set(focusedMonitorStrategy.rawValue, forKey: "focusedMonitorStrategy") }
    }
    @Published var showPFWAcrossSpaces = false {
        didSet {
            defaults.set(showPFWAcrossSpaces, forKey: "showPFWAcrossSpaces")
            guard !suppressServiceCallbacks else { return }
            AppServices.shared.shelfController?.refreshWindowBehaviors()
            AppServices.shared.reconfigureHotZones()
        }
    }
    @Published var hotZoneEnabled = false {
        didSet {
            defaults.set(hotZoneEnabled, forKey: "hotZoneEnabled")
            guard !suppressServiceCallbacks else { return }
            AppServices.shared.reconfigureHotZones()
        }
    }
    @Published var hotZoneEdge: HotZoneEdge = .right {
        didSet {
            defaults.set(hotZoneEdge.rawValue, forKey: "hotZoneEdge")
            guard !suppressServiceCallbacks else { return }
            AppServices.shared.reconfigureHotZones()
        }
    }
    @Published var hotZoneCorner: HotZoneCorner = .bottomRight {
        didSet {
            defaults.set(hotZoneCorner.rawValue, forKey: "hotZoneCorner")
            guard !suppressServiceCallbacks else { return }
            AppServices.shared.reconfigureHotZones()
        }
    }
    @Published var hotZoneWidth: Double = 12 {
        didSet {
            defaults.set(hotZoneWidth, forKey: "hotZoneWidth")
            guard !suppressServiceCallbacks else { return }
            AppServices.shared.reconfigureHotZones()
        }
    }
    @Published var hotZoneHeight: Double = 160 {
        didSet {
            defaults.set(hotZoneHeight, forKey: "hotZoneHeight")
            guard !suppressServiceCallbacks else { return }
            AppServices.shared.reconfigureHotZones()
        }
    }
    @Published var hotZoneIdleOpacity: Double = 0.12 {
        didSet {
            defaults.set(hotZoneIdleOpacity, forKey: "hotZoneIdleOpacity")
            guard !suppressServiceCallbacks else { return }
            AppServices.shared.reconfigureHotZones()
        }
    }
    @Published var autoCollapseDelay: Double = 4 {
        didSet { defaults.set(autoCollapseDelay, forKey: "autoCollapseDelay") }
    }
    @Published var autoHideAfterSuccess = false {
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
    @Published var commandShortcutPreset: CommandShortcutPreset = .optionSpace {
        didSet {
            defaults.set(commandShortcutPreset.rawValue, forKey: "commandShortcutPreset")
            globalShortcutCommand = commandShortcutPreset.label
            guard !suppressServiceCallbacks else { return }
            AppServices.shared.hotkeyManager?.register(state: self)
        }
    }
    @Published var dropShelfShortcutPreset: DropShelfShortcutPreset = .controlShiftCommandPlus {
        didSet {
            defaults.set(dropShelfShortcutPreset.rawValue, forKey: "dropShelfShortcutPreset")
            dropShelfShortcut = dropShelfShortcutPreset.label
            guard !suppressServiceCallbacks else { return }
            AppServices.shared.hotkeyManager?.register(state: self)
        }
    }
    @Published var globalShortcutCommand = "⌥Space"
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
    @Published var zoteroStoragePath: String {
        didSet {
            defaults.set(zoteroStoragePath, forKey: "zoteroStoragePath")
            refreshStorageLocations()
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
    @Published var zoteroStorageStatus = FolderLocationStatus(name: "Zotero Storage", path: "")
    @Published var downloadsStatus = FolderLocationStatus(name: "Downloads", path: "")
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
    @Published var localImportPath: String {
        didSet { defaults.set(localImportPath, forKey: "localImportPath") }
    }
    @Published var localImportRecursive: Bool {
        didSet { defaults.set(localImportRecursive, forKey: "localImportRecursive") }
    }
    @Published var localImportMaxDepth: String {
        didSet { defaults.set(localImportMaxDepth, forKey: "localImportMaxDepth") }
    }
    @Published var localImportExcludeExistingZotero: Bool {
        didSet { defaults.set(localImportExcludeExistingZotero, forKey: "localImportExcludeExistingZotero") }
    }
    @Published var localImportUseGemini: Bool {
        didSet { defaults.set(localImportUseGemini, forKey: "localImportUseGemini") }
    }
    @Published var localImportStopOnGeminiQuota: Bool {
        didSet { defaults.set(localImportStopOnGeminiQuota, forKey: "localImportStopOnGeminiQuota") }
    }
    @Published var localImportFilter: LocalImportFilter = .newOnly
    @Published var localImportData = LocalImportData()

    let runner = CommandRunner()
    private let defaults = UserDefaults.standard

    init() {
        let defaultProject = Self.defaultProjectPath()
        let defaultVault = Self.defaultVaultPath()
        let resolvedProjectPath = defaults.string(forKey: "projectPath") ?? defaultProject
        projectPath = resolvedProjectPath
        let savedUVPath = defaults.string(forKey: "uvPath")
        if let savedUVPath, !Self.isSystemUVPath(savedUVPath) {
            uvPath = savedUVPath
        } else {
            uvPath = Self.defaultUVPath(projectPath: resolvedProjectPath)
        }
        vaultPath = defaults.string(forKey: "vaultPath") ?? defaultVault
        zoteroStoragePath = defaults.string(forKey: "zoteroStoragePath") ?? Self.defaultZoteroStoragePath()
        localImportPath = defaults.string(forKey: "localImportPath") ?? ""
        localImportRecursive = defaults.object(forKey: "localImportRecursive") as? Bool ?? true
        localImportMaxDepth = defaults.string(forKey: "localImportMaxDepth") ?? ""
        localImportExcludeExistingZotero = defaults.object(forKey: "localImportExcludeExistingZotero") as? Bool ?? true
        localImportUseGemini = defaults.object(forKey: "localImportUseGemini") as? Bool ?? false
        localImportStopOnGeminiQuota = defaults.object(forKey: "localImportStopOnGeminiQuota") as? Bool ?? true
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
        if let value = defaults.string(forKey: "commandShortcutPreset"),
           let preset = CommandShortcutPreset(rawValue: value) {
            commandShortcutPreset = preset
            globalShortcutCommand = preset.label
        }
        if let value = defaults.string(forKey: "dropShelfShortcutPreset"),
           let preset = DropShelfShortcutPreset(rawValue: value) {
            dropShelfShortcutPreset = preset
            dropShelfShortcut = preset.label
        }

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
        if defaults.object(forKey: "showPFWAcrossSpaces") != nil {
            showPFWAcrossSpaces = defaults.bool(forKey: "showPFWAcrossSpaces")
        }

        if defaults.bool(forKey: "pfwP0DefaultsApplied") == false {
            dropShelfActivationMode = .keyboardShortcutOnly
            dropShelfPlacement = .bottomRight
            displayMode = .focusedMonitor
            focusedMonitorStrategy = .cursorScreen
            hotZoneEnabled = false
            showPFWAcrossSpaces = false
            autoHideAfterSuccess = false
            defaults.set(true, forKey: "pfwP0DefaultsApplied")
        }

        restoreZoteroVerification()
        suppressServiceCallbacks = false
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

    var vaultRootURL: URL {
        vaultURL.deletingLastPathComponent()
    }

    var zoteroStorageURL: URL {
        URL(fileURLWithPath: NSString(string: zoteroStoragePath).expandingTildeInPath)
    }

    var downloadsURL: URL {
        FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Downloads", isDirectory: true)
    }

    var logsURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/PaperFlow", isDirectory: true)
    }

    func workflowStepState(
        commandFragment: String,
        prerequisiteGroups: [[String]] = [],
        outputs: [String] = []
    ) -> WorkflowStepState {
        if runner.isRunning {
            if runner.currentCommand.contains(commandFragment) {
                return .running
            }
            return .blocked("Another PaperFlow command is running")
        }

        let missing = missingPrerequisiteGroups(prerequisiteGroups)
        if !missing.isEmpty {
            return .blocked("Requires \(missing.joined(separator: ", "))")
        }

        guard !outputs.isEmpty, outputs.allSatisfy(artifactExists) else {
            return .ready
        }

        let newestInput = prerequisiteGroups
            .flatMap { $0 }
            .compactMap(artifactModificationDate)
            .max()
        let oldestOutput = outputs.compactMap(artifactModificationDate).min()
        if let newestInput, let oldestOutput, newestInput > oldestOutput {
            return .outdated("An input changed after this output was generated")
        }
        return .completed
    }

    func artifactExists(_ relativePath: String) -> Bool {
        let url = projectURL.appendingPathComponent(relativePath)
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory) else {
            return false
        }
        if isDirectory.boolValue {
            return !((try? FileManager.default.contentsOfDirectory(atPath: url.path).isEmpty) ?? true)
        }
        return true
    }

    func hasGeneratedArtifact(prefix: String, suffix: String) -> Bool {
        latestFile(prefix: prefix, suffix: suffix) != nil
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

    var ingestApplyBlocker: String? {
        guard !droppedPDFs.isEmpty else {
            return "Drop at least one PDF first"
        }
        guard shelfStoreInLocalVault, shelfLinkToZoteroNoUpload else {
            return "Keep local vault and linked attachment only enabled"
        }
        guard case .succeeded = runner.status,
              runner.currentCommand.contains("paperflow ingest"),
              runner.currentCommand.contains("--dry-run"),
              dryRunIngestScope == currentIngestScope else {
            return "Run Dry Run successfully for these exact PDFs first"
        }
        return nil
    }

    var migrationApplyBlocker: String? {
        guard zoteroVerification.writeAccess else {
            return "Verify a Zotero API key with write access in Settings"
        }
        let missing = missingPrerequisiteGroups([
            ["data/backups"],
            ["data/migration_plan.json"],
            ["data/apply_preview.json", "data/apply_preview.md"]
        ])
        guard missing.isEmpty else {
            return "Requires \(missing.joined(separator: ", "))"
        }
        guard let planDate = artifactModificationDate("data/migration_plan.json"),
              let previewDate = ["data/apply_preview.json", "data/apply_preview.md"]
                .compactMap(artifactModificationDate)
                .max(),
              previewDate >= planDate else {
            return "Run Dry Run Migration again because the plan changed"
        }
        guard let preview = readJSON(dataURL.appendingPathComponent("apply_preview.json")),
              preview["collection_mode"] as? String == collectionMode.rawValue,
              preview["tag_mode"] as? String == tagMode.rawValue else {
            return "Run Dry Run Migration again because the collection or tag mode changed"
        }
        return nil
    }

    func refreshStatus() {
        refreshDashboard()
        refreshVaultStatus()
        refreshStorageLocations()
        refreshGeminiUsage()
        refreshLocalImportStatus()
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
            last429Time: usage["last_429_resource_exhausted_time"] as? String,
            lastSuccessTime: usage["last_success_time"] as? String,
            lastInvalidKeyTime: usage["last_401_403_time"] as? String,
            currentStatus: usage["current_status"] as? String ?? "unknown"
        )
        if geminiUsage.failedRateLimitCalls > 0 {
            geminiVerification.rateLimited = true
            geminiVerification.message = "Gemini Flash is currently rate-limited. Try later or reduce batch size."
        }
    }

    func refreshLocalImportStatus() {
        localImportData = ReportParser.localImportData(dataURL: dataURL)
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

    func refreshStorageLocations(scanDownloads: Bool = false) {
        zoteroStorageStatus = folderLocationStatus(
            name: "Zotero Storage",
            url: zoteroStorageURL,
            recursive: true
        )
        if scanDownloads {
            downloadsStatus = folderLocationStatus(
                name: "Downloads",
                url: downloadsURL,
                recursive: false
            )
        } else {
            var status = FolderLocationStatus(name: "Downloads", path: downloadsURL.path)
            var isDirectory: ObjCBool = false
            status.exists = FileManager.default.fileExists(atPath: downloadsURL.path, isDirectory: &isDirectory)
                && isDirectory.boolValue
            downloadsStatus = status
        }
    }

    private func folderLocationStatus(name: String, url: URL, recursive: Bool) -> FolderLocationStatus {
        var status = FolderLocationStatus(name: name, path: url.path)
        var isDirectory: ObjCBool = false
        status.exists = FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory)
            && isDirectory.boolValue
        guard status.exists else { return status }

        status.isScanned = true
        let keys: [URLResourceKey] = [.isRegularFileKey, .fileSizeKey]
        let files: [URL]
        if recursive {
            let enumerator = FileManager.default.enumerator(
                at: url,
                includingPropertiesForKeys: keys,
                options: [.skipsHiddenFiles]
            )
            var discovered: [URL] = []
            if let enumerator {
                for case let fileURL as URL in enumerator {
                    discovered.append(fileURL)
                }
            }
            files = discovered
        } else {
            files = (try? FileManager.default.contentsOfDirectory(
                at: url,
                includingPropertiesForKeys: keys,
                options: [.skipsHiddenFiles]
            )) ?? []
        }

        for file in files where file.pathExtension.caseInsensitiveCompare("pdf") == .orderedSame {
            let values = try? file.resourceValues(forKeys: Set(keys))
            guard values?.isRegularFile == true else { continue }
            status.pdfCount += 1
            status.totalBytes += UInt64(values?.fileSize ?? 0)
        }
        return status
    }

    func addDroppedURLs(_ urls: [URL]) {
        invalidDropWarnings.removeAll()
        var existing = Set(droppedPDFs.map(\.url))
        var addedPDF = false
        for url in urls {
            if url.pathExtension.lowercased() == "pdf" {
                if !existing.contains(url) {
                    droppedPDFs.append(DroppedPDF(url: url))
                    existing.insert(url)
                    addedPDF = true
                }
            } else {
                invalidDropWarnings.append("Ignored non-PDF: \(url.lastPathComponent)")
            }
        }
        if addedPDF {
            dryRunIngestScope = []
        }
    }

    func removePDFs(at offsets: IndexSet) {
        for index in offsets.sorted(by: >) {
            droppedPDFs.remove(at: index)
        }
        dryRunIngestScope = []
    }

    func removePDF(_ pdf: DroppedPDF) {
        droppedPDFs.removeAll { $0.id == pdf.id }
        dryRunIngestScope = []
        if droppedPDFs.isEmpty, dropShelfPhase != .processing {
            dropShelfPhase = .idleCompact
        }
    }

    func clearPDFs() {
        droppedPDFs.removeAll()
        invalidDropWarnings.removeAll()
        dryRunIngestScope = []
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
            vaultPath = url.lastPathComponent.caseInsensitiveCompare("Library") == .orderedSame
                ? url.path
                : url.appendingPathComponent("Library", isDirectory: true).path
        }
    }

    func chooseZoteroStorageDirectory() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.directoryURL = zoteroStorageURL
        if panel.runModal() == .OK, let url = panel.url {
            zoteroStoragePath = url.path
        }
    }

    func chooseLocalImportFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.directoryURL = localImportPath.isEmpty
            ? projectURL
            : URL(fileURLWithPath: NSString(string: localImportPath).expandingTildeInPath)
        if panel.runModal() == .OK, let url = panel.url {
            localImportPath = url.path
        }
    }

    func scanDownloadsForImport() {
        localImportPath = downloadsURL.path
        selectedSection = .localFolderImport
        refreshStorageLocations(scanDownloads: true)
        runLocalFolderScan()
    }

    func openDownloadsImport() {
        localImportPath = downloadsURL.path
        selectedSection = .localFolderImport
        refreshStorageLocations(scanDownloads: true)
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
        guard requirePrerequisites([["data/zotero_items.jsonl"]], action: "Enrich Metadata") else { return }
        runZotero(arguments: ["enrich-metadata"], timeoutSeconds: 1800)
    }

    func runDetectDuplicates() {
        guard requirePrerequisites(
            [["data/zotero_items_enriched.jsonl", "data/zotero_items.jsonl"]],
            action: "Detect Duplicates"
        ) else { return }
        runZotero(arguments: ["detect-duplicates"], timeoutSeconds: 1800)
    }

    func runPlanMigration() {
        guard requirePrerequisites(
            [["data/zotero_items_enriched.jsonl", "data/zotero_items.jsonl"]],
            action: "Plan Migration"
        ) else { return }
        runZotero(arguments: ["plan-migration"], timeoutSeconds: 1800)
    }

    func runDryRunMigration() {
        guard requirePrerequisites([["data/migration_plan.json"]], action: "Dry Run Migration") else { return }
        runZotero(
            arguments: [
                "dry-run-migration",
                "--collection-mode", collectionMode.rawValue,
                "--tag-mode", tagMode.rawValue
            ],
            timeoutSeconds: 1800
        )
    }

    func runApplyMigration() {
        if let blocker = migrationApplyBlocker {
            invalidDropWarnings = ["Apply Migration blocked. \(blocker)."]
            return
        }
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
        guard requirePrerequisites([["data/cleanup_report.md"]], action: "Cleanup Empty Collections") else { return }
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
        dryRunIngestScope = currentIngestScope
        runUV(arguments: ingestArguments(apply: false, offlineFast: false), timeoutSeconds: 120)
    }

    func runDryRunIngestOfflineFast() {
        guard backend.ingestLinkedLocal else {
            invalidDropWarnings = ["Backend missing: paperflow ingest --storage-mode linked-local is not implemented yet."]
            return
        }
        guard !droppedPDFs.isEmpty else {
            invalidDropWarnings = ["Drop at least one PDF first."]
            return
        }
        dryRunIngestScope = currentIngestScope
        runUV(arguments: ingestArguments(apply: false, offlineFast: true), timeoutSeconds: 60)
    }

    func runApplyIngest() {
        guard backend.ingestLinkedLocal else {
            invalidDropWarnings = ["Backend missing: paperflow ingest --storage-mode linked-local is not implemented yet."]
            return
        }
        if let blocker = ingestApplyBlocker {
            invalidDropWarnings = ["Apply Ingest blocked. \(blocker)."]
            return
        }
        let args = ingestArguments(apply: true, offlineFast: false)
        runUV(arguments: args, timeoutSeconds: 1800, destructive: true)
    }

    func runVaultInit() {
        runUV(
            arguments: ["run", "paperflow", "vault", "init", "--vault-root", vaultRootURL.path],
            timeoutSeconds: 600
        )
    }

    func runVaultPlanPaths() {
        guard requirePrerequisites([["data/migration_plan.json"]], action: "Plan Vault Paths") else { return }
        runUV(
            arguments: ["run", "paperflow", "vault", "plan-paths", "--vault-library", vaultURL.path],
            timeoutSeconds: 600
        )
    }

    func runLocalFolderScan() {
        let path = localImportPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !path.isEmpty else {
            invalidDropWarnings = ["Choose a folder or enter a terminal path first."]
            return
        }
        var args = ["run", "paperflow", "local", "scan", path]
        args.append(localImportRecursive ? "--recursive" : "--no-recursive")
        if let depth = Int(localImportMaxDepth.trimmingCharacters(in: .whitespacesAndNewlines)) {
            args += ["--max-depth", String(depth)]
        }
        args.append("--progress-jsonl")
        runUV(arguments: args, timeoutSeconds: 1800)
    }

    func runLocalFolderMatchZotero() {
        guard requirePrerequisites([["data/local_scan.json"]], action: "Match Zotero") else { return }
        if !localImportExcludeExistingZotero {
            invalidDropWarnings = ["Exclude existing Zotero items is off. Matching is still safe and recommended before import."]
        }
        runUVSequence([
            (["run", "paperflow", "local", "index-zotero"], 1800),
            (["run", "paperflow", "local", "match-zotero"], 1800)
        ])
    }

    func runIndexZoteroStorage() {
        runUV(
            arguments: ["run", "paperflow", "local", "index-zotero"],
            timeoutSeconds: 1800
        )
    }

    func runLocalFolderClassifyNew() {
        guard requirePrerequisites(
            [["data/local_scan.json"], ["data/local_zotero_match_plan.json"]],
            action: "Classify New Papers"
        ) else { return }
        var args = ["run", "paperflow", "local", "classify-new"]
        if localImportUseGemini {
            args += [
                "--use-gemini",
                "--gemini-model", selectedGeminiModel,
                "--stop-on-gemini-quota", localImportStopOnGeminiQuota ? "true" : "false"
            ]
        }
        runUV(arguments: args, timeoutSeconds: 3600)
    }

    func saveUserClassificationOverrideRule(
        row: LocalImportRow,
        collection: String,
        tagsText: String
    ) {
        let cleanedCollection = collection.trimmingCharacters(in: .whitespacesAndNewlines)
        let tags = tagsText
            .split { character in character == ";" || character == "," || character == "\n" || character == "\t" }
            .map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        guard !cleanedCollection.isEmpty || !tags.isEmpty else {
            invalidDropWarnings = ["Enter at least one collection or tag before saving a taxonomy rule."]
            return
        }
        let title = row.title == "(untitled)" ? URL(fileURLWithPath: row.localPath).deletingPathExtension().lastPathComponent : row.title
        let titleNeedle = normalizedRuleNeedle(title)
        guard !titleNeedle.isEmpty else {
            invalidDropWarnings = ["Cannot create taxonomy rule because this row has no usable title."]
            return
        }
        let configURL = projectURL.appendingPathComponent("config", isDirectory: true)
        let overridesURL = configURL.appendingPathComponent("user_taxonomy_overrides.yaml")
        do {
            try FileManager.default.createDirectory(at: configURL, withIntermediateDirectories: true)
            var content = ""
            if FileManager.default.fileExists(atPath: overridesURL.path) {
                content = try String(contentsOf: overridesURL, encoding: .utf8)
            }
            if content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                content = "rules:\n"
            }
            if !content.contains("rules:") {
                content = "rules:\n" + content
            }
            if !content.hasSuffix("\n") {
                content += "\n"
            }
            var rule = """
              - name: \(yamlQuoted("User override - \(title)"))
                when:
                  title_contains:
                    - \(yamlQuoted(titleNeedle))
                collections:
            """
            if cleanedCollection.isEmpty {
                rule += "      []\n"
            } else {
                rule += "      - \(yamlQuoted(cleanedCollection))\n"
            }
            rule += "    tags:\n"
            if tags.isEmpty {
                rule += "      []\n"
            } else {
                for tag in tags {
                    rule += "      - \(yamlQuoted(tag))\n"
                }
            }
            try (content + rule).write(to: overridesURL, atomically: true, encoding: .utf8)
            invalidDropWarnings = ["Saved taxonomy override rule to \(overridesURL.path). Re-running local classification."]
            runLocalFolderClassifyNew()
        } catch {
            invalidDropWarnings = ["Failed to save taxonomy override rule: \(error.localizedDescription)"]
        }
    }

    func runLocalFolderPlanImport() {
        guard requirePrerequisites([["data/local_classification_plan.json"]], action: "Plan Import") else { return }
        runUV(
            arguments: [
                "run", "paperflow", "local", "plan-import",
                "--vault-library", vaultURL.path
            ],
            timeoutSeconds: 1800
        )
    }

    func runApplyLocalImport() {
        guard requirePrerequisites([["data/local_import_plan.json"]], action: "Apply Local Import") else { return }
        guard zoteroVerification.writeAccess else {
            invalidDropWarnings = ["Apply Local Import blocked: Zotero API key write access is missing or unverified."]
            return
        }
        runUV(
            arguments: [
                "run", "paperflow", "local", "apply-import",
                "--apply",
                "--confirm", "IMPORT LOCAL PAPERS"
            ],
            timeoutSeconds: 7200,
            destructive: true
        )
    }

    func runLocalFolderAuditImport() {
        guard hasGeneratedArtifact(prefix: "local_import_apply_log_", suffix: ".json") else {
            invalidDropWarnings = ["Audit Import requires a successful local_import_apply_log_*.json file."]
            return
        }
        runUV(arguments: ["run", "paperflow", "local", "audit-import"], timeoutSeconds: 1800)
    }

    func runPlanLocalizeAttachments() {
        runZotero(
            arguments: ["plan-localize-attachments", "--vault-library", vaultURL.path],
            timeoutSeconds: 1800
        )
    }

    func runApplyLocalizeAttachments() {
        guard requirePrerequisites(
            [["data/localize_attachments_plan.json"]],
            action: "Apply Localize Attachments"
        ) else { return }
        guard zoteroVerification.writeAccess else {
            invalidDropWarnings = ["Attachment localization requires verified Zotero write access."]
            return
        }
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
        guard requirePrerequisites(
            [["data/localize_attachments_plan.json"]],
            action: "Verify Localized Attachments"
        ) else { return }
        guard hasGeneratedArtifact(prefix: "localize_apply_log_", suffix: ".json") else {
            invalidDropWarnings = ["Verify Localized Attachments requires a localize_apply_log_*.json file."]
            return
        }
        runZotero(arguments: ["verify-localized-attachments"], timeoutSeconds: 1800)
    }

    func runCleanupStoredAttachments() {
        guard requirePrerequisites(
            [["data/localize_attachments_plan.json"], ["data/localize_verify_report.json"]],
            action: "Cleanup Stored Attachments"
        ) else { return }
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
            if !stopOnGeminiQuotaHit {
                args.append("--continue-on-gemini-quota")
            }
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
            if !stopOnGeminiQuotaHit {
                args.append("--continue-on-gemini-quota")
            }
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
            if !stopOnGeminiQuotaHit {
                args.append("--continue-on-gemini-quota")
            }
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
            if !stopOnGeminiQuotaHit {
                args.append("--continue-on-gemini-quota")
            }
        }
        runUV(arguments: args, timeoutSeconds: 3600, destructive: true)
    }

    func runRepairMetadataDryRun() {
        runUV(arguments: metadataRepairArguments(apply: false), timeoutSeconds: 1800)
    }

    func runRepairMetadataDryRun(itemKey: String) {
        let key = itemKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else {
            invalidDropWarnings = ["Select a metadata item first."]
            return
        }
        runUV(arguments: metadataRepairArguments(apply: false, itemKey: key), timeoutSeconds: 1800)
    }

    func runApplyMetadataRepairs() {
        runUV(arguments: metadataRepairArguments(apply: true), timeoutSeconds: 3600, destructive: true)
    }

    func runApplyMetadataRepair(itemKey: String, approvedFields: [String]) {
        let key = itemKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty else {
            invalidDropWarnings = ["Select a metadata item first."]
            return
        }
        var args = metadataRepairArguments(apply: true, itemKey: key)
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

    func openFolder(path: String) {
        let expanded = NSString(string: path).expandingTildeInPath
        guard !expanded.isEmpty else { return }
        NSWorkspace.shared.open(URL(fileURLWithPath: expanded, isDirectory: true))
    }

    func openLocalPDF(path: String) {
        let expanded = NSString(string: path).expandingTildeInPath
        guard !expanded.isEmpty else { return }
        NSWorkspace.shared.open(URL(fileURLWithPath: expanded))
    }

    func revealInFinder(path: String) {
        let expanded = NSString(string: path).expandingTildeInPath
        guard !expanded.isEmpty else { return }
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: expanded)])
    }

    func openZoteroItem(itemKey: String) {
        let key = itemKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !key.isEmpty,
              let url = URL(string: "zotero://select/library/items/\(key)") else {
            invalidDropWarnings = ["No matched Zotero item key for this row."]
            return
        }
        NSWorkspace.shared.open(url)
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
        runner.run(makeUVSpec(
            arguments: arguments,
            timeoutSeconds: timeoutSeconds,
            destructive: destructive
        ))
    }

    private func runUVSequence(_ commands: [([String], TimeInterval)]) {
        runner.runSequence(commands.map { command in
            makeUVSpec(arguments: command.0, timeoutSeconds: command.1, destructive: false)
        })
    }

    private func makeUVSpec(
        arguments: [String],
        timeoutSeconds: TimeInterval,
        destructive: Bool
    ) -> CommandSpec {
        let executable = NSString(string: uvPath).expandingTildeInPath
        let environment = commandEnvironment()
        let zoteroSecret = zoteroAPIKey.isEmpty ? (environment["ZOTERO_API_KEY"] ?? "") : zoteroAPIKey
        let geminiSecret = geminiAPIKey.isEmpty ? (environment["GEMINI_API_KEY"] ?? "") : geminiAPIKey
        return CommandSpec(
            executable: executable,
            arguments: arguments,
            workingDirectory: projectURL,
            environment: environment,
            timeoutSeconds: timeoutSeconds,
            redactedSecrets: [zoteroSecret, geminiSecret],
            isDestructive: destructive
        )
    }

    private func runMissingBackend(_ message: String) {
        invalidDropWarnings = [message]
    }

    private func requirePrerequisites(_ groups: [[String]], action: String) -> Bool {
        let missing = missingPrerequisiteGroups(groups)
        guard missing.isEmpty else {
            invalidDropWarnings = ["\(action) blocked. Missing \(missing.joined(separator: ", "))."]
            return false
        }
        return true
    }

    private func missingPrerequisiteGroups(_ groups: [[String]]) -> [String] {
        groups.compactMap { group in
            group.contains(where: artifactExists) ? nil : group.joined(separator: " or ")
        }
    }

    private func artifactModificationDate(_ relativePath: String) -> Date? {
        let url = projectURL.appendingPathComponent(relativePath)
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory) else {
            return nil
        }
        if isDirectory.boolValue,
           let children = try? FileManager.default.contentsOfDirectory(
               at: url,
               includingPropertiesForKeys: [.contentModificationDateKey]
           ) {
            return children.map(modificationDate).max() ?? modificationDate(url)
        }
        return modificationDate(url)
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
            "last_429_resource_exhausted_time": NSNull(),
            "last_success_time": NSNull(),
            "last_401_403_time": NSNull(),
            "current_status": "unknown"
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
            current["last_success_time"] = ISO8601DateFormatter().string(from: Date())
            current["current_status"] = "ok"
        }

        if errorType == "rate_limited" {
            current["failed_rate_limit_calls"] = (current["failed_rate_limit_calls"] as? Int ?? 0) + 1
            current["last_429_resource_exhausted_time"] = ISO8601DateFormatter().string(from: Date())
            current["current_status"] = "rate_limited"
        } else if errorType == "invalid_key" {
            current["last_401_403_time"] = ISO8601DateFormatter().string(from: Date())
            current["current_status"] = "invalid_key"
        } else if errorType == "service_error" {
            current["current_status"] = "service_error"
        } else if errorType != nil {
            current["current_status"] = "unknown"
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
        if let activeEnvironment = environment["VIRTUAL_ENV"], !activeEnvironment.isEmpty {
            let activeBin = URL(fileURLWithPath: activeEnvironment).appendingPathComponent("bin").path
            environment["PATH"] = environment["PATH"]?
                .split(separator: ":")
                .map(String.init)
                .filter { $0 != activeBin }
                .joined(separator: ":")
        }
        environment.removeValue(forKey: "VIRTUAL_ENV")
        environment["UV_PROJECT_ENVIRONMENT"] = projectURL.appendingPathComponent(".venv").path
        environment["UV_CACHE_DIR"] = projectURL.appendingPathComponent(".uv-cache").path
        environment["UV_PYTHON_INSTALL_DIR"] = projectURL.appendingPathComponent(".uv-python").path
        environment["UV_TOOL_DIR"] = projectURL.appendingPathComponent(".uv-tools").path
        environment["UV_NO_ACTIVE_VENV"] = "1"
        if !zoteroUserID.isEmpty {
            environment["ZOTERO_USER_ID"] = zoteroUserID
        }
        if apiKeyStorageMode == .keychain && !zoteroAPIKey.isEmpty {
            environment["ZOTERO_API_KEY"] = zoteroAPIKey
        }
        if apiKeyStorageMode == .keychain && !geminiAPIKey.isEmpty {
            environment["GEMINI_API_KEY"] = geminiAPIKey
        }
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"
        return environment
    }

    private func ingestArguments(apply: Bool, offlineFast: Bool) -> [String] {
        var args = ["run", "paperflow", "ingest"] + droppedPDFs.map { $0.url.path }
        args += [
            apply ? "--apply" : "--dry-run",
            "--storage-mode", "linked-local",
            "--vault-library", vaultURL.path,
            "--progress-jsonl",
            "--verbose",
            "--total-timeout-seconds", apply ? "1800" : "60",
            "--network-timeout-seconds", "10",
            "--pdf-timeout-seconds", "20",
            "--llm-timeout-seconds", "30",
            "--no-gemini"
        ]
        if offlineFast {
            args.append("--offline-fast")
        }
        return args
    }

    private var currentIngestScope: [String] {
        droppedPDFs.map { pdf in
            let url = pdf.url.standardizedFileURL
            let values = try? url.resourceValues(forKeys: [.contentModificationDateKey, .fileSizeKey])
            let modified = values?.contentModificationDate?.timeIntervalSince1970 ?? 0
            return "\(url.path)|\(values?.fileSize ?? -1)|\(modified)"
        }
        .sorted()
    }

    private func metadataRepairArguments(apply: Bool, itemKey: String? = nil) -> [String] {
        var args = ["run", "paperflow", "cleanup", "repair-metadata"]
        if apply {
            args += ["--apply", "--confirm", "APPLY METADATA REPAIRS"]
        } else {
            args.append("--dry-run")
        }
        if let itemKey, !itemKey.isEmpty {
            args += ["--item-key", itemKey]
        }
        if geminiCleanupEnabled && enableGeminiMetadataExtraction {
            args += ["--enable-gemini", "--gemini-model", selectedGeminiModel]
            if !stopOnGeminiQuotaHit {
                args.append("--continue-on-gemini-quota")
            }
        }
        return args
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

    private func yamlQuoted(_ value: String) -> String {
        let escaped = value
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
        return "\"\(escaped)\""
    }

    private func normalizedRuleNeedle(_ value: String) -> String {
        value
            .lowercased()
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
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

    private static func defaultZoteroStoragePath() -> String {
        NSString(string: "~/Zotero/storage").expandingTildeInPath
    }

    private static func defaultUVPath(projectPath: String) -> String {
        let projectWrapper = URL(fileURLWithPath: projectPath)
            .appendingPathComponent("bin/paperflow-uv")
            .path
        if FileManager.default.isExecutableFile(atPath: projectWrapper) {
            return projectWrapper
        }
        let candidates = [
            "/opt/homebrew/bin/uv",
            "/usr/local/bin/uv",
            NSString(string: "~/.local/bin/uv").expandingTildeInPath
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) } ?? "/opt/homebrew/bin/uv"
    }

    private static func isSystemUVPath(_ path: String) -> Bool {
        let expanded = NSString(string: path).expandingTildeInPath
        return [
            "/opt/homebrew/bin/uv",
            "/usr/local/bin/uv",
            NSString(string: "~/.local/bin/uv").expandingTildeInPath
        ].contains(expanded)
    }
}
