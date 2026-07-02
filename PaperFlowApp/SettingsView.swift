import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var state: AppState

    private var permissions: PermissionStatus {
        PermissionManager.status(launchAtLogin: state.launchAtLogin)
    }

    var body: some View {
        ZStack {
            PaperFlowAuroraBackground()
                .ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                SectionTitle("Settings")
                Text("경로, 단축키, 계정, Gemini, 로컬 vault 정책을 한 곳에서 관리합니다. API key 원문은 Dashboard와 로그에 표시하지 않습니다.")
                    .foregroundStyle(PaperFlowTheme.muted)

                settingsCard(title: "PaperFlow", icon: "folder") {
                    pathRow("Project directory", text: $state.projectPath, actionTitle: "Choose", action: state.chooseProjectDirectory)
                    pathRow("uv executable", text: $state.uvPath, actionTitle: "Choose", action: state.chooseUVExecutable)
                    pathRow("Local vault", text: $state.vaultPath, actionTitle: "Choose", action: state.chooseVaultDirectory)
                    settingRow("Default ingest") {
                        Picker("Default ingest", selection: $state.defaultMode) {
                            ForEach(DefaultRunMode.allCases) { mode in Text(mode.label).tag(mode) }
                        }
                        .labelsHidden()
                        .pickerStyle(.segmented)
                        .frame(maxWidth: 320)
                    }
                    settingRow("Storage mode") {
                        Picker("Storage mode", selection: $state.storageModeSetting) {
                            ForEach(StorageModeSetting.allCases) { mode in Text(mode.rawValue).tag(mode) }
                        }
                        .labelsHidden()
                        .pickerStyle(.segmented)
                        .frame(maxWidth: 360)
                    }
                    Toggle("Never upload PDFs to Zotero Storage", isOn: $state.neverUploadPDFsToZoteroStorage)
                }

                settingsCard(title: "Drop Shelf", icon: "tray.and.arrow.down") {
                    settingRow("Activation") {
                        Picker("Activation mode", selection: $state.dropShelfActivationMode) {
                            ForEach(DropShelfActivationMode.allCases) { mode in Text(mode.label).tag(mode) }
                        }
                        .labelsHidden()
                        .frame(maxWidth: 360)
                    }
                    settingRow("Drop shelf shortcut") {
                        Picker("Drop shelf shortcut", selection: $state.dropShelfShortcutPreset) {
                            ForEach(DropShelfShortcutPreset.allCases) { preset in Text(preset.label).tag(preset) }
                        }
                        .labelsHidden()
                        .pickerStyle(.segmented)
                        .frame(maxWidth: 360)
                    }
                    helperText(state.dropShelfShortcutPreset.detail)
                    settingRow("Show on") {
                        Picker("Show on", selection: $state.displayMode) {
                            ForEach(DisplayMode.allCases) { mode in Text(mode.label).tag(mode) }
                        }
                        .labelsHidden()
                        .frame(maxWidth: 360)
                    }
                    settingRow("Placement") {
                        Picker("Placement", selection: $state.dropShelfPlacement) {
                            ForEach(DropShelfPlacement.allCases) { placement in Text(placement.label).tag(placement) }
                        }
                        .labelsHidden()
                        .frame(maxWidth: 360)
                    }
                    Toggle("Show PFW across Spaces", isOn: $state.showPFWAcrossSpaces)
                    Toggle("Auto-hide after successful dry-run/apply", isOn: $state.autoHideAfterSuccess)
                    Toggle("Auto dry-run after drop", isOn: $state.autoDryRunAfterDrop)
                    Toggle("Enable hot-zone", isOn: $state.hotZoneEnabled)
                    HStack(spacing: 12) {
                        Stepper("Width \(Int(state.hotZoneWidth)) px", value: $state.hotZoneWidth, in: 6...80, step: 2)
                        Stepper("Height \(Int(state.hotZoneHeight)) px", value: $state.hotZoneHeight, in: 80...360, step: 10)
                    }
                    Slider(value: $state.hotZoneIdleOpacity, in: 0.02...0.60) {
                        Text("Hot-zone opacity")
                    }
                    helperText("Hot-zone은 activation mode가 Hot-Zone on Hover일 때만 활성화됩니다.")
                }

                settingsCard(title: "Global Shortcuts", icon: "keyboard") {
                    settingRow("Command window") {
                        Picker("Command window shortcut", selection: $state.commandShortcutPreset) {
                            ForEach(CommandShortcutPreset.allCases) { preset in Text(preset.label).tag(preset) }
                        }
                        .labelsHidden()
                        .pickerStyle(.segmented)
                        .frame(maxWidth: 320)
                    }
                    helperText(state.commandShortcutPreset.detail)
                    settingRow("Drop shelf") {
                        Text(state.dropShelfShortcutPreset.label)
                            .font(.system(.body, design: .monospaced))
                            .foregroundStyle(PaperFlowTheme.muted)
                    }
                    helperText("단축키를 바꾸면 앱이 전역 hotkey를 즉시 재등록합니다.")
                }

                settingsCard(title: "Accounts & API Keys", icon: "key") {
                    settingRow("Storage") {
                        Picker("API key storage", selection: $state.apiKeyStorageMode) {
                            ForEach(APIKeyStorageMode.allCases) { mode in Text(mode.label).tag(mode) }
                        }
                        .labelsHidden()
                        .pickerStyle(.segmented)
                        .frame(maxWidth: 360)
                    }

                    subhead("Zotero")
                    helperText("Zotero write API는 numeric user ID가 필요합니다. 이메일/username은 write URL에서 실패합니다.")
                    pathRow("Numeric user ID", text: $state.zoteroUserID, actionTitle: "Fetch", action: state.verifyAndSaveZoteroAPIKey)
                    if state.apiKeyStorageMode == .keychain {
                        secureInputRow("API key", text: $state.pendingZoteroAPIKey, actionTitle: "Verify & Save", action: state.verifyAndSaveZoteroAPIKey)
                        keyValue("Stored key", state.redactedAPIKey)
                    } else {
                        helperText("ZOTERO_API_KEY 환경변수를 사용합니다.")
                    }
                    accessGrid
                    if !state.zoteroVerification.writeAccess {
                        WarningBox(text: "Zotero write access가 없으면 apply-migration을 막습니다.")
                    }

                    Rectangle()
                        .fill(PaperFlowTheme.line)
                        .frame(height: 1)

                    subhead("Gemini")
                    if state.apiKeyStorageMode == .keychain {
                        secureInputRow("API key", text: $state.pendingGeminiAPIKey, actionTitle: "Verify & Save", action: state.verifyAndSaveGeminiAPIKey)
                        keyValue("Stored key", state.redactedGeminiAPIKey)
                    } else {
                        helperText("GEMINI_API_KEY 환경변수를 사용합니다.")
                    }
                    settingRow("Model") {
                        Picker("Gemini model", selection: $state.geminiModel) {
                            Text("gemini-2.5-flash").tag("gemini-2.5-flash")
                            Text("gemini-2.5-flash-lite").tag("gemini-2.5-flash-lite")
                            Text("gemini-2.0-flash").tag("gemini-2.0-flash")
                            Text("Custom").tag("custom")
                        }
                        .labelsHidden()
                        .frame(maxWidth: 360)
                    }
                    if state.geminiModel == "custom" {
                        settingRow("Custom model") {
                            TextField("Custom Gemini model", text: $state.customGeminiModel)
                                .paperFlowTextInput()
                                .frame(maxWidth: 360)
                        }
                    }
                    Toggle("Enable Gemini cleanup", isOn: $state.geminiCleanupEnabled)
                    Toggle("Stop batch cleanup when Gemini quota is hit", isOn: $state.stopOnGeminiQuotaHit)
                    geminiUsageGrid
                }

                settingsCard(title: "Zotero Migration Defaults", icon: "books.vertical") {
                    settingRow("Collection mode") {
                        Picker("Collection mode", selection: $state.collectionMode) {
                            ForEach(CollectionMode.allCases) { mode in Text(mode.rawValue).tag(mode) }
                        }
                        .labelsHidden()
                        .frame(maxWidth: 360)
                    }
                    settingRow("Tag mode") {
                        Picker("Tag mode", selection: $state.tagMode) {
                            ForEach(TagMode.allCases) { mode in Text(mode.rawValue).tag(mode) }
                        }
                        .labelsHidden()
                        .frame(maxWidth: 360)
                    }
                    helperText("Apply는 여전히 typed confirmation 없이는 실행되지 않습니다.")
                }

                settingsCard(title: "Cleanup Safety", icon: "checklist") {
                    Toggle("Enable Gemini for abstract extraction", isOn: $state.enableGeminiAbstractExtraction)
                    Toggle("Enable Gemini for metadata extraction", isOn: $state.enableGeminiMetadataExtraction)
                    Toggle("Enable Gemini for classification review", isOn: $state.enableGeminiClassificationReview)
                    Toggle("Require manual approval for Gemini-generated repairs", isOn: $state.requireManualApprovalForGeminiRepairs)
                    Toggle("Never overwrite existing abstract", isOn: $state.neverOverwriteExistingAbstract)
                    Toggle("Never delete duplicate with reading work", isOn: $state.neverDeleteDuplicateWithReadingWork)
                }

                settingsCard(title: "Permissions & macOS", icon: "lock") {
                    keyValue("Files and folders", permissions.filesAndFolders)
                    keyValue("Accessibility", permissions.accessibility)
                    keyValue("Input monitoring", permissions.inputMonitoring)
                    keyValue("Login item", permissions.loginItem)
                    HStack {
                        Button("Open Accessibility Settings") { PermissionManager.openAccessibilitySettings() }
                        Toggle("Launch PaperFlow at login", isOn: Binding(
                            get: { state.launchAtLogin },
                            set: { state.setLaunchAtLogin($0) }
                        ))
                    }
                }
            }
                .frame(maxWidth: 980, alignment: .leading)
                .padding(18)
                .padding(.bottom, 24)
            }
        }
        .foregroundStyle(PaperFlowTheme.ink)
        .preferredColorScheme(.dark)
    }

    private var accessGrid: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 160), spacing: 10)], spacing: 10) {
            MiniSettingTile(title: "User ID", value: state.zoteroUserID.isEmpty ? "not set" : state.zoteroUserID)
            MiniSettingTile(title: "Username", value: state.zoteroUsername.isEmpty ? "unknown" : state.zoteroUsername)
            MiniSettingTile(title: "Library", value: state.zoteroVerification.libraryAccess ? "yes" : "no")
            MiniSettingTile(title: "Write", value: state.zoteroVerification.writeAccess ? "yes" : "no")
            MiniSettingTile(title: "Notes", value: state.zoteroVerification.notesAccess ? "yes" : "no")
            MiniSettingTile(title: "Files", value: state.zoteroVerification.filesAccess ? "yes" : "no")
        }
    }

    private var geminiUsageGrid: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 170), spacing: 10)], spacing: 10) {
            MiniSettingTile(title: "Status", value: state.geminiVerification.message)
            MiniSettingTile(title: "Quota", value: state.geminiUsage.quotaStatus)
            MiniSettingTile(title: "Requests", value: "\(state.geminiUsage.requestCount)")
            MiniSettingTile(title: "Tokens", value: "\(state.geminiUsage.totalTokens)")
            MiniSettingTile(title: "429 calls", value: "\(state.geminiUsage.failedRateLimitCalls)")
        }
    }

    private func settingsCard<Content: View>(title: String, icon: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .foregroundStyle(PaperFlowTheme.sky)
                    .frame(width: 22)
                Text(title)
                    .font(.headline)
                Spacer()
            }
            content()
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .paperFlowCard(tint: PaperFlowTheme.sky, radius: 16)
    }

    private func settingRow<Content: View>(_ label: String, @ViewBuilder content: () -> Content) -> some View {
        HStack(alignment: .center, spacing: 14) {
            Text(label)
                .font(.callout)
                .fontWeight(.medium)
                .frame(width: 170, alignment: .leading)
            content()
            Spacer(minLength: 0)
        }
    }

    private func pathRow(_ label: String, text: Binding<String>, actionTitle: String, action: @escaping () -> Void) -> some View {
        settingRow(label) {
            TextField(label, text: text)
                .paperFlowTextInput()
                .font(.system(.body, design: .monospaced))
                .frame(minWidth: 260)
            Button(actionTitle, action: action)
        }
    }

    private func secureInputRow(_ label: String, text: Binding<String>, actionTitle: String, action: @escaping () -> Void) -> some View {
        settingRow(label) {
            SecureField(label, text: text)
                .paperFlowTextInput()
                .frame(minWidth: 260)
            Button(actionTitle, action: action)
        }
    }

    private func keyValue(_ label: String, _ value: String) -> some View {
        settingRow(label) {
            Text(value.isEmpty ? "-" : value)
                .foregroundStyle(PaperFlowTheme.muted)
                .textSelection(.enabled)
        }
    }

    private func subhead(_ value: String) -> some View {
        Text(value)
            .font(.subheadline)
            .fontWeight(.semibold)
            .padding(.top, 4)
    }

    private func helperText(_ value: String) -> some View {
        Text(value)
            .font(.caption)
            .foregroundStyle(PaperFlowTheme.muted)
    }
}

private struct MiniSettingTile: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption2)
                .foregroundStyle(PaperFlowTheme.muted)
            Text(value)
                .font(.caption)
                .fontWeight(.medium)
                .lineLimit(2)
                .textSelection(.enabled)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .paperFlowCard(tint: PaperFlowTheme.lilac, radius: 10)
    }
}
