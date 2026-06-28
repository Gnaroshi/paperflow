import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var state: AppState

    private var permissions: PermissionStatus {
        PermissionManager.status(launchAtLogin: state.launchAtLogin)
    }

    var body: some View {
        Form {
            Section("PaperFlow") {
                HStack {
                    TextField("paperflow project directory", text: $state.projectPath)
                    Button("Choose") { state.chooseProjectDirectory() }
                }
                HStack {
                    TextField("uv path", text: $state.uvPath)
                    Button("Choose") { state.chooseUVExecutable() }
                }
                HStack {
                    TextField("vault path", text: $state.vaultPath)
                    Button("Choose") { state.chooseVaultDirectory() }
                }
                Picker("Default ingest mode", selection: $state.defaultMode) {
                    ForEach(DefaultRunMode.allCases) { mode in
                        Text(mode.label).tag(mode)
                    }
                }
                .pickerStyle(.segmented)
                Picker("Storage mode", selection: $state.storageModeSetting) {
                    ForEach(StorageModeSetting.allCases) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
                Toggle("Never upload PDFs to Zotero Storage", isOn: $state.neverUploadPDFsToZoteroStorage)
            }

            Section("Drop Shelf") {
                Picker("Activation mode", selection: $state.dropShelfActivationMode) {
                    ForEach(DropShelfActivationMode.allCases) { mode in
                        Text(mode.label).tag(mode)
                    }
                }
                StatusLine(label: "Shortcut", value: state.dropShelfShortcut)
                Picker("Show on", selection: $state.displayMode) {
                    ForEach(DisplayMode.allCases) { mode in
                        Text(mode.label).tag(mode)
                    }
                }
                Picker("Placement", selection: $state.dropShelfPlacement) {
                    ForEach(DropShelfPlacement.allCases) { placement in
                        Text(placement.label).tag(placement)
                    }
                }
                Picker("Focused monitor strategy", selection: $state.focusedMonitorStrategy) {
                    ForEach(FocusedMonitorStrategy.allCases) { strategy in
                        Text(strategy.label).tag(strategy)
                    }
                }
                Toggle("Auto-hide after successful dry-run/apply", isOn: $state.autoHideAfterSuccess)
                Stepper("Auto-hide after \(Int(state.autoCollapseDelay)) seconds idle", value: $state.autoCollapseDelay, in: 1...20, step: 1)
                Toggle("Auto dry-run after drop", isOn: $state.autoDryRunAfterDrop)
                Toggle("Enable hot-zone", isOn: $state.hotZoneEnabled)
                Picker("Edge", selection: $state.hotZoneEdge) {
                    ForEach(HotZoneEdge.allCases) { edge in
                        Text(edge.rawValue).tag(edge)
                    }
                }
                Picker("Corner", selection: $state.hotZoneCorner) {
                    ForEach(HotZoneCorner.allCases) { corner in
                        Text(corner.label).tag(corner)
                    }
                }
                Stepper("Hot-zone width: \(Int(state.hotZoneWidth)) px", value: $state.hotZoneWidth, in: 6...80, step: 2)
                Stepper("Hot-zone height: \(Int(state.hotZoneHeight)) px", value: $state.hotZoneHeight, in: 80...360, step: 10)
                Slider(value: $state.hotZoneIdleOpacity, in: 0.02...0.60) {
                    Text("Idle opacity")
                }
                Text("Hot-zone is inactive unless Activation mode is Hot-Zone on Hover.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Global Shortcuts") {
                TextField("Command window shortcut", text: $state.globalShortcutCommand)
                    .disabled(true)
                StatusLine(label: "Drop shelf", value: state.dropShelfShortcut)
                Text("Option + Shift + I: Finder selection ingest placeholder")
                    .foregroundStyle(.secondary)
                Text("Custom shortcut capture UI is planned; defaults are active through Carbon hot keys.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Zotero Migration Defaults") {
                Picker("Collection mode", selection: $state.collectionMode) {
                    ForEach(CollectionMode.allCases) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
                Picker("Tag mode", selection: $state.tagMode) {
                    ForEach(TagMode.allCases) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
                Text("Apply still requires typed confirmation before any write.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Accounts & API Keys") {
                Picker("API key storage", selection: $state.apiKeyStorageMode) {
                    ForEach(APIKeyStorageMode.allCases) { mode in
                        Text(mode.label).tag(mode)
                    }
                }

                Text("Zotero")
                    .font(.headline)
                Text("The Zotero Web API requires the numeric user ID. Email addresses and usernames do not work for write calls.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                TextField("Numeric Zotero User ID", text: $state.zoteroUserID)
                    .textFieldStyle(.roundedBorder)
                if state.apiKeyStorageMode == .keychain {
                    SecureField("Zotero API Key", text: $state.pendingZoteroAPIKey)
                        .textFieldStyle(.roundedBorder)
                    HStack {
                        Text("Stored Zotero key")
                        Spacer()
                        Text(state.redactedAPIKey)
                            .foregroundStyle(.secondary)
                    }
                    .font(.caption)
                    HStack {
                        Button("Fetch from API Key") {
                            state.verifyAndSaveZoteroAPIKey()
                        }
                        Button("Save unverified key") {
                            state.saveUnverifiedZoteroAPIKey()
                        }
                    }
                } else {
                    Text("PaperFlow will use ZOTERO_API_KEY from the process environment.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                StatusLine(label: "Numeric User ID", value: state.zoteroUserID.isEmpty ? "(not set)" : state.zoteroUserID)
                StatusLine(label: "Username", value: state.zoteroUsername.isEmpty ? "(unknown)" : state.zoteroUsername)
                StatusLine(label: "Library access", value: state.zoteroVerification.libraryAccess ? "yes" : "no")
                StatusLine(label: "Write access", value: state.zoteroVerification.writeAccess ? "yes" : "no")
                StatusLine(label: "Notes access", value: state.zoteroVerification.notesAccess ? "yes" : "no")
                StatusLine(label: "Files access", value: state.zoteroVerification.filesAccess ? "yes" : "no")
                StatusLine(label: "Verification", value: state.zoteroVerification.message)
                if !state.zoteroVerification.writeAccess {
                    Text("Apply migration is blocked until the Zotero key has user library write access.")
                        .font(.caption)
                        .foregroundStyle(.red)
                }
                if !state.zoteroVerification.notesAccess {
                    Text("Notes access is missing or unverified, so note/highlight preservation checks may be incomplete.")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }

                Divider()

                Text("Gemini")
                    .font(.headline)
                if state.apiKeyStorageMode == .keychain {
                    SecureField("Gemini API Key", text: $state.pendingGeminiAPIKey)
                        .textFieldStyle(.roundedBorder)
                    HStack {
                        Text("Stored Gemini key")
                        Spacer()
                        Text(state.redactedGeminiAPIKey)
                            .foregroundStyle(.secondary)
                    }
                    .font(.caption)
                    HStack {
                        Button("Verify Gemini Key") {
                            state.verifyAndSaveGeminiAPIKey()
                        }
                        Button("Save unverified key") {
                            state.saveUnverifiedGeminiAPIKey()
                        }
                    }
                } else {
                    Text("PaperFlow will use GEMINI_API_KEY from the process environment.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Picker("Gemini model", selection: $state.geminiModel) {
                    Text("gemini-2.5-flash").tag("gemini-2.5-flash")
                    Text("gemini-2.5-flash-lite").tag("gemini-2.5-flash-lite")
                    Text("gemini-2.0-flash").tag("gemini-2.0-flash")
                    Text("Custom").tag("custom")
                }
                if state.geminiModel == "custom" {
                    TextField("Custom Gemini model", text: $state.customGeminiModel)
                        .textFieldStyle(.roundedBorder)
                }
                Toggle("Enable Gemini cleanup", isOn: $state.geminiCleanupEnabled)
                Toggle("Stop batch cleanup when Gemini quota is hit", isOn: $state.stopOnGeminiQuotaHit)
                StatusLine(label: "Gemini status", value: state.geminiVerification.message)
                StatusLine(label: "Requests today", value: "\(state.geminiUsage.requestCount)")
                StatusLine(label: "Input tokens", value: "\(state.geminiUsage.inputTokens)")
                StatusLine(label: "Output tokens", value: "\(state.geminiUsage.outputTokens)")
                StatusLine(label: "Total tokens", value: "\(state.geminiUsage.totalTokens)")
                StatusLine(label: "Rate-limit calls", value: "\(state.geminiUsage.failedRateLimitCalls)")
                if let last429 = state.geminiUsage.last429Time {
                    StatusLine(label: "Last 429", value: last429)
                }
                if state.geminiVerification.rateLimited || state.geminiUsage.failedRateLimitCalls > 0 {
                    Text("Gemini Flash is currently rate-limited. Try later or reduce batch size.")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
            }

            Section("Cleanup") {
                Toggle("Enable Gemini for abstract extraction", isOn: $state.enableGeminiAbstractExtraction)
                Toggle("Enable Gemini for metadata extraction", isOn: $state.enableGeminiMetadataExtraction)
                Toggle("Enable Gemini for classification review", isOn: $state.enableGeminiClassificationReview)
                Toggle("Require manual approval for Gemini-generated repairs", isOn: $state.requireManualApprovalForGeminiRepairs)
                Toggle("Never overwrite existing abstract", isOn: $state.neverOverwriteExistingAbstract)
                Toggle("Never delete duplicate with reading work", isOn: $state.neverDeleteDuplicateWithReadingWork)
            }

            Section("Permissions") {
                StatusLine(label: "Files and folders", value: permissions.filesAndFolders)
                StatusLine(label: "Accessibility", value: permissions.accessibility)
                StatusLine(label: "Input monitoring", value: permissions.inputMonitoring)
                StatusLine(label: "Login item", value: permissions.loginItem)
                Button("Open Accessibility Settings") {
                    PermissionManager.openAccessibilitySettings()
                }
            }

            Section("macOS") {
                Toggle("Launch PaperFlow at login", isOn: Binding(
                    get: { state.launchAtLogin },
                    set: { state.setLaunchAtLogin($0) }
                ))
            }
        }
        .formStyle(.grouped)
    }
}
