import AppKit

enum ScreenPlacementPolicy {
    /// Space membership and display placement are independent. The shelf stays
    /// anchored to its selected physical display while joining every Space on
    /// that display.
    static let showsAcrossSpacesByDefault = true

    static let shelfMarginRight: CGFloat = 24
    static let shelfMarginBottom: CGFloat = 24
    static let compactShelfSize = NSSize(width: 420, height: 96)
    static let dropReadyShelfSize = NSSize(width: 600, height: 400)
    static let processingShelfSize = NSSize(width: 640, height: 420)
    static let resultShelfSize = NSSize(width: 680, height: 520)
    static let expandedShelfSize = NSSize(width: 600, height: 400)

    static func showAcrossSpacesValue(currentValue: Bool, migrationApplied: Bool) -> Bool {
        migrationApplied ? currentValue : showsAcrossSpacesByDefault
    }

    static func shelfFrame(
        on screen: NSScreen,
        expanded: Bool,
        placement: DropShelfPlacement = .bottomRight,
        phase: DropShelfPhase = .idleCompact
    ) -> NSRect {
        let visible = screen.visibleFrame
        let size = cappedSize(baseSize(for: phase, expanded: expanded), visible: visible)
        return anchoredFrame(size: size, visible: visible, placement: placement)
    }

    static func shelfFrame(
        on screen: NSScreen,
        size: NSSize,
        placement: DropShelfPlacement = .bottomRight
    ) -> NSRect {
        let visible = screen.visibleFrame
        return anchoredFrame(size: cappedSize(size, visible: visible), visible: visible, placement: placement)
    }

    static func shelfHiddenStartFrame(
        on screen: NSScreen,
        expanded: Bool,
        placement: DropShelfPlacement = .bottomRight,
        phase: DropShelfPhase = .idleCompact
    ) -> NSRect {
        var frame = shelfFrame(on: screen, expanded: expanded, placement: placement, phase: phase)
        frame.origin.y = screen.visibleFrame.minY - frame.height - 12
        return frame
    }

    static func compactShelfFrame(on screen: NSScreen, placement: DropShelfPlacement = .bottomRight) -> NSRect {
        shelfFrame(on: screen, size: compactShelfSize, placement: placement)
    }

    private static func baseSize(for phase: DropShelfPhase, expanded: Bool) -> NSSize {
        guard expanded else {
            return compactShelfSize
        }
        switch phase {
        case .idleCompact:
            return dropReadyShelfSize
        case .hoveringValidPDF, .hoveringInvalidFile, .queued, .reviewNeeded:
            return dropReadyShelfSize
        case .processing:
            return processingShelfSize
        case .success, .failure:
            return resultShelfSize
        }
    }

    private static func cappedSize(_ size: NSSize, visible: NSRect) -> NSSize {
        NSSize(
            width: min(760, max(320, min(size.width, visible.width - 48))),
            height: min(620, max(96, min(size.height, visible.height - 48)))
        )
    }

    private static func anchoredFrame(size: NSSize, visible: NSRect, placement: DropShelfPlacement) -> NSRect {
        let rawX: CGFloat
        let rawY: CGFloat
        switch placement {
        case .bottomCenter:
            rawX = visible.midX - size.width / 2
            rawY = visible.minY + shelfMarginBottom
        case .bottomRight:
            rawX = visible.maxX - size.width - shelfMarginRight
            rawY = visible.minY + shelfMarginBottom
        case .rightEdge:
            rawX = visible.maxX - size.width - shelfMarginRight
            rawY = visible.midY - size.height / 2
        case .custom:
            rawX = visible.maxX - size.width - shelfMarginRight
            rawY = visible.minY + shelfMarginBottom
        }
        let clampedX = min(max(rawX, visible.minX + 24), visible.maxX - size.width - 24)
        let clampedY = min(max(rawY, visible.minY + shelfMarginBottom), visible.maxY - size.height - 24)
        return NSRect(x: clampedX, y: clampedY, width: size.width, height: size.height)
    }

    static func oldShelfFrame(on screen: NSScreen, expanded: Bool) -> NSRect {
        let visible = screen.visibleFrame
        let size = expanded ? expandedShelfSize : compactShelfSize
        return NSRect(
            x: visible.maxX - size.width - shelfMarginRight,
            y: visible.minY + shelfMarginBottom,
            width: size.width,
            height: size.height
        )
    }

    static func commandPopupFrame(on screen: NSScreen) -> NSRect {
        let visible = screen.visibleFrame
        let size = NSSize(
            width: min(680, max(420, visible.width - 48)),
            height: min(520, max(360, visible.height - 48))
        )
        return NSRect(
            x: visible.midX - size.width / 2,
            y: visible.midY - size.height / 2,
            width: size.width,
            height: size.height
        )
    }

    static func hotZoneFrame(
        on screen: NSScreen,
        edge: HotZoneEdge,
        corner: HotZoneCorner,
        width: CGFloat,
        height: CGFloat
    ) -> NSRect {
        let visible = screen.visibleFrame
        switch edge {
        case .right:
            let y = corner == .topRight ? visible.maxY - height - 96 : visible.minY + 96
            return NSRect(x: visible.maxX - width, y: y, width: width, height: height)
        case .left:
            let y = corner == .topLeft ? visible.maxY - height - 96 : visible.minY + 96
            return NSRect(x: visible.minX, y: y, width: width, height: height)
        case .bottom:
            let x = corner == .bottomLeft ? visible.minX + 96 : visible.maxX - height - 96
            return NSRect(x: x, y: visible.minY, width: height, height: width)
        case .top:
            let x = corner == .topLeft ? visible.minX + 96 : visible.maxX - height - 96
            return NSRect(x: x, y: visible.maxY - width, width: height, height: width)
        }
    }
}
