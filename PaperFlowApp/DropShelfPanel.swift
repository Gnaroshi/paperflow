import AppKit

final class DropShelfPanel: NSPanel {
    weak var dropController: FloatingDropShelfController?

    init(frame: NSRect) {
        super.init(
            contentRect: frame,
            styleMask: [.titled, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        level = .floating
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        hidesOnDeactivate = false
        isReleasedWhenClosed = false
        isMovableByWindowBackground = true
        titleVisibility = .hidden
        titlebarAppearsTransparent = true
        backgroundColor = .clear
        isOpaque = false
        hasShadow = true
        standardWindowButton(.closeButton)?.isHidden = true
        standardWindowButton(.miniaturizeButton)?.isHidden = true
        standardWindowButton(.zoomButton)?.isHidden = true
        ignoresMouseEvents = false
    }

    override var canBecomeKey: Bool {
        true
    }

    override var canBecomeMain: Bool {
        false
    }

    override func mouseDown(with event: NSEvent) {
        if dropController?.isExpanded == false || event.clickCount >= 2 {
            dropController?.compactLeftClick(clickCount: event.clickCount)
            return
        }
        super.mouseDown(with: event)
    }

    override func rightMouseDown(with event: NSEvent) {
        dropController?.compactRightClick()
    }

    @objc func expandShelfFromMenu(_ sender: Any?) {
        dropController?.showExpanded()
    }

    @objc func openMainWindowFromMenu(_ sender: Any?) {
        AppServices.shared.openMainWindow()
    }

    @objc func hideShelfFromMenu(_ sender: Any?) {
        dropController?.hideShelf()
    }
}
