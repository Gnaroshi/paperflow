import AppKit

@MainActor
final class MenuBarController: NSObject {
    private let state: AppState
    private let statusItem: NSStatusItem

    init(state: AppState) {
        self.state = state
        self.statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        super.init()
        configure()
    }

    func refresh() {
        configure()
    }

    private func configure() {
        if let button = statusItem.button {
            button.image = NSImage(systemSymbolName: "doc.text.magnifyingglass", accessibilityDescription: "PaperFlow")
            button.toolTip = "PaperFlow - \(state.statusText)"
        }
        let menu = NSMenu()
        menu.addItem(item("Toggle Drop Shelf", #selector(showDropShelf)))
        menu.addItem(item("Show Command Window", #selector(showCommandWindow)))
        menu.addItem(item("Open Main Window", #selector(openMainWindow)))
        menu.addItem(item("Open Cleanup Workbench", #selector(openCleanupWorkbench)))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(item("Open Vault", #selector(openVault)))
        menu.addItem(item("Open Reports", #selector(openReports)))
        menu.addItem(item("Settings", #selector(openSettings)))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(debugMenu())
        menu.addItem(NSMenuItem.separator())
        menu.addItem(item("Quit", #selector(quit)))
        statusItem.menu = menu
    }

    private func item(_ title: String, _ action: Selector) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
        item.target = self
        return item
    }

    private func debugMenu() -> NSMenuItem {
        let parent = NSMenuItem(title: "Debug", action: nil, keyEquivalent: "")
        let menu = NSMenu()
        menu.addItem(item("Show Shelf on All Screens", #selector(debugShowShelfAllScreens)))
        menu.addItem(item("Simulate Valid PDF Hover", #selector(debugValidHover)))
        menu.addItem(item("Simulate Invalid File Hover", #selector(debugInvalidHover)))
        menu.addItem(item("Simulate Processing Success", #selector(debugSuccess)))
        menu.addItem(item("Simulate Processing Failure", #selector(debugFailure)))
        menu.addItem(item("Print Screen Frames", #selector(debugPrintScreens)))
        menu.addItem(item("Print Visible Frames", #selector(debugPrintScreens)))
        menu.addItem(item("Print Current Cursor Screen", #selector(debugPrintCursorScreen)))
        menu.addItem(item("Print Keyboard Main Screen", #selector(debugPrintKeyboardMainScreen)))
        parent.submenu = menu
        return parent
    }

    @objc private func showDropShelf() {
        AppServices.shared.shelfController?.toggleShelf()
    }

    @objc private func showCommandWindow() {
        AppServices.shared.commandPopupWindow?.show()
    }

    @objc private func openMainWindow() {
        AppServices.shared.openMainWindow()
    }

    @objc private func openCleanupWorkbench() {
        AppServices.shared.openMainWindow(section: .cleanupWorkbench)
    }

    @objc private func openSettings() {
        AppServices.shared.openMainWindow(section: .settings)
    }

    @objc private func openVault() {
        state.openVault()
    }

    @objc private func openReports() {
        state.openReportsFolder()
    }

    @objc private func quit() {
        NSApplication.shared.terminate(nil)
    }

    @objc private func debugShowShelfAllScreens() {
        AppServices.shared.shelfController?.showOnAllScreens()
    }

    @objc private func debugValidHover() {
        AppServices.shared.shelfController?.simulateValidHover()
    }

    @objc private func debugInvalidHover() {
        AppServices.shared.shelfController?.simulateInvalidHover()
    }

    @objc private func debugSuccess() {
        AppServices.shared.shelfController?.simulateProcessingSuccess()
    }

    @objc private func debugFailure() {
        AppServices.shared.shelfController?.simulateProcessingFailure()
    }

    @objc private func debugPrintScreens() {
        let text = AppServices.shared.monitorManager.screenDescription()
        print(text)
        state.invalidDropWarnings = [text]
    }

    @objc private func debugPrintCursorScreen() {
        let screen = AppServices.shared.monitorManager.cursorScreen()
        let text = "Cursor screen: frame=\(screen.frame), visible=\(screen.visibleFrame)"
        print(text)
        state.invalidDropWarnings = [text]
    }

    @objc private func debugPrintKeyboardMainScreen() {
        let screen = NSScreen.main ?? AppServices.shared.monitorManager.cursorScreen()
        let text = "Keyboard main screen: frame=\(screen.frame), visible=\(screen.visibleFrame)"
        print(text)
        state.invalidDropWarnings = [text]
    }
}
