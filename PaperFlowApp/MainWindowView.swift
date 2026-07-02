import SwiftUI

struct MainWindowView: View {
    @EnvironmentObject private var state: AppState
    @State private var confirmation: ConfirmationKind?
    @State private var confirmationText = ""
    @State private var sidebarCollapsed = false

    var body: some View {
        GeometryReader { geometry in
            let sidebarWidth = sidebarCollapsed ? 56 : min(260, max(228, geometry.size.width * 0.22))
            HStack(spacing: 0) {
                SidebarRailOrFullSidebar(
                    selectedSection: $state.selectedSection,
                    isCollapsed: $sidebarCollapsed
                )
                .frame(width: sidebarWidth)
                .animation(.easeInOut(duration: 0.16), value: sidebarCollapsed)

                Divider()

                VStack(spacing: 0) {
                    HeaderView()
                    Divider()
                    ScrollView {
                        sectionView
                            .padding(.horizontal, geometry.size.width < 1180 ? 12 : 16)
                            .padding(.vertical, 14)
                            .frame(maxWidth: .infinity, alignment: .topLeading)
                    }
                    Divider()
                    CommandLogView(runner: state.runner)
                        .padding(10)
                        .frame(minHeight: 128, idealHeight: 164, maxHeight: geometry.size.height < 820 ? 190 : 260)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .frame(minWidth: 980, minHeight: 700)
        .onAppear {
            state.refreshStatus()
        }
        .onChange(of: state.runner.status) { status in
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
                .foregroundStyle(.secondary)
            Text("Type \(kind.requiredText) to continue.")
                .font(.caption)
            TextField("Confirmation", text: $confirmationText)
                .textFieldStyle(.roundedBorder)
            HStack {
                Spacer()
                Button("Cancel") {
                    confirmation = nil
                }
                Button(role: .destructive) {
                    runConfirmed(kind)
                    confirmation = nil
                } label: {
                    Text("Run")
                }
                .disabled(confirmationText != kind.requiredText)
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

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                isCollapsed.toggle()
            } label: {
                Image(systemName: isCollapsed ? "sidebar.left" : "sidebar.left")
                    .frame(width: 36, height: 30)
            }
            .buttonStyle(.plain)
            .help(isCollapsed ? "Expand sidebar" : "Collapse sidebar")
            .padding(.top, 12)
            .padding(.leading, 8)

            ScrollView {
                VStack(alignment: .leading, spacing: 3) {
                    ForEach(AppSection.allCases) { section in
                        Button {
                            selectedSection = section
                        } label: {
                            HStack(spacing: 10) {
                                Image(systemName: section.symbolName)
                                    .frame(width: 24)
                                if !isCollapsed {
                                    Text(section.rawValue)
                                        .lineLimit(1)
                                        .minimumScaleFactor(0.82)
                                }
                            }
                            .frame(maxWidth: .infinity, minHeight: 32, alignment: .leading)
                            .padding(.horizontal, isCollapsed ? 8 : 9)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(selectedSection == section ? Color.accentColor.opacity(0.14) : Color.clear)
                            )
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .help(section.rawValue)
                    }
                }
                .padding(.horizontal, isCollapsed ? 4 : 8)
            }
        }
        .frame(maxHeight: .infinity, alignment: .topLeading)
        .background(
            LinearGradient(
                colors: [
                    Color(red: 0.96, green: 0.97, blue: 1.0),
                    Color(red: 0.98, green: 0.95, blue: 0.98)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
        )
    }
}

struct HeaderView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("PaperFlow")
                    .font(.title3)
                    .fontWeight(.semibold)
                Text("Status: \(state.statusText) • queued: \(state.runner.queuedCount)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button { AppServices.shared.shelfController?.toggleShelf() } label: {
                Label("Shelf", systemImage: "tray.and.arrow.down")
            }
            Button { AppServices.shared.commandPopupWindow?.show() } label: {
                Label("Command", systemImage: "command")
            }
            Button { state.refreshStatus() } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            Button { state.openProjectFolder() } label: {
                Label("Project", systemImage: "folder")
            }
            Button { state.openReportsFolder() } label: {
                Label("Reports", systemImage: "doc.text")
            }
        }
        .padding(14)
    }
}

struct DropShelfSettingsView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionTitle("Drop Shelf Settings")
            Text("The shelf is hidden by default and appears with ⌃⇧⌘+. Hot-zones are optional because macOS does not deliver global drag events until the cursor enters one of PaperFlow's windows.")
                .foregroundStyle(.secondary)

            Toggle("Enable hot-zone", isOn: $state.hotZoneEnabled)
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
            Toggle("Show PFW across Spaces", isOn: $state.showPFWAcrossSpaces)
            Picker("Focused monitor strategy", selection: $state.focusedMonitorStrategy) {
                ForEach(FocusedMonitorStrategy.allCases) { strategy in
                    Text(strategy.label).tag(strategy)
                }
            }
            Picker("Hot-zone edge", selection: $state.hotZoneEdge) {
                ForEach(HotZoneEdge.allCases) { edge in
                    Text(edge.rawValue).tag(edge)
                }
            }
            Picker("Hot-zone corner", selection: $state.hotZoneCorner) {
                ForEach(HotZoneCorner.allCases) { corner in
                    Text(corner.label).tag(corner)
                }
            }
            HStack {
                Stepper("Width: \(Int(state.hotZoneWidth)) px", value: $state.hotZoneWidth, in: 6...80, step: 2)
                Stepper("Height: \(Int(state.hotZoneHeight)) px", value: $state.hotZoneHeight, in: 80...360, step: 10)
            }
            Slider(value: $state.hotZoneIdleOpacity, in: 0.02...0.60) {
                Text("Idle opacity")
            }
            Text("Idle opacity: \(state.hotZoneIdleOpacity, specifier: "%.2f")")
                .font(.caption)
                .foregroundStyle(.secondary)
            Toggle("Auto-hide after successful dry-run/apply", isOn: $state.autoHideAfterSuccess)
            Toggle("Auto dry-run after drop", isOn: $state.autoDryRunAfterDrop)
            Stepper("Auto-collapse delay: \(Int(state.autoCollapseDelay)) seconds", value: $state.autoCollapseDelay, in: 1...20, step: 1)

            HStack {
                Button("Show Drop Shelf") { AppServices.shared.shelfController?.showExpanded() }
                Button("Hide Drop Shelf") { AppServices.shared.shelfController?.hideShelf() }
                Button("Rebuild Hot-Zones") { AppServices.shared.reconfigureHotZones() }
            }
        }
    }
}

struct LogsView: View {
    @EnvironmentObject private var state: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            SectionTitle("Logs")
            Button("Open App Logs") { state.openAppLogsFolder() }
            CommandLogView(runner: state.runner)
                .frame(minHeight: 420)
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
                .foregroundStyle(.secondary)
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
                .background(Color(nsColor: .textBackgroundColor))
                .clipShape(RoundedRectangle(cornerRadius: 6))
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color(nsColor: .separatorColor)))
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
            .fontWeight(.bold)
            .foregroundStyle(
                LinearGradient(
                    colors: [Color(red: 0.22, green: 0.24, blue: 0.58), Color(red: 0.54, green: 0.34, blue: 0.72)],
                    startPoint: .leading,
                    endPoint: .trailing
                )
            )
    }
}

struct InfoTile: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.body)
                .lineLimit(3)
                .textSelection(.enabled)
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 82, alignment: .topLeading)
        .background(
            LinearGradient(
                colors: [
                    Color(red: 0.96, green: 0.97, blue: 1.0),
                    Color(red: 1.0, green: 0.96, blue: 0.98)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .shadow(color: Color.black.opacity(0.035), radius: 8, x: 0, y: 4)
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
                .foregroundStyle(.secondary)
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

struct WarningBox: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.callout)
            .foregroundStyle(.secondary)
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(red: 1.0, green: 0.95, blue: 0.78).opacity(0.55))
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}
