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
                Text("PDF library, Drop Shelf, Zotero 연결과 macOS 동작을 관리합니다.")
                    .foregroundStyle(PaperFlowTheme.muted)

                settingsCard(title: "PDF Library", icon: "folder") {
                    pathRow("PDF library", detail: "새 PDF를 이 Mac에 보관할 위치", text: $state.vaultPath, actionTitle: "Choose", action: state.chooseVaultDirectory)
                    settingRow("Default ingest", detail: "PDF drop 이후 기본 실행 모드") {
                        Picker("Default ingest", selection: $state.defaultMode) {
                            ForEach(DefaultRunMode.allCases) { mode in Text(mode.label).tag(mode) }
                        }
                        .labelsHidden()
                        .pickerStyle(.segmented)
                        .frame(maxWidth: .infinity)
                    }
                    settingToggle(
                        "Keep PDFs on this Mac",
                        detail: "PDF는 선택한 library에 보관하고 Zotero에는 위치만 연결",
                        isOn: $state.neverUploadPDFsToZoteroStorage
                    )
                    Text("Zotero data sync는 논문 정보만 동기화합니다. PDF cloud upload는 사용하지 않습니다.")
                        .font(.callout)
                        .foregroundStyle(PaperFlowTheme.muted)
                }

                settingsCard(title: "Drop Shelf", icon: "tray.and.arrow.down") {
                    settingRow("Activation", detail: "PFW가 나타나는 조건") {
                        Picker("Activation mode", selection: $state.dropShelfActivationMode) {
                            ForEach(DropShelfActivationMode.allCases) { mode in Text(mode.label).tag(mode) }
                        }
                        .labelsHidden()
                        .frame(maxWidth: .infinity)
                    }
                    settingRow("Drop shelf shortcut", detail: state.dropShelfShortcutPreset.detail) {
                        Picker("Drop shelf shortcut", selection: $state.dropShelfShortcutPreset) {
                            ForEach(DropShelfShortcutPreset.allCases) { preset in Text(preset.label).tag(preset) }
                        }
                        .labelsHidden()
                        .pickerStyle(.segmented)
                        .frame(maxWidth: .infinity)
                    }
                    settingRow("Show on", detail: "PFW를 표시할 monitor") {
                        Picker("Show on", selection: $state.displayMode) {
                            ForEach(DisplayMode.allCases) { mode in Text(mode.label).tag(mode) }
                        }
                        .labelsHidden()
                        .frame(maxWidth: .infinity)
                    }
                    settingRow("Placement", detail: "선택한 monitor 안의 위치") {
                        Picker("Placement", selection: $state.dropShelfPlacement) {
                            ForEach(DropShelfPlacement.allCases) { placement in Text(placement.label).tag(placement) }
                        }
                        .labelsHidden()
                        .frame(maxWidth: .infinity)
                    }
                    settingToggle("Follow across Spaces", detail: "Desktop을 전환해도 PFW를 현재 작업 옆에 유지", isOn: $state.showPFWAcrossSpaces)
                    settingToggle("Auto-hide after success", detail: "성공 결과 표시 후 PFW 숨김", isOn: $state.autoHideAfterSuccess)
                    settingToggle("Auto preview after drop", detail: "Drop 직후 PDF를 자동으로 확인", isOn: $state.autoDryRunAfterDrop)
                    settingToggle("Enable hot-zone", detail: "PDF를 화면 가장자리로 끌면 PFW 표시", isOn: $state.hotZoneEnabled)
                    if state.hotZoneEnabled {
                        settingRow("Hot-zone size", detail: "Activation surface의 폭과 높이") {
                            HStack(spacing: PaperFlowSpacing.md) {
                                Stepper("W \(Int(state.hotZoneWidth))", value: $state.hotZoneWidth, in: 6...80, step: 2)
                                Stepper("H \(Int(state.hotZoneHeight))", value: $state.hotZoneHeight, in: 80...360, step: 10)
                            }
                        }
                        settingRow("Hot-zone opacity") {
                            HStack(spacing: PaperFlowSpacing.sm) {
                                Slider(value: $state.hotZoneIdleOpacity, in: 0.02...0.60)
                                Text(state.hotZoneIdleOpacity, format: .number.precision(.fractionLength(2)))
                                    .font(.caption.monospacedDigit())
                                    .frame(width: 40, alignment: .trailing)
                            }
                        }
                    }
                }

                settingsCard(title: "Global Shortcuts", icon: "keyboard") {
                    settingRow("Command window", detail: state.commandShortcutPreset.detail) {
                        Picker("Command window shortcut", selection: $state.commandShortcutPreset) {
                            ForEach(CommandShortcutPreset.allCases) { preset in Text(preset.label).tag(preset) }
                        }
                        .labelsHidden()
                        .pickerStyle(.segmented)
                        .frame(maxWidth: .infinity)
                    }
                    settingRow("Drop shelf", detail: state.dropShelfShortcutPreset.detail) {
                        Picker("Drop shelf shortcut", selection: $state.dropShelfShortcutPreset) {
                            ForEach(DropShelfShortcutPreset.allCases) { preset in Text(preset.label).tag(preset) }
                        }
                        .labelsHidden()
                        .pickerStyle(.segmented)
                        .frame(maxWidth: .infinity)
                    }
                }

                settingsCard(title: "Connections", icon: "key") {
                    SettingsSubsectionHeader(
                        "Zotero",
                        detail: "Apply를 사용하려면 Zotero 연결과 write access가 필요합니다."
                    )
                    pathRow("Account ID", detail: "API key 확인 시 자동으로 가져옵니다.", text: $state.zoteroUserID, actionTitle: "Fetch", action: state.verifyAndSaveZoteroAPIKey)
                    if state.apiKeyStorageMode == .keychain {
                        secureInputRow("API key", detail: "Keychain에 저장하고 접근 권한을 검증", text: $state.pendingZoteroAPIKey, actionTitle: "Verify & Save", action: state.verifyAndSaveZoteroAPIKey)
                        keyValue("Stored key", state.redactedAPIKey)
                    } else {
                        settingRow("API key") {
                            Text("Managed outside PaperFlow. Open Advanced & Diagnostics to change this mode.")
                                .foregroundStyle(PaperFlowTheme.muted)
                        }
                    }
                    if state.showTechnicalDetails {
                        accessGrid
                    }
                    if !state.zoteroVerification.writeAccess {
                        WarningBox(text: "Zotero에서 변경을 적용하려면 write access가 필요합니다.")
                    }

                    Rectangle()
                        .fill(PaperFlowTheme.line)
                        .frame(height: 1)

                    SettingsSubsectionHeader("Gemini", detail: "Cleanup과 ambiguous classification에서만 선택적으로 사용합니다.")
                    if state.apiKeyStorageMode == .keychain {
                        secureInputRow("API key", detail: "검증 성공 시 Keychain에 저장", text: $state.pendingGeminiAPIKey, actionTitle: "Verify & Save", action: state.verifyAndSaveGeminiAPIKey)
                        keyValue("Stored key", state.redactedGeminiAPIKey)
                    } else {
                        settingRow("API key") {
                            Text("Managed outside PaperFlow. Open Advanced & Diagnostics to change this mode.")
                                .foregroundStyle(PaperFlowTheme.muted)
                        }
                    }
                    settingRow("Model", detail: "Cleanup 요청에 사용할 Gemini Flash model") {
                        Picker("Gemini model", selection: $state.geminiModel) {
                            Text("gemini-2.5-flash").tag("gemini-2.5-flash")
                            Text("gemini-2.5-flash-lite").tag("gemini-2.5-flash-lite")
                            Text("gemini-2.0-flash").tag("gemini-2.0-flash")
                            Text("Custom").tag("custom")
                        }
                        .labelsHidden()
                        .frame(maxWidth: .infinity)
                    }
                    if state.geminiModel == "custom" {
                        settingRow("Custom model") {
                            TextField("Custom Gemini model", text: $state.customGeminiModel)
                                .paperFlowTextInput()
                                .frame(maxWidth: .infinity)
                        }
                    }
                    settingToggle("Enable Gemini cleanup", detail: "기본 분류로 결정하기 어려운 경우에만 사용", isOn: $state.geminiCleanupEnabled)
                    if state.showTechnicalDetails {
                        settingToggle("Stop on quota limit", detail: "Stop a batch when the provider rejects more requests", isOn: $state.stopOnGeminiQuotaHit)
                        geminiUsageGrid
                    }
                }

                settingsCard(title: "Advanced & Diagnostics", icon: "wrench.and.screwdriver") {
                    settingToggle(
                        "Show technical details",
                        detail: "경로, raw status, reports와 logs를 표시합니다. 기본 화면에는 필요하지 않은 정보입니다.",
                        isOn: $state.showTechnicalDetails
                    )
                    if state.showTechnicalDetails {
                        pathRow("Project directory", detail: "PaperFlow source and local data", text: $state.projectPath, actionTitle: "Choose", action: state.chooseProjectDirectory)
                        pathRow("uv executable", detail: "Python command runner", text: $state.uvPath, actionTitle: "Choose", action: state.chooseUVExecutable)
                        pathRow("Zotero storage", detail: "Existing Zotero-managed PDF source", text: $state.zoteroStoragePath, actionTitle: "Choose", action: state.chooseZoteroStorageDirectory)
                        settingRow("API key storage") {
                            Picker("API key storage", selection: $state.apiKeyStorageMode) {
                                ForEach(APIKeyStorageMode.allCases) { mode in Text(mode.label).tag(mode) }
                            }
                            .labelsHidden()
                            .pickerStyle(.segmented)
                            .frame(maxWidth: .infinity)
                        }
                        settingRow("Storage mode") {
                            Picker("Storage mode", selection: $state.storageModeSetting) {
                                ForEach(StorageModeSetting.allCases) { mode in Text(mode.rawValue).tag(mode) }
                            }
                            .labelsHidden()
                            .pickerStyle(.segmented)
                            .frame(maxWidth: .infinity)
                        }
                        SettingsActionBar {
                            Button("Open Reports") { state.selectedSection = .reports }
                            Button("Open Logs") { state.selectedSection = .logs }
                            Button("Open Project") { state.openProjectFolder() }
                            Button("Open App Logs") { state.openAppLogsFolder() }
                        }
                    }
                }

                if state.showTechnicalDetails {
                    settingsCard(title: "Migration Defaults", icon: "books.vertical") {
                        settingRow("Collection mode", detail: "How Apply treats existing collections") {
                            Picker("Collection mode", selection: $state.collectionMode) {
                                ForEach(CollectionMode.allCases) { mode in Text(mode.rawValue).tag(mode) }
                            }
                            .labelsHidden()
                            .frame(maxWidth: .infinity)
                        }
                        settingRow("Tag mode", detail: "Which managed tags Apply replaces") {
                            Picker("Tag mode", selection: $state.tagMode) {
                                ForEach(TagMode.allCases) { mode in Text(mode.rawValue).tag(mode) }
                            }
                            .labelsHidden()
                            .frame(maxWidth: .infinity)
                        }
                        settingRow("Apply safety") {
                            Label("Current backup and preview required", systemImage: "lock.fill")
                                .foregroundStyle(PaperFlowTheme.muted)
                        }
                    }

                    settingsCard(title: "Cleanup Safety", icon: "checklist") {
                        settingToggle("Gemini abstract extraction", detail: "Extract only from supplied PDF text", isOn: $state.enableGeminiAbstractExtraction)
                        settingToggle("Gemini metadata extraction", detail: "Extract fields without inventing values", isOn: $state.enableGeminiMetadataExtraction)
                        settingToggle("Gemini classification review", detail: "Review only low-confidence classification", isOn: $state.enableGeminiClassificationReview)
                        settingToggle("Manual approval required", detail: "Never apply Gemini repairs automatically", isOn: $state.requireManualApprovalForGeminiRepairs)
                        settingToggle("Preserve existing abstract", detail: "Never replace a non-empty abstract", isOn: $state.neverOverwriteExistingAbstract)
                        settingToggle("Preserve duplicate reading work", detail: "Keep duplicates that contain notes or annotations", isOn: $state.neverDeleteDuplicateWithReadingWork)
                    }
                }

                settingsCard(title: "Permissions & macOS", icon: "lock") {
                    keyValue("Files and folders", permissions.filesAndFolders)
                    keyValue("Accessibility", permissions.accessibility)
                    if state.showTechnicalDetails {
                        keyValue("Input monitoring", permissions.inputMonitoring)
                        keyValue("Login item", permissions.loginItem)
                    }
                    settingToggle("Launch at login", detail: "macOS login 후 PaperFlow 자동 실행", isOn: Binding(
                        get: { state.launchAtLogin },
                        set: { state.setLaunchAtLogin($0) }
                    ))
                    SettingsActionBar {
                        Button("Open Accessibility Settings") { PermissionManager.openAccessibilitySettings() }
                    }
                }
            }
                .frame(maxWidth: 1100, alignment: .leading)
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
        VStack(alignment: .leading, spacing: PaperFlowSpacing.md) {
            HStack(spacing: PaperFlowSpacing.sm) {
                Image(systemName: icon)
                    .foregroundStyle(PaperFlowTheme.sky)
                    .frame(width: 22)
                Text(title)
                    .font(.headline)
                Spacer()
            }
            content()
        }
        .padding(PaperFlowSpacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .paperFlowCard(tint: PaperFlowTheme.sky, radius: 16)
    }

    private func settingRow<Content: View>(
        _ label: String,
        detail: String? = nil,
        @ViewBuilder content: () -> Content
    ) -> some View {
        ResponsiveSettingRow(label, detail: detail) {
            content()
        }
    }

    private func settingToggle(
        _ label: String,
        detail: String? = nil,
        isOn: Binding<Bool>
    ) -> some View {
        SettingsToggleRow(label, detail: detail, isOn: isOn)
    }

    private func pathRow(
        _ label: String,
        detail: String? = nil,
        text: Binding<String>,
        actionTitle: String,
        action: @escaping () -> Void
    ) -> some View {
        settingRow(label, detail: detail) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: PaperFlowSpacing.xs) {
                    TextField(label, text: text)
                        .paperFlowTextInput()
                        .font(.system(.body, design: .monospaced))
                    Button(actionTitle, action: action)
                        .frame(minWidth: 74)
                }
                VStack(alignment: .leading, spacing: PaperFlowSpacing.xs) {
                    TextField(label, text: text)
                        .paperFlowTextInput()
                        .font(.system(.body, design: .monospaced))
                    Button(actionTitle, action: action)
                }
            }
        }
    }

    private func secureInputRow(
        _ label: String,
        detail: String? = nil,
        text: Binding<String>,
        actionTitle: String,
        action: @escaping () -> Void
    ) -> some View {
        settingRow(label, detail: detail) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: PaperFlowSpacing.xs) {
                    SecureField(label, text: text)
                        .paperFlowTextInput()
                    Button(actionTitle, action: action)
                        .frame(minWidth: 96)
                }
                VStack(alignment: .leading, spacing: PaperFlowSpacing.xs) {
                    SecureField(label, text: text)
                        .paperFlowTextInput()
                    Button(actionTitle, action: action)
                }
            }
        }
    }

    private func keyValue(_ label: String, _ value: String) -> some View {
        settingRow(label) {
            Text(value.isEmpty ? "-" : value)
                .foregroundStyle(PaperFlowTheme.muted)
                .textSelection(.enabled)
        }
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
