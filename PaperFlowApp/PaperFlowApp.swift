import AppKit
import SwiftUI

@MainActor
final class AppServices {
    static let shared = AppServices()

    let state = AppState()
    let monitorManager = MultiMonitorManager()

    var menuBarController: MenuBarController?
    var shelfController: FloatingDropShelfController?
    var commandPopupWindow: CommandPopupWindow?
    var hotkeyManager: GlobalHotkeyManager?

    private var mainWindowController: NSWindowController?

    private init() {}

    func start() {
        guard menuBarController == nil else {
            return
        }
        menuBarController = MenuBarController(state: state)
        let shelf = FloatingDropShelfController(state: state, monitorManager: monitorManager)
        shelfController = shelf
        commandPopupWindow = CommandPopupWindow(state: state, monitorManager: monitorManager)

        let hotkeys = GlobalHotkeyManager()
        hotkeys.register(state: state)
        hotkeyManager = hotkeys

        shelf.configureHotZones()
        shelf.showCompact()
    }

    func reconfigureHotZones() {
        shelfController?.configureHotZones()
    }

    func openMainWindow(section: AppSection? = nil) {
        if let section {
            state.selectedSection = section
        }
        if mainWindowController == nil {
            let window = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 1120, height: 820),
                styleMask: [.titled, .closable, .miniaturizable, .resizable],
                backing: .buffered,
                defer: false
            )
            window.title = "PaperFlow"
            window.center()
            window.contentView = NSHostingView(
                rootView: MainWindowView()
                    .environmentObject(state)
            )
            mainWindowController = NSWindowController(window: window)
        }
        mainWindowController?.showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        Task { @MainActor in
            AppServices.shared.start()
        }
    }
}

@main
struct PaperFlowApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        Settings {
            SettingsView()
                .environmentObject(AppServices.shared.state)
                .frame(width: 620)
                .padding()
        }
    }
}
