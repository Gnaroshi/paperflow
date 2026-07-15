import AppKit
import SwiftUI

@MainActor
final class AppServices {
    static let shared = AppServices()

    private static let followsSpacesDefaultMigrationKey = "pfwFollowsSpacesDefaultV1"

    let state = AppState()
    let monitorManager = MultiMonitorManager()

    var menuBarController: MenuBarController?
    var shelfController: FloatingDropShelfController?
    var commandPopupWindow: CommandPopupWindow?
    var hotkeyManager: GlobalHotkeyManager?

    private var mainWindowController: NSWindowController?

    private init() {}

    func start() {
        migrateFollowsSpacesDefaultIfNeeded()

        if menuBarController == nil {
            menuBarController = MenuBarController(state: state)
        }
        if shelfController == nil {
            let shelf = FloatingDropShelfController(state: state, monitorManager: monitorManager)
            shelfController = shelf
            shelf.applyActivationMode()
        }
        if commandPopupWindow == nil {
            commandPopupWindow = CommandPopupWindow(state: state, monitorManager: monitorManager)
        }

        if hotkeyManager == nil {
            let hotkeys = GlobalHotkeyManager()
            hotkeys.register(state: state)
            hotkeyManager = hotkeys
        }
    }

    private func migrateFollowsSpacesDefaultIfNeeded() {
        let defaults = UserDefaults.standard
        let migrationApplied = defaults.bool(forKey: Self.followsSpacesDefaultMigrationKey)
        let migratedValue = ScreenPlacementPolicy.showAcrossSpacesValue(
            currentValue: state.showPFWAcrossSpaces,
            migrationApplied: migrationApplied
        )

        if state.showPFWAcrossSpaces != migratedValue {
            state.showPFWAcrossSpaces = migratedValue
        }
        if !migrationApplied {
            defaults.set(true, forKey: Self.followsSpacesDefaultMigrationKey)
        }
    }

    func toggleShelf() {
        start()
        shelfController?.toggleShelf()
    }

    func showCommandWindow() {
        start()
        commandPopupWindow?.show()
    }

    func reconfigureHotZones() {
        shelfController?.configureHotZones()
    }

    func openMainWindow(section: AppSection? = nil) {
        if let section {
            state.selectedSection = section
        }
        if let existingWindow = NSApp.windows.first(where: { window in
            window.title == "PaperFlow" && !(window is DropShelfPanel) && !(window is CommandPopupPanel)
        }) {
            existingWindow.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        if mainWindowController == nil {
            let window = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 1120, height: 820),
                styleMask: [.titled, .closable, .miniaturizable, .resizable],
                backing: .buffered,
                defer: false
            )
            window.title = "PaperFlow"
            window.minSize = NSSize(width: 760, height: 620)
            window.setFrameAutosaveName("PaperFlow Main Window")
            window.center()
            window.contentView = NSHostingView(
                rootView: MainWindowView()
                    .environmentObject(state)
            )
            mainWindowController = NSWindowController(window: window)
        }
        mainWindowController?.showWindow(nil)
        mainWindowController?.window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        Task { @MainActor in
            AppServices.shared.start()
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
            Task { @MainActor in
                AppServices.shared.openMainWindow()
            }
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        Task { @MainActor in
            AppServices.shared.openMainWindow()
        }
        return false
    }
}

@main
struct PaperFlowApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup("PaperFlow") {
            MainWindowView()
                .environmentObject(AppServices.shared.state)
                .frame(minWidth: 760, minHeight: 620)
                .onAppear {
                    Task { @MainActor in
                        AppServices.shared.start()
                    }
                }
        }
        .defaultSize(width: 1180, height: 820)

        Settings {
            SettingsView()
                .environmentObject(AppServices.shared.state)
                .frame(width: 620)
                .padding()
        }
    }
}
