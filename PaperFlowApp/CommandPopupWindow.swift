import AppKit
import SwiftUI

@MainActor
final class CommandPopupWindow {
    private let state: AppState
    private let monitorManager: MultiMonitorManager
    private var panel: CommandPopupPanel?

    init(state: AppState, monitorManager: MultiMonitorManager) {
        self.state = state
        self.monitorManager = monitorManager
    }

    func show() {
        let screen = monitorManager.focusedScreen(strategy: state.focusedMonitorStrategy)
        let frame = ScreenPlacementPolicy.commandPopupFrame(on: screen)
        let panel = ensurePanel(frame: frame)
        panel.setFrame(frame, display: true)
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func hide() {
        panel?.orderOut(nil)
    }

    func toggle() {
        if panel?.isVisible == true {
            hide()
        } else {
            show()
        }
    }

    private func ensurePanel(frame: NSRect) -> CommandPopupPanel {
        if let panel {
            return panel
        }
        let panel = CommandPopupPanel(frame: frame)
        panel.onEscape = { [weak self] in
            self?.hide()
        }
        panel.contentView = NSHostingView(
            rootView: CommandPaletteView(onClose: { [weak self] in self?.hide() })
                .environmentObject(state)
        )
        self.panel = panel
        return panel
    }
}

final class CommandPopupPanel: NSPanel {
    var onEscape: (() -> Void)?

    init(frame: NSRect) {
        super.init(
            contentRect: frame,
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        level = .floating
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        isReleasedWhenClosed = false
        backgroundColor = .clear
        isOpaque = false
        hasShadow = false
        isMovableByWindowBackground = true
    }

    override var canBecomeKey: Bool {
        true
    }

    override func cancelOperation(_ sender: Any?) {
        onEscape?()
    }
}
