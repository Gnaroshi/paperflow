import AppKit

enum ScreenPlacementPolicy {
    static let shelfMarginRight: CGFloat = 24
    static let shelfMarginBottom: CGFloat = 24
    static let compactShelfSize = NSSize(width: 150, height: 48)
    static let expandedShelfSize = NSSize(width: 520, height: 220)

    static func shelfFrame(on screen: NSScreen, expanded: Bool, placement: DropShelfPlacement = .bottomCenter) -> NSRect {
        let visible = screen.visibleFrame
        let size = expanded ? expandedShelfSize : compactShelfSize
        switch placement {
        case .bottomCenter:
            return NSRect(
                x: visible.midX - size.width / 2,
                y: visible.minY + shelfMarginBottom,
                width: size.width,
                height: size.height
            )
        case .bottomRight:
            return NSRect(
                x: visible.maxX - size.width - shelfMarginRight,
                y: visible.minY + shelfMarginBottom,
                width: size.width,
                height: size.height
            )
        case .rightEdge:
            return NSRect(
                x: visible.maxX - size.width - shelfMarginRight,
                y: visible.midY - size.height / 2,
                width: size.width,
                height: size.height
            )
        case .custom:
            return NSRect(
                x: visible.midX - size.width / 2,
                y: visible.minY + shelfMarginBottom,
                width: size.width,
                height: size.height
            )
        }
    }

    static func shelfHiddenStartFrame(on screen: NSScreen, expanded: Bool, placement: DropShelfPlacement = .bottomCenter) -> NSRect {
        var frame = shelfFrame(on: screen, expanded: expanded, placement: placement)
        frame.origin.y = screen.visibleFrame.minY - frame.height - 12
        return frame
    }

    static func compactShelfFrame(on screen: NSScreen, placement: DropShelfPlacement = .bottomCenter) -> NSRect {
        let visible = screen.visibleFrame
        let size = compactShelfSize
        switch placement {
        case .bottomCenter:
            return NSRect(
                x: visible.midX - size.width / 2,
                y: visible.minY + shelfMarginBottom,
                width: size.width,
                height: size.height
            )
        case .bottomRight, .rightEdge, .custom:
            return NSRect(
                x: visible.maxX - size.width - shelfMarginRight,
                y: visible.minY + shelfMarginBottom,
                width: size.width,
                height: size.height
            )
        }
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
        let size = NSSize(width: 680, height: 520)
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
