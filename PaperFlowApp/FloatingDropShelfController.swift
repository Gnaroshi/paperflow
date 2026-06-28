import AppKit
import QuartzCore
import SwiftUI

@MainActor
final class FloatingDropShelfController: ObservableObject {
    @Published private(set) var isExpanded = false
    @Published private(set) var visibilityState: PFWVisibilityState = .hidden

    private let state: AppState
    private let monitorManager: MultiMonitorManager
    private var panel: DropShelfPanel?
    private var auxiliaryPanels: [DropShelfPanel] = []
    private var hotZoneWindows: [HotZoneWindow] = []
    private var collapseTask: DispatchWorkItem?
    private var placementTimer: Timer?

    init(state: AppState, monitorManager: MultiMonitorManager) {
        self.state = state
        self.monitorManager = monitorManager
    }

    func configureHotZones() {
        placementTimer?.invalidate()
        placementTimer = nil
        hotZoneWindows.forEach { $0.orderOut(nil) }
        hotZoneWindows.removeAll()
        guard state.hotZoneEnabled, state.dropShelfActivationMode == .hotZoneOnHover else {
            return
        }
        let screens = monitorManager.targetScreens(for: state)
        for screen in screens {
            let frame = ScreenPlacementPolicy.hotZoneFrame(
                on: screen,
                edge: state.hotZoneEdge,
                corner: state.hotZoneCorner,
                width: CGFloat(state.hotZoneWidth),
                height: CGFloat(state.hotZoneHeight)
            )
            let window = HotZoneWindow(
                frame: frame,
                screen: screen,
                opacity: state.hotZoneIdleOpacity,
                showAcrossSpaces: state.showPFWAcrossSpaces,
                dropController: self
            )
            window.orderFrontRegardless()
            hotZoneWindows.append(window)
        }
        if state.displayMode == .focusedMonitor || state.displayMode == .cursorMonitor {
            placementTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    self?.refreshHotZoneFrames()
                }
            }
        }
    }

    func showCompact(on screen: NSScreen? = nil) {
        isExpanded = false
        state.dropShelfPhase = state.droppedPDFs.isEmpty ? .idleCompact : .queued
        showPanel(expanded: false, on: screen)
    }

    func showExpanded(on screen: NSScreen? = nil) {
        cancelAutoCollapse()
        isExpanded = true
        if screen == nil, state.displayMode == .allMonitors {
            showOnAllScreens()
            return
        }
        showPanel(expanded: true, on: screen)
    }

    func toggleShelf() {
        switch visibilityState {
        case .hidden, .hiding:
            showExpandedFromShortcut()
        case .showing, .visible:
            hideShelf()
        }
    }

    func showExpandedFromShortcut() {
        state.shelfLastResult = state.droppedPDFs.isEmpty ? "Ready. Drop PDFs to preview." : "\(state.droppedPDFs.count) PDF file(s) queued"
        showExpanded()
    }

    func applyActivationMode() {
        configureHotZones()
        switch state.dropShelfActivationMode {
        case .alwaysShowCompact:
            showCompact()
        case .keyboardShortcutOnly, .hotZoneOnHover, .menuBarOnly:
            hideShelf()
        }
    }

    func hideShelf() {
        cancelAutoCollapse()
        guard visibilityState != .hidden, visibilityState != .hiding else {
            panel?.orderOut(nil)
            auxiliaryPanels.forEach { $0.orderOut(nil) }
            auxiliaryPanels.removeAll()
            return
        }
        visibilityState = .hiding
        let panels = ([panel].compactMap { $0 } + auxiliaryPanels).filter { $0.isVisible }
        guard !panels.isEmpty else {
            visibilityState = .hidden
            return
        }
        for window in panels {
            let screen = window.screen ?? NSScreen.main ?? monitorManager.cursorScreen()
            var hiddenFrame = window.frame
            hiddenFrame.origin.y = screen.visibleFrame.minY - hiddenFrame.height - 12
            NSAnimationContext.runAnimationGroup { context in
                context.duration = 0.18
                context.timingFunction = CAMediaTimingFunction(name: .easeIn)
                window.animator().setFrame(hiddenFrame, display: true)
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.22) { [weak self] in
            Task { @MainActor in
                guard self?.visibilityState == .hiding else {
                    return
                }
                panels.forEach { $0.orderOut(nil) }
                self?.auxiliaryPanels.removeAll()
                self?.visibilityState = .hidden
            }
        }
    }

    func compactLeftClick(clickCount: Int) {
        NSLog("PaperFlow DropShelf compact click received: clickCount=\(clickCount)")
        state.shelfLastResult = "Shelf click received."
        if clickCount >= 2 {
            AppServices.shared.openMainWindow()
        } else {
            showExpanded()
        }
    }

    func compactRightClick() {
        NSLog("PaperFlow DropShelf compact right click received")
        let menu = NSMenu()
        menu.addItem(withTitle: "Expand Shelf", action: #selector(DropShelfPanel.expandShelfFromMenu(_:)), keyEquivalent: "")
        menu.addItem(withTitle: "Open Main Window", action: #selector(DropShelfPanel.openMainWindowFromMenu(_:)), keyEquivalent: "")
        menu.addItem(withTitle: "Hide Shelf", action: #selector(DropShelfPanel.hideShelfFromMenu(_:)), keyEquivalent: "")
        menu.items.forEach { $0.target = panel }
        if let event = NSApp.currentEvent {
            NSMenu.popUpContextMenu(menu, with: event, for: panel?.contentView ?? NSView())
        }
    }

    func hotZoneHover(on screen: NSScreen? = nil) {
        guard state.dropShelfActivationMode == .hotZoneOnHover else {
            return
        }
        state.shelfLastResult = "Drop PDFs to preview."
        showExpanded(on: screen)
    }

    func dragHover(valid: Bool, on screen: NSScreen? = nil, fileCount: Int = 0) {
        cancelAutoCollapse()
        state.dropShelfPhase = valid ? .hoveringValidPDF : .hoveringInvalidFile
        let count = fileCount
        if valid {
            state.shelfLastResult = count > 0 ? "\(count) file(s). Release to preview PDFs." : "Release to preview PDFs."
        } else {
            state.shelfLastResult = "Only PDF files are accepted."
        }
        showExpanded(on: screen)
    }

    func dragExited() {
        if state.droppedPDFs.isEmpty {
            state.dropShelfPhase = .idleCompact
        } else {
            state.dropShelfPhase = .queued
        }
        scheduleDragExitCollapse()
    }

    func handleDropped(_ urls: [URL], on screen: NSScreen? = nil) {
        cancelAutoCollapse()
        state.addDroppedURLs(urls)
        state.dropShelfPhase = state.invalidDropWarnings.isEmpty ? .queued : .reviewNeeded
        state.shelfLastResult = "\(state.droppedPDFs.count) PDF file(s) queued"
        showExpanded(on: screen)
        if state.autoDryRunAfterDrop, !state.droppedPDFs.isEmpty {
            state.dropShelfAction = .dryRunIngest
            state.runDropShelfSelectedAction()
        }
    }

    func simulateValidHover() {
        dragHover(valid: true)
    }

    func simulateInvalidHover() {
        dragHover(valid: false)
        state.invalidDropWarnings = ["Ignored non-PDF: example.txt"]
    }

    func simulateProcessingSuccess() {
        state.dropShelfPhase = .success
        state.shelfLastResult = "Simulated successful paperflow run."
        showExpanded()
    }

    func simulateProcessingFailure() {
        state.dropShelfPhase = .failure
        state.shelfLastResult = "Simulated paperflow failure."
        showExpanded()
    }

    func showOnAllScreens() {
        auxiliaryPanels.forEach { $0.orderOut(nil) }
        auxiliaryPanels.removeAll()
        panel?.orderOut(nil)
        isExpanded = true
        visibilityState = .showing
        for screen in NSScreen.screens {
            let frame = ScreenPlacementPolicy.shelfFrame(
                on: screen,
                expanded: true,
                placement: state.dropShelfPlacement,
                phase: state.dropShelfPhase
            )
            let panel = DropShelfPanel(frame: frame)
            panel.dropController = self
            panel.updateCollectionBehavior(showAcrossSpaces: state.showPFWAcrossSpaces)
            panel.contentView = NSHostingView(
                rootView: DropShelfView(controller: self)
                    .environmentObject(state)
            )
            panel.orderFrontRegardless()
            auxiliaryPanels.append(panel)
        }
        visibilityState = .visible
    }

    func refreshWindowBehaviors() {
        panel?.updateCollectionBehavior(showAcrossSpaces: state.showPFWAcrossSpaces)
        auxiliaryPanels.forEach { $0.updateCollectionBehavior(showAcrossSpaces: state.showPFWAcrossSpaces) }
    }

    func commandStarted() {
        state.dropShelfPhase = .processing
        state.shelfLastResult = "Command started. Live output is shown below."
        showExpanded()
    }

    func commandFinished(success: Bool) {
        state.dropShelfPhase = success ? .success : .failure
        state.shelfLastResult = success ? successSummary() : failureSummary()
        if success, state.autoHideAfterSuccess {
            scheduleAutoCollapse()
        } else {
            showExpanded()
        }
    }

    private func showPanel(expanded: Bool, on screen: NSScreen? = nil) {
        auxiliaryPanels.forEach { $0.orderOut(nil) }
        auxiliaryPanels.removeAll()
        visibilityState = .showing
        let targetScreen = screen ?? monitorManager.targetScreens(for: state).first ?? monitorManager.focusedScreen(strategy: state.focusedMonitorStrategy)
        let frame = expanded
            ? ScreenPlacementPolicy.shelfFrame(
                on: targetScreen,
                expanded: true,
                placement: state.dropShelfPlacement,
                phase: state.dropShelfPhase
            )
            : ScreenPlacementPolicy.compactShelfFrame(on: targetScreen, placement: state.dropShelfPlacement)
        let panel = ensurePanel(frame: frame)
        panel.updateCollectionBehavior(showAcrossSpaces: state.showPFWAcrossSpaces)
        if panel.isVisible {
            panel.setFrame(frame, display: true, animate: true)
            visibilityState = .visible
        } else {
            let startFrame = expanded
                ? ScreenPlacementPolicy.shelfHiddenStartFrame(
                    on: targetScreen,
                    expanded: true,
                    placement: state.dropShelfPlacement,
                    phase: state.dropShelfPhase
                )
                : frame
            panel.setFrame(startFrame, display: false)
        }
        panel.orderFrontRegardless()
        if expanded {
            NSAnimationContext.runAnimationGroup { context in
                context.duration = 0.22
                context.timingFunction = CAMediaTimingFunction(name: .easeOut)
                panel.animator().setFrame(frame, display: true)
            } completionHandler: { [weak self] in
                Task { @MainActor in
                    self?.visibilityState = .visible
                }
            }
        } else {
            panel.setFrame(frame, display: true, animate: false)
            visibilityState = .visible
        }
    }

    private func refreshHotZoneFrames() {
        guard state.hotZoneEnabled, state.dropShelfActivationMode == .hotZoneOnHover, hotZoneWindows.count == 1 else {
            return
        }
        let screen = monitorManager.targetScreens(for: state).first
            ?? monitorManager.cursorScreen()
        let frame = ScreenPlacementPolicy.hotZoneFrame(
            on: screen,
            edge: state.hotZoneEdge,
            corner: state.hotZoneCorner,
            width: CGFloat(state.hotZoneWidth),
            height: CGFloat(state.hotZoneHeight)
        )
        hotZoneWindows.first?.updateFrame(frame, opacity: state.hotZoneIdleOpacity)
    }

    private func ensurePanel(frame: NSRect) -> DropShelfPanel {
        if let panel {
            return panel
        }
        let panel = DropShelfPanel(frame: frame)
        panel.dropController = self
        panel.contentView = NSHostingView(
            rootView: DropShelfView(controller: self)
                .environmentObject(state)
        )
        self.panel = panel
        return panel
    }

    private func scheduleAutoCollapse() {
        cancelAutoCollapse()
        let task = DispatchWorkItem { [weak self] in
            Task { @MainActor in
                self?.state.clearPDFs()
                if self?.state.dropShelfActivationMode == .alwaysShowCompact {
                    self?.showCompact()
                } else {
                    self?.hideShelf()
                }
            }
        }
        collapseTask = task
        DispatchQueue.main.asyncAfter(deadline: .now() + state.autoCollapseDelay, execute: task)
    }

    private func scheduleDragExitCollapse() {
        cancelAutoCollapse()
        let task = DispatchWorkItem { [weak self] in
            Task { @MainActor in
                guard let self, self.state.dropShelfPhase != .processing else {
                    return
                }
                if self.state.droppedPDFs.isEmpty {
                    if self.state.dropShelfActivationMode == .alwaysShowCompact {
                        self.showCompact()
                    } else {
                        self.hideShelf()
                    }
                }
            }
        }
        collapseTask = task
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5, execute: task)
    }

    private func cancelAutoCollapse() {
        collapseTask?.cancel()
        collapseTask = nil
    }

    private func successSummary() -> String {
        let output = state.runner.output
        if let planLine = output
            .split(separator: "\n")
            .first(where: { $0.localizedCaseInsensitiveContains("Wrote") || $0.localizedCaseInsensitiveContains("planned") }) {
            return String(planLine)
        }
        return "paperflow completed successfully."
    }

    private func failureSummary() -> String {
        let command = state.runner.currentCommand.isEmpty ? "paperflow command" : state.runner.currentCommand
        let tail = state.runner.output
            .split(separator: "\n")
            .suffix(4)
            .joined(separator: "\n")
        return tail.isEmpty ? "\(command) failed." : tail
    }
}
