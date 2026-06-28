import AppKit

final class HotZoneWindow: NSWindow {
    private let dropController: FloatingDropShelfController
    private let owningScreen: NSScreen

    init(
        frame: NSRect,
        screen: NSScreen,
        opacity: Double,
        dropController: FloatingDropShelfController
    ) {
        self.dropController = dropController
        self.owningScreen = screen
        super.init(
            contentRect: frame,
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        level = .floating
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        ignoresMouseEvents = false
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        contentView = HotZoneContentView(
            opacity: opacity,
            screen: screen,
            dropController: dropController
        )
    }

    override var canBecomeKey: Bool {
        false
    }

    func updateFrame(_ frame: NSRect, opacity: Double) {
        setFrame(frame, display: true)
        (contentView as? HotZoneContentView)?.idleOpacity = opacity
    }
}

private final class HotZoneContentView: NSView {
    var idleOpacity: Double {
        didSet { needsDisplay = true }
    }

    private let screen: NSScreen
    private weak var dropController: FloatingDropShelfController?
    private var trackingArea: NSTrackingArea?
    private var highlighted = false {
        didSet { needsDisplay = true }
    }

    init(
        opacity: Double,
        screen: NSScreen,
        dropController: FloatingDropShelfController
    ) {
        self.idleOpacity = opacity
        self.screen = screen
        self.dropController = dropController
        super.init(frame: .zero)
        registerForDraggedTypes([.fileURL])
    }

    required init?(coder: NSCoder) {
        nil
    }

    override func draw(_ dirtyRect: NSRect) {
        let alpha = highlighted ? 0.55 : idleOpacity
        NSColor.controlAccentColor.withAlphaComponent(alpha).setFill()
        bounds.fill()
    }

    override func updateTrackingAreas() {
        if let trackingArea {
            removeTrackingArea(trackingArea)
        }
        let area = NSTrackingArea(
            rect: bounds,
            options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
            owner: self,
            userInfo: nil
        )
        addTrackingArea(area)
        trackingArea = area
        super.updateTrackingAreas()
    }

    override func mouseEntered(with event: NSEvent) {
        highlighted = true
    }

    override func mouseExited(with event: NSEvent) {
        highlighted = false
    }

    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        highlighted = true
        let urls = Self.urls(from: sender)
        let valid = !urls.isEmpty && urls.allSatisfy { $0.pathExtension.lowercased() == "pdf" }
        dropController?.dragHover(valid: valid, on: screen)
        return valid ? .copy : []
    }

    override func draggingExited(_ sender: NSDraggingInfo?) {
        highlighted = false
        dropController?.dragExited()
    }

    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        highlighted = false
        dropController?.handleDropped(Self.urls(from: sender), on: screen)
        return true
    }

    private static func urls(from draggingInfo: NSDraggingInfo) -> [URL] {
        let pasteboard = draggingInfo.draggingPasteboard
        guard let items = pasteboard.pasteboardItems else {
            return []
        }
        return items.compactMap { item in
            guard let string = item.string(forType: .fileURL) else {
                return nil
            }
            return URL(string: string)
        }
    }
}
