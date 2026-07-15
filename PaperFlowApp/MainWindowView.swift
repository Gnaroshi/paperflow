import SwiftUI

struct MainWindowView: View {
    @EnvironmentObject private var state: AppState
    @State private var confirmation: ConfirmationKind?
    @State private var confirmationText = ""
    @State private var sidebarCollapsed = false
    @State private var commandLogExpanded = false

    var body: some View {
        GeometryReader { geometry in
            let usesRail = sidebarCollapsed || geometry.size.width < 900
            let sidebarWidth = usesRail ? 52 : min(236, max(208, geometry.size.width * 0.20))
            let contentPadding: CGFloat = geometry.size.width < 940 ? 14 : 22
            ZStack {
                PaperFlowAuroraBackground()
                    .ignoresSafeArea()
                HStack(spacing: 0) {
                    SidebarRailOrFullSidebar(
                        selectedSection: $state.selectedSection,
                        isCollapsed: $sidebarCollapsed,
                        forceRail: geometry.size.width < 900,
                        showTechnicalDetails: state.showTechnicalDetails
                    )
                    .frame(width: sidebarWidth)
                    .animation(.easeInOut(duration: 0.16), value: sidebarCollapsed)

                    Rectangle()
                        .fill(PaperFlowTheme.line)
                        .frame(width: 1)

                    VStack(spacing: 0) {
                        HeaderView(compact: geometry.size.width < 980)
                        Rectangle()
                            .fill(PaperFlowTheme.line)
                            .frame(height: 1)
                        if !state.invalidDropWarnings.isEmpty {
                            PersistentNotice(
                                message: state.invalidDropWarnings[0],
                                dismiss: { state.invalidDropWarnings.removeAll() }
                            )
                            .padding(.horizontal, contentPadding)
                            .padding(.top, 12)
                        }
                        ScrollView {
                            sectionView
                                .padding(.horizontal, contentPadding)
                                .padding(.vertical, 18)
                                .frame(maxWidth: 1240, alignment: .topLeading)
                                .frame(maxWidth: .infinity, alignment: .top)
                        }
                        .id(state.selectedSection)
                        Rectangle()
                            .fill(PaperFlowTheme.line)
                            .frame(height: 1)
                        if state.showTechnicalDetails {
                            CommandActivityDock(
                                runner: state.runner,
                                expanded: $commandLogExpanded,
                                maxHeight: max(150, min(260, geometry.size.height * 0.34))
                            )
                        } else if state.runner.isRunning {
                            UserActivityBar(runner: state.runner)
                        }
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        }
        .foregroundStyle(PaperFlowTheme.ink)
        .preferredColorScheme(.dark)
        .frame(minWidth: 760, minHeight: 620)
        .onChange(of: state.runner.status) { status in
            if status == .running && state.showTechnicalDetails {
                commandLogExpanded = true
            }
            if status != .running {
                state.refreshStatus()
                AppServices.shared.menuBarController?.refresh()
            }
        }
        .sheet(item: $confirmation) { kind in
            confirmationSheet(kind)
        }
    }

    @ViewBuilder
    private var sectionView: some View {
        switch state.selectedSection {
        case .dashboard:
            DashboardView()
        case .dropShelfSettings:
            DropShelfSettingsView()
        case .zoteroOrganize:
            ZoteroOrganizeView(confirm: showConfirmation)
        case .localVault:
            LocalVaultView()
        case .localFolderImport:
            LocalFolderImportView(confirm: showConfirmation)
        case .existingAttachments:
            ExistingAttachmentsView(confirm: showConfirmation)
        case .cleanupWorkbench:
            CleanupWorkbenchView(confirm: showConfirmation)
        case .userGuide:
            UserGuideView()
        case .reports:
            ReportsView()
        case .settings:
            SettingsView()
        case .logs:
            LogsView()
        }
    }

    private func showConfirmation(_ kind: ConfirmationKind) {
        confirmationText = ""
        confirmation = kind
    }

    private func confirmationSheet(_ kind: ConfirmationKind) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(kind.title)
                .font(.title3)
                .fontWeight(.semibold)
            Text(kind.warning)
                .foregroundStyle(PaperFlowTheme.muted)
            if kind.requiresTypedConfirmation {
                Text("Type \(kind.requiredText) to continue.")
                    .font(.caption)
                TextField("Confirmation", text: $confirmationText)
                    .paperFlowTextInput()
            }
            HStack {
                Spacer()
                Button("Cancel") {
                    confirmation = nil
                }
                if kind.requiresTypedConfirmation {
                    Button(role: .destructive) {
                        runConfirmed(kind)
                        confirmation = nil
                    } label: {
                        Text("Delete")
                    }
                    .disabled(confirmationText != kind.requiredText)
                } else {
                    Button("Apply") {
                        runConfirmed(kind)
                        confirmation = nil
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
        }
        .padding()
        .frame(width: 520)
    }

    private func runConfirmed(_ kind: ConfirmationKind) {
        switch kind {
        case .applyIngest:
            state.runApplyIngest()
        case .applyMigration:
            state.runApplyMigration()
        case .cleanupDeleteEmpty:
            state.runCleanupDeleteEmpty()
        case .localizeAttachments:
            state.runApplyLocalizeAttachments()
        case .cleanupStoredAttachments:
            state.runCleanupStoredAttachments()
        case .applyLocalImport:
            state.runApplyLocalImport()
        case .applyAbstractRepairs:
            state.runApplyAbstractRepairs()
        case .applyMetadataRepairs:
            state.runApplyMetadataRepairs()
        case .applySelectedAbstractRepair(let itemKey):
            state.runApplyAbstractRepair(itemKey: itemKey)
        case .applySelectedMetadataRepair(let itemKey, let approvedFields):
            state.runApplyMetadataRepair(itemKey: itemKey, approvedFields: approvedFields)
        }
    }
}

private struct SidebarRailOrFullSidebar: View {
    @Binding var selectedSection: AppSection
    @Binding var isCollapsed: Bool
    let forceRail: Bool
    let showTechnicalDetails: Bool

    private var railOnly: Bool { isCollapsed || forceRail }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                isCollapsed.toggle()
            } label: {
                Image(systemName: railOnly ? "sidebar.right" : "sidebar.left")
                    .frame(width: 36, height: 30)
            }
            .buttonStyle(.plain)
            .help(railOnly ? "Expand sidebar" : "Collapse sidebar")
            .padding(.top, 12)
            .padding(.leading, 8)

            ScrollView {
                VStack(alignment: .leading, spacing: 3) {
                    ForEach(AppSection.visibleCases(showTechnicalDetails: showTechnicalDetails)) { section in
                        Button {
                            selectedSection = section
                        } label: {
                            HStack(spacing: 10) {
                                Image(systemName: section.symbolName)
                                    .frame(width: 24)
                                if !railOnly {
                                    Text(section.rawValue)
                                        .lineLimit(1)
                                        .minimumScaleFactor(0.82)
                                }
                            }
                            .frame(maxWidth: .infinity, minHeight: 32, alignment: .leading)
                            .padding(.horizontal, railOnly ? 8 : 9)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(selectedSection == section ? PaperFlowTheme.sky.opacity(0.18) : Color.clear)
                            )
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .help(section.rawValue)
                    }
                }
                .padding(.horizontal, railOnly ? 4 : 8)
            }
        }
        .frame(maxHeight: .infinity, alignment: .topLeading)
        .background(PaperFlowTheme.sidebar)
    }
}

struct HeaderView: View {
    @EnvironmentObject private var state: AppState
    let compact: Bool

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("PaperFlow")
                    .font(.title3)
                    .fontWeight(.semibold)
                Text(state.runner.isRunning ? "Working" : "Ready")
                    .font(.caption)
                    .foregroundStyle(PaperFlowTheme.muted)
            }
            Spacer()
            HStack(spacing: 6) {
                headerButton("Shelf", icon: "tray.and.arrow.down") { AppServices.shared.toggleShelf() }
                headerButton("Refresh", icon: "arrow.clockwise") { state.refreshStatus() }
                if state.showTechnicalDetails {
                    headerButton("Command", icon: "command") { AppServices.shared.showCommandWindow() }
                }
                if !compact && state.showTechnicalDetails {
                    headerButton("Project", icon: "folder") { state.openProjectFolder() }
                }
            }
        }
        .padding(.horizontal, 16)
        .frame(height: 58)
        .background(PaperFlowTheme.canvas0.opacity(0.92))
    }

    private func headerButton(_ title: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            if compact {
                Image(systemName: icon)
                    .frame(width: 26, height: 26)
            } else {
                Label(title, systemImage: icon)
            }
        }
        .buttonStyle(.borderless)
        .help(title)
    }
}

struct DropShelfSettingsView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: PaperFlowSpacing.md) {
            SectionTitle("Drop Shelf Settings")
            Text("PFW를 여는 방식, 표시 위치, 자동 동작을 설정합니다. 기본값은 단축키로만 표시이며 hot-zone은 선택 기능입니다.")
                .foregroundStyle(PaperFlowTheme.muted)

            SurfaceSection(title: "Activation", subtitle: "표시 방식과 화면 위치를 결정합니다.") {
                ResponsiveSettingRow("Activation mode", detail: "PFW가 나타나는 조건") {
                    Picker("Activation mode", selection: $state.dropShelfActivationMode) {
                        ForEach(DropShelfActivationMode.allCases) { mode in
                            Text(mode.label).tag(mode)
                        }
                    }
                    .labelsHidden()
                    .frame(maxWidth: .infinity)
                }
                ResponsiveSettingRow("Shortcut", detail: state.dropShelfShortcutPreset.detail) {
                    Picker("Drop shelf shortcut", selection: $state.dropShelfShortcutPreset) {
                        ForEach(DropShelfShortcutPreset.allCases) { preset in
                            Text(preset.label).tag(preset)
                        }
                    }
                    .labelsHidden()
                    .pickerStyle(.segmented)
                    .frame(maxWidth: .infinity)
                }
                ResponsiveSettingRow("Show on", detail: "PFW를 표시할 monitor") {
                    Picker("Show on", selection: $state.displayMode) {
                        ForEach(DisplayMode.allCases) { mode in
                            Text(mode.label).tag(mode)
                        }
                    }
                    .labelsHidden()
                    .frame(maxWidth: .infinity)
                }
                ResponsiveSettingRow("Placement", detail: "선택한 monitor 안의 기본 위치") {
                    Picker("Placement", selection: $state.dropShelfPlacement) {
                        ForEach(DropShelfPlacement.allCases) { placement in
                            Text(placement.label).tag(placement)
                        }
                    }
                    .labelsHidden()
                    .frame(maxWidth: .infinity)
                }
                ResponsiveSettingRow("Monitor strategy", detail: "Focused monitor를 판단하는 기준") {
                    Picker("Focused monitor strategy", selection: $state.focusedMonitorStrategy) {
                        ForEach(FocusedMonitorStrategy.allCases) { strategy in
                            Text(strategy.label).tag(strategy)
                        }
                    }
                    .labelsHidden()
                    .frame(maxWidth: .infinity)
                }
                SettingsToggleRow(
                    "Follow across Spaces",
                    detail: "Desktop을 전환해도 PFW를 현재 작업 옆에 유지",
                    isOn: $state.showPFWAcrossSpaces
                )
            }

            SurfaceSection(title: "Hot-zone", subtitle: "화면 가장자리의 작은 drag activation surface입니다. 기본값은 꺼짐입니다.") {
                SettingsToggleRow(
                    "Enable hot-zone",
                    detail: "Hot-Zone on Hover activation mode에서 사용",
                    isOn: $state.hotZoneEnabled
                )
                if state.hotZoneEnabled {
                    ResponsiveSettingRow("Edge") {
                        Picker("Hot-zone edge", selection: $state.hotZoneEdge) {
                            ForEach(HotZoneEdge.allCases) { edge in
                                Text(edge.rawValue.capitalized).tag(edge)
                            }
                        }
                        .labelsHidden()
                        .frame(maxWidth: .infinity)
                    }
                    ResponsiveSettingRow("Corner") {
                        Picker("Hot-zone corner", selection: $state.hotZoneCorner) {
                            ForEach(HotZoneCorner.allCases) { corner in
                                Text(corner.label).tag(corner)
                            }
                        }
                        .labelsHidden()
                        .frame(maxWidth: .infinity)
                    }
                    ResponsiveSettingRow("Width") {
                        Stepper(value: $state.hotZoneWidth, in: 6...80, step: 2) {
                            Text("\(Int(state.hotZoneWidth)) px")
                                .monospacedDigit()
                        }
                        .frame(maxWidth: .infinity)
                    }
                    ResponsiveSettingRow("Height") {
                        Stepper(value: $state.hotZoneHeight, in: 80...360, step: 10) {
                            Text("\(Int(state.hotZoneHeight)) px")
                                .monospacedDigit()
                        }
                        .frame(maxWidth: .infinity)
                    }
                    ResponsiveSettingRow("Idle opacity") {
                        HStack(spacing: PaperFlowSpacing.sm) {
                            Slider(value: $state.hotZoneIdleOpacity, in: 0.02...0.60)
                            Text(state.hotZoneIdleOpacity, format: .number.precision(.fractionLength(2)))
                                .font(.caption.monospacedDigit())
                                .frame(width: 40, alignment: .trailing)
                        }
                    }
                }
            }

            SurfaceSection(title: "Behavior", subtitle: "Drop 이후 PFW의 자동 동작을 설정합니다.") {
                SettingsToggleRow(
                    "Auto-hide after success",
                    detail: "성공 결과를 표시한 뒤 PFW를 자동으로 숨김",
                    isOn: $state.autoHideAfterSuccess
                )
                SettingsToggleRow(
                    "Auto preview after drop",
                    detail: "PDF drop 직후 자동으로 확인",
                    isOn: $state.autoDryRunAfterDrop
                )
                ResponsiveSettingRow("Auto-collapse delay", detail: "Drag가 벗어난 뒤 compact 상태로 돌아가는 시간") {
                    Stepper(value: $state.autoCollapseDelay, in: 1...20, step: 1) {
                        Text("\(Int(state.autoCollapseDelay)) seconds")
                            .monospacedDigit()
                    }
                    .frame(maxWidth: .infinity)
                }
            }

            SurfaceSection(title: "Preview", subtitle: "설정값을 변경하지 않고 PFW 표시 상태를 확인합니다.") {
                SettingsActionBar {
                    Button("Show Drop Shelf") { AppServices.shared.shelfController?.showExpanded() }
                    Button("Hide Drop Shelf") { AppServices.shared.shelfController?.hideShelf() }
                    if state.showTechnicalDetails {
                        Button("Rebuild Hot-Zones") { AppServices.shared.reconfigureHotZones() }
                    }
                }
            }
        }
    }
}

struct LogsView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionTitle("Logs")
            SurfaceSection(title: "Command history", subtitle: "Secrets are redacted before command output is displayed or written to disk.") {
                FlowLayout(spacing: 8) {
                    Button("Open App Logs") { state.openAppLogsFolder() }
                    Button("Open Current Log") { state.runner.openLogFile() }
                        .disabled(state.runner.currentLogFile == nil)
                }
                CommandLogView(runner: state.runner)
                    .frame(minHeight: 360)
            }
        }
    }
}

struct CommandLogView: View {
    @ObservedObject var runner: CommandRunner

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Command Output")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                Button { runner.copyOutput() } label: {
                    Label("Copy Log", systemImage: "doc.on.doc")
                }
                .disabled(runner.output.isEmpty)
                Button { runner.openLogFile() } label: {
                    Label("Open Log", systemImage: "terminal")
                }
                .disabled(runner.currentLogFile == nil)
                Button { runner.cancel() } label: {
                    Label("Stop", systemImage: "stop.fill")
                }
                .disabled(!runner.isRunning)
            }
            Text(runner.currentCommand.isEmpty ? "No command running." : runner.currentCommand)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(PaperFlowTheme.muted)
                .lineLimit(1)
                .truncationMode(.middle)
            ScrollViewReader { proxy in
                ScrollView {
                    Text(runner.output.isEmpty ? "No command output yet." : runner.output)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(runner.output.isEmpty ? .secondary : .primary)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                        .id("bottom")
                }
                .background(PaperFlowTheme.canvas0.opacity(0.86))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .onChange(of: runner.output) { _ in
                    proxy.scrollTo("bottom", anchor: .bottom)
                }
            }
        }
    }
}

struct SectionTitle: View {
    let title: String

    init(_ title: String) {
        self.title = title
    }

    var body: some View {
        Text(title)
            .font(.title)
            .fontWeight(.semibold)
            .foregroundStyle(PaperFlowTheme.ink)
            .fixedSize(horizontal: false, vertical: true)
    }
}

struct InfoTile: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption)
                .foregroundStyle(PaperFlowTheme.muted)
            Text(value)
                .font(.body)
                .lineLimit(3)
                .textSelection(.enabled)
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 82, alignment: .topLeading)
        .paperFlowCard(tint: PaperFlowTheme.sky, radius: 14)
    }
}

struct StatusLine: View {
    let label: String
    let value: String

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label)
                .fontWeight(.medium)
                .frame(width: 150, alignment: .leading)
            Text(value)
                .foregroundStyle(PaperFlowTheme.muted)
                .textSelection(.enabled)
                .lineLimit(2)
                .truncationMode(.middle)
            Spacer()
        }
    }
}

struct WorkflowButton: View {
    let title: String
    let icon: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Label(title, systemImage: icon)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .buttonStyle(.bordered)
    }
}

struct WorkflowStepCard: View {
    let number: Int
    let title: String
    let detail: String
    let icon: String
    let state: WorkflowStepState
    let actionTitle: String
    let action: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 9, style: .continuous)
                        .fill(stateColor.opacity(0.16))
                    Image(systemName: icon)
                        .foregroundStyle(stateColor)
                }
                .frame(width: 38, height: 38)

                VStack(alignment: .leading, spacing: 3) {
                    Text("STEP \(number)")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(PaperFlowTheme.faint)
                    Text(title)
                        .font(.headline)
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(PaperFlowTheme.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 4)
                WorkflowStateBadge(state: state)
            }

            if let stateDetail = state.detail {
                Label(stateDetail, systemImage: stateIcon)
                    .font(.caption)
                    .foregroundStyle(stateColor)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Button(actionTitle, action: action)
                .buttonStyle(.bordered)
                .disabled(!state.allowsExecution)
        }
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: 154, alignment: .topLeading)
        .background(PaperFlowTheme.panel1)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(state == .running ? stateColor.opacity(0.72) : PaperFlowTheme.line, lineWidth: 1)
        )
    }

    private var stateColor: Color {
        switch state {
        case .completed:
            return PaperFlowTheme.mint
        case .ready:
            return PaperFlowTheme.sky
        case .running:
            return PaperFlowTheme.lilac
        case .outdated:
            return PaperFlowTheme.amber
        case .blocked:
            return PaperFlowTheme.rose
        }
    }

    private var stateIcon: String {
        switch state {
        case .completed:
            return "checkmark.circle.fill"
        case .ready:
            return "play.circle"
        case .running:
            return "clock.arrow.circlepath"
        case .outdated:
            return "arrow.clockwise.circle"
        case .blocked:
            return "lock.fill"
        }
    }
}

struct WorkflowStateBadge: View {
    let state: WorkflowStepState

    var body: some View {
        Text(state.label)
            .font(.caption2.weight(.semibold))
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(color.opacity(0.14))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }

    private var color: Color {
        switch state {
        case .completed:
            return PaperFlowTheme.mint
        case .ready:
            return PaperFlowTheme.sky
        case .running:
            return PaperFlowTheme.lilac
        case .outdated:
            return PaperFlowTheme.amber
        case .blocked:
            return PaperFlowTheme.rose
        }
    }
}

struct SurfaceSection<Content: View>: View {
    let title: String
    let subtitle: String?
    let content: Content

    init(title: String, subtitle: String? = nil, @ViewBuilder content: () -> Content) {
        self.title = title
        self.subtitle = subtitle
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.headline)
                if let subtitle {
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(PaperFlowTheme.muted)
                }
            }
            content
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(PaperFlowTheme.panel0)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(PaperFlowTheme.line, lineWidth: 1)
        )
    }
}

private struct PersistentNotice: View {
    let message: String
    let dismiss: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(PaperFlowTheme.amber)
            Text(message)
                .font(.callout)
                .frame(maxWidth: .infinity, alignment: .leading)
            Button(action: dismiss) {
                Image(systemName: "xmark")
            }
            .buttonStyle(.plain)
        }
        .padding(10)
        .background(PaperFlowTheme.amber.opacity(0.10))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(PaperFlowTheme.amber.opacity(0.34), lineWidth: 1)
        )
    }
}

private struct CommandActivityDock: View {
    @ObservedObject var runner: CommandRunner
    @Binding var expanded: Bool
    let maxHeight: CGFloat

    var body: some View {
        VStack(spacing: 0) {
            Button {
                expanded.toggle()
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: runner.isRunning ? "circle.dotted.circle.fill" : "terminal")
                        .foregroundStyle(runner.isRunning ? PaperFlowTheme.lilac : PaperFlowTheme.muted)
                    Text(runner.isRunning ? "\(runner.currentStage.isEmpty ? "Command running" : runner.currentStage)" : runner.status.label)
                        .font(.callout.weight(.medium))
                    if runner.isRunning {
                        Text(runner.elapsedSeconds, format: .number.precision(.fractionLength(0)))
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(PaperFlowTheme.muted)
                    }
                    Spacer()
                    Text(runner.currentCommand)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(PaperFlowTheme.faint)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Image(systemName: expanded ? "chevron.down" : "chevron.up")
                        .foregroundStyle(PaperFlowTheme.muted)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 14)
            .frame(height: 42)

            if expanded {
                Rectangle()
                    .fill(PaperFlowTheme.line)
                    .frame(height: 1)
                CommandLogView(runner: runner)
                    .padding(10)
                    .frame(height: maxHeight)
            }
        }
        .background(PaperFlowTheme.sidebar)
    }
}

private struct UserActivityBar: View {
    @ObservedObject var runner: CommandRunner

    var body: some View {
        HStack(spacing: 10) {
            ProgressView()
                .controlSize(.small)
            Text("PaperFlow is working")
                .font(.callout.weight(.medium))
            Spacer()
            Button("Cancel") { runner.cancel() }
        }
        .padding(.horizontal, 14)
        .frame(height: 42)
        .background(PaperFlowTheme.sidebar)
    }
}

struct WarningBox: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.callout)
            .foregroundStyle(PaperFlowTheme.muted)
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .paperFlowCard(tint: PaperFlowTheme.amber, radius: 12)
    }
}
