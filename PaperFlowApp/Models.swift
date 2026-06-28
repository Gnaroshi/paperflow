import Foundation

enum AppSection: String, CaseIterable, Identifiable {
    case dashboard = "Dashboard"
    case dropShelfSettings = "Drop Shelf Settings"
    case zoteroOrganize = "Zotero Organize"
    case localVault = "Local Vault"
    case existingAttachments = "Existing Attachments"
    case cleanupWorkbench = "Cleanup Workbench"
    case reports = "Reports"
    case settings = "Settings"
    case logs = "Logs"

    var id: String { rawValue }

    var symbolName: String {
        switch self {
        case .dashboard:
            return "gauge.with.dots.needle.67percent"
        case .dropShelfSettings:
            return "tray.and.arrow.down"
        case .zoteroOrganize:
            return "books.vertical"
        case .localVault:
            return "externaldrive"
        case .existingAttachments:
            return "paperclip"
        case .cleanupWorkbench:
            return "checklist"
        case .reports:
            return "doc.text.magnifyingglass"
        case .settings:
            return "gearshape"
        case .logs:
            return "terminal"
        }
    }
}

struct DroppedPDF: Identifiable, Hashable {
    let id = UUID()
    let url: URL

    var name: String {
        url.lastPathComponent
    }
}

enum DefaultRunMode: String, CaseIterable, Identifiable {
    case dryRun = "dry-run"
    case apply = "apply"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .dryRun:
            return "Dry Run"
        case .apply:
            return "Apply"
        }
    }
}

enum DisplayMode: String, CaseIterable, Identifiable {
    case focusedMonitor
    case cursorMonitor
    case allMonitors
    case primaryMonitor

    var id: String { rawValue }

    var label: String {
        switch self {
        case .focusedMonitor:
            return "Focused Monitor"
        case .cursorMonitor:
            return "Cursor Monitor"
        case .allMonitors:
            return "All Monitors"
        case .primaryMonitor:
            return "Primary Monitor"
        }
    }
}

enum DropShelfActivationMode: String, CaseIterable, Identifiable {
    case keyboardShortcutOnly
    case hotZoneOnHover
    case alwaysShowCompact
    case menuBarOnly

    var id: String { rawValue }

    var label: String {
        switch self {
        case .keyboardShortcutOnly:
            return "Keyboard Shortcut Only"
        case .hotZoneOnHover:
            return "Hot-Zone on Hover"
        case .alwaysShowCompact:
            return "Always Show Compact Shelf"
        case .menuBarOnly:
            return "Menu Bar Only"
        }
    }
}

enum DropShelfPlacement: String, CaseIterable, Identifiable {
    case bottomCenter
    case bottomRight
    case rightEdge
    case custom

    var id: String { rawValue }

    var label: String {
        switch self {
        case .bottomCenter:
            return "Bottom Center"
        case .bottomRight:
            return "Bottom Right"
        case .rightEdge:
            return "Right Edge"
        case .custom:
            return "Custom"
        }
    }
}

enum FocusedMonitorStrategy: String, CaseIterable, Identifiable {
    case keyboardMainScreen
    case cursorScreen
    case frontmostAppWindowScreen

    var id: String { rawValue }

    var label: String {
        switch self {
        case .keyboardMainScreen:
            return "Keyboard Main Screen"
        case .cursorScreen:
            return "Cursor Screen"
        case .frontmostAppWindowScreen:
            return "Frontmost App Window"
        }
    }
}

enum HotZoneEdge: String, CaseIterable, Identifiable {
    case right
    case bottom
    case top
    case left

    var id: String { rawValue }
}

enum HotZoneCorner: String, CaseIterable, Identifiable {
    case bottomRight
    case topRight
    case bottomLeft
    case topLeft

    var id: String { rawValue }

    var label: String {
        switch self {
        case .bottomRight:
            return "Bottom Right"
        case .topRight:
            return "Top Right"
        case .bottomLeft:
            return "Bottom Left"
        case .topLeft:
            return "Top Left"
        }
    }
}

enum APIKeyStorageMode: String, CaseIterable, Identifiable {
    case environmentVariables
    case keychain

    var id: String { rawValue }

    var label: String {
        switch self {
        case .environmentVariables:
            return "Environment Variables"
        case .keychain:
            return "Keychain"
        }
    }
}

enum StorageModeSetting: String, CaseIterable, Identifiable {
    case linkedLocalOnly = "linked-local only"
    case askEveryTime = "ask every time"

    var id: String { rawValue }
}

enum DropShelfPhase: String {
    case idleCompact
    case hoveringValidPDF
    case hoveringInvalidFile
    case queued
    case processing
    case success
    case failure
    case reviewNeeded

    var label: String {
        switch self {
        case .idleCompact:
            return "Drop PDFs"
        case .hoveringValidPDF:
            return "Release to preview PDFs"
        case .hoveringInvalidFile:
            return "PDFs Only"
        case .queued:
            return "PDFs Queued"
        case .processing:
            return "Processing"
        case .success:
            return "Success"
        case .failure:
            return "Failure"
        case .reviewNeeded:
            return "Review Needed"
        }
    }
}

enum DropShelfAction: String, CaseIterable, Identifiable {
    case dryRunIngest
    case applyIngest
    case addToZoteroInbox
    case organizeWithAILibrary

    var id: String { rawValue }

    var label: String {
        switch self {
        case .dryRunIngest:
            return "Dry Run Ingest"
        case .applyIngest:
            return "Apply Ingest"
        case .addToZoteroInbox:
            return "Add to Zotero Inbox"
        case .organizeWithAILibrary:
            return "Organize with AI Library"
        }
    }
}

enum RunStatus: Equatable {
    case idle
    case running
    case succeeded(Int32)
    case failed(Int32)
    case timedOut
    case cancelled

    var label: String {
        switch self {
        case .idle:
            return "Idle"
        case .running:
            return "Running"
        case .succeeded:
            return "Succeeded"
        case .failed(let code):
            return "Failed (\(code))"
        case .timedOut:
            return "Timed out"
        case .cancelled:
            return "Cancelled"
        }
    }
}

enum ConfirmationKind: Identifiable {
    case applyIngest
    case applyMigration
    case cleanupDeleteEmpty
    case localizeAttachments
    case cleanupStoredAttachments
    case applyAbstractRepairs
    case applyMetadataRepairs
    case applySelectedAbstractRepair(String)
    case applySelectedMetadataRepair(String, [String])

    var id: String {
        switch self {
        case .applySelectedAbstractRepair(let itemKey):
            return "\(title)-\(itemKey)"
        case .applySelectedMetadataRepair(let itemKey, let fields):
            return "\(title)-\(itemKey)-\(fields.joined(separator: ","))"
        default:
            return title
        }
    }

    var title: String {
        switch self {
        case .applyIngest:
            return "Apply Ingest"
        case .applyMigration:
            return "Apply Zotero Migration"
        case .cleanupDeleteEmpty:
            return "Delete Empty Old Collections"
        case .localizeAttachments:
            return "Localize Zotero PDF Attachments"
        case .cleanupStoredAttachments:
            return "Delete Old Stored PDF Attachments"
        case .applyAbstractRepairs:
            return "Apply Abstract Repairs"
        case .applyMetadataRepairs:
            return "Apply Metadata Repairs"
        case .applySelectedAbstractRepair(let itemKey):
            return "Apply Abstract Repair: \(itemKey)"
        case .applySelectedMetadataRepair(let itemKey, _):
            return "Apply Metadata Repair: \(itemKey)"
        }
    }

    var requiredText: String {
        switch self {
        case .applyIngest:
            return "INGEST LOCAL PDFS"
        case .applyMigration:
            return "REPLACE MY ZOTERO COLLECTIONS"
        case .cleanupDeleteEmpty:
            return "DELETE EMPTY OLD COLLECTIONS"
        case .localizeAttachments:
            return "LOCALIZE ZOTERO PDF ATTACHMENTS"
        case .cleanupStoredAttachments:
            return "DELETE OLD STORED PDF ATTACHMENTS"
        case .applyAbstractRepairs:
            return "APPLY ABSTRACT REPAIRS"
        case .applyMetadataRepairs, .applySelectedMetadataRepair:
            return "APPLY METADATA REPAIRS"
        case .applySelectedAbstractRepair:
            return "APPLY ABSTRACT REPAIRS"
        }
    }

    var warning: String {
        switch self {
        case .applyIngest:
            return "This should copy PDFs into the local vault and create linked Zotero attachments only. It must not upload PDFs to Zotero Storage."
        case .applyMigration:
            return "This changes Zotero collections/tags only. It does not move PDFs. Zotero Desktop must sync to display Web API changes. It should not delete notes, annotations, highlights, or attachments."
        case .cleanupDeleteEmpty:
            return "This deletes old non-AI-Library collections only when paperflow reports them empty."
        case .localizeAttachments:
            return "This should convert stored Zotero PDFs into linked local attachments. Review the plan before applying."
        case .cleanupStoredAttachments:
            return "Do not run unless verify report succeeded. Never delete stored attachments that contain notes, annotations, or highlights unless explicitly reviewed."
        case .applyAbstractRepairs:
            return "This updates Zotero abstractNote only for high-confidence repairs and should not overwrite existing abstracts unless backend options explicitly allow it."
        case .applyMetadataRepairs:
            return "This updates Zotero metadata fields from reviewed repair proposals. It must not replace stronger metadata with weaker metadata."
        case .applySelectedAbstractRepair(let itemKey):
            return "This updates Zotero abstractNote for item \(itemKey) only if the repair is high-confidence."
        case .applySelectedMetadataRepair(let itemKey, let fields):
            let fieldList = fields.isEmpty ? "the selected repair fields" : fields.joined(separator: ", ")
            return "This updates \(fieldList) for Zotero item \(itemKey) only."
        }
    }
}

enum CollectionMode: String, CaseIterable, Identifiable {
    case addOnly = "add-only"
    case replaceAll = "replace-all"
    case replaceNonProtected = "replace-non-protected"

    var id: String { rawValue }
}

enum TagMode: String, CaseIterable, Identifiable {
    case appendNormalized = "append-normalized"
    case replaceManaged = "replace-managed"
    case replaceAll = "replace-all"

    var id: String { rawValue }
}

struct DashboardSummary {
    var plannedItems = 0
    var duplicateCandidates = 0
    var missingMetadataItems = 0
    var missingAbstractItems = 0
    var lowConfidenceItems = 0
    var nonPaperItems = 0
    var sourceItems = 0
    var itemUpdates = 0
    var collectionsToCreate = 0
    var oldCollectionsWouldBeEmpty = 0
    var latestMigrationStatus = "No migration plan found"
    var latestApplyStatus = "No apply log found"
    var latestCleanupStatus = "No cleanup report found"
    var latestMigrationAuditStatus = "No migration audit found"
    var latestStoredPDFLocalizationStatus = "No localization report found"
}

struct VaultStatus {
    var path: String
    var exists = false
    var fileCount = 0
    var pdfCount = 0
    var totalBytes: UInt64 = 0
    var instructionsShown = false
    var lastIngest = "No ingest log found"

    var totalSizeLabel: String {
        ByteCountFormatter.string(fromByteCount: Int64(totalBytes), countStyle: .file)
    }
}

struct BackendCapability {
    var ingestLinkedLocal = false
    var vaultCommands = false
    var localizeAttachmentCommands = false
}

struct ZoteroCredentialStatus {
    var verified = false
    var message = "Not verified"
    var numericUserID = ""
    var username = ""
    var libraryAccess = false
    var writeAccess = false
    var notesAccess = false
    var filesAccess = false

    var writeAccessLabel: String {
        writeAccess ? "yes" : "no"
    }
}

struct GeminiCredentialStatus {
    var verified = false
    var rateLimited = false
    var message = "Not verified"
    var model = "gemini-2.5-flash"
}

struct GeminiUsageSummary {
    var date = ""
    var requestCount = 0
    var inputTokens = 0
    var outputTokens = 0
    var totalTokens = 0
    var failedRateLimitCalls = 0
    var last429Time: String?

    var quotaStatus: String {
        if failedRateLimitCalls > 0 {
            return "Rate-limited"
        }
        if requestCount > 0 {
            return "Active"
        }
        return "No usage today"
    }
}

struct FieldDiff: Identifiable, Hashable {
    var id: String { field }
    let field: String
    let before: String
    let after: String
}

struct CleanupWorkbenchItem: Identifiable, Hashable {
    var id: String { itemKey }
    let itemKey: String
    let title: String
    let currentCollections: [String]
    let plannedCollections: [String]
    let normalizedTags: [String]
    let confidence: Double
    let rationale: String
    let metadataIssues: [String]
    let doi: String
    let arxivID: String
    let url: String
    let publicationTitle: String
    let year: String
    let abstractStatus: String
    let currentAbstract: String
    let pdfAttachmentStatus: String
    let noteCount: Int
    let annotationCount: Int
    let highlightCount: Int
    let underlineCount: Int
    let childNoteCount: Int
    let readingWorkPresent: Bool
    let duplicateRole: String
    let canonicalItemKey: String
    let localPDFPaths: [String]
    var proposedAbstract: String = ""
    var abstractEvidenceSource: String = ""
    var abstractRepairConfidence: Double = 0
    var metadataDiffs: [FieldDiff] = []
}

struct DuplicateWorkbenchItem: Identifiable, Hashable {
    var id: String { itemKey }
    let itemKey: String
    let title: String
    let doi: String
    let arxivID: String
    let url: String
    let year: String
    let publicationTitle: String
    let currentCollections: [String]
    let plannedCollections: [String]
    let metadataScore: String
    let noteCount: Int
    let annotationCount: Int
    let highlightCount: Int
    let underlineCount: Int
    let commentCount: Int
    let pdfAttachmentCount: Int
    let pdfStatus: String
    let localPDFPaths: [String]
    let isCanonical: Bool
    let unsafeToDelete: Bool
}

struct DuplicateWorkbenchGroup: Identifiable, Hashable {
    let id: String
    let normalizedTitle: String
    let matchType: String
    let canonicalItemKey: String
    let recommendedAction: String
    let metadataMergeSuggested: Bool
    let suggestedMetadataSourceItemKey: String
    let items: [DuplicateWorkbenchItem]
}

struct CleanupWorkbenchData {
    var allItems: [CleanupWorkbenchItem] = []
    var missingAbstract: [CleanupWorkbenchItem] = []
    var missingMetadata: [CleanupWorkbenchItem] = []
    var lowConfidence: [CleanupWorkbenchItem] = []
    var nonPaper: [CleanupWorkbenchItem] = []
    var duplicateGroups: [DuplicateWorkbenchGroup] = []
}

struct CommandSpec {
    let executable: String
    let arguments: [String]
    let workingDirectory: URL
    let environment: [String: String]
    let timeoutSeconds: TimeInterval
    let redactedSecrets: [String]
    var isDestructive: Bool = false

    var displayCommand: String {
        ([executable] + arguments).map(Self.shellQuoted).joined(separator: " ")
    }

    var redactedDisplayCommand: String {
        redact(displayCommand)
    }

    func redact(_ text: String) -> String {
        var redacted = text
        for secret in redactedSecrets where !secret.isEmpty {
            redacted = redacted.replacingOccurrences(of: secret, with: "••••REDACTED••••")
        }
        return redacted
    }

    private static func shellQuoted(_ value: String) -> String {
        if value.range(of: #"^[A-Za-z0-9_@%+=:,./-]+$"#, options: .regularExpression) != nil {
            return value
        }
        return "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }
}
