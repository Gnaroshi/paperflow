import AppKit
import SwiftUI

@MainActor
final class FloatingDropShelfController: ObservableObject {
    @Published private(set) var isExpanded = false

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
        guard state.hotZoneEnabled else {
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
        isExpanded = true
        showPanel(expanded: true, on: screen)
    }

    func toggleShelf() {
        if panel?.isVisible == true {
            hideShelf()
        } else {
            showExpanded()
        }
    }

    func hideShelf() {
        guard state.dropShelfPhase != .processing else {
            return
        }
        panel?.orderOut(nil)
        auxiliaryPanels.forEach { $0.orderOut(nil) }
        auxiliaryPanels.removeAll()
    }

    func dragHover(valid: Bool, on screen: NSScreen? = nil) {
        cancelAutoCollapse()
        state.dropShelfPhase = valid ? .hoveringValidPDF : .hoveringInvalidFile
        showExpanded(on: screen)
    }

    func dragExited() {
        if state.droppedPDFs.isEmpty {
            state.dropShelfPhase = .idleCompact
        } else {
            state.dropShelfPhase = .queued
        }
    }

    func handleDropped(_ urls: [URL], on screen: NSScreen? = nil) {
        cancelAutoCollapse()
        state.addDroppedURLs(urls)
        state.dropShelfPhase = state.invalidDropWarnings.isEmpty ? .queued : .reviewNeeded
        state.shelfLastResult = "\(state.droppedPDFs.count) PDF file(s) queued"
        showExpanded(on: screen)
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
        scheduleAutoCollapse()
    }

    func simulateProcessingFailure() {
        state.dropShelfPhase = .failure
        state.shelfLastResult = "Simulated paperflow failure."
        showExpanded()
    }

    func showOnAllScreens() {
        auxiliaryPanels.forEach { $0.orderOut(nil) }
        auxiliaryPanels.removeAll()
        isExpanded = true
        for screen in NSScreen.screens {
            let frame = ScreenPlacementPolicy.shelfFrame(on: screen, expanded: true)
            let panel = DropShelfPanel(frame: frame)
            panel.contentView = NSHostingView(
                rootView: DropShelfView(controller: self)
                    .environmentObject(state)
            )
            panel.orderFrontRegardless()
            auxiliaryPanels.append(panel)
        }
    }

    func commandStarted() {
        state.dropShelfPhase = .processing
        state.shelfLastResult = "paperflow is running..."
        showExpanded()
    }

    func commandFinished(success: Bool) {
        state.dropShelfPhase = success ? .success : .failure
        state.shelfLastResult = success ? "paperflow completed successfully." : "paperflow failed. Review command output."
        if success {
            scheduleAutoCollapse()
        } else {
            showExpanded()
        }
    }

    private func showPanel(expanded: Bool, on screen: NSScreen? = nil) {
        auxiliaryPanels.forEach { $0.orderOut(nil) }
        auxiliaryPanels.removeAll()
        let targetScreen = screen ?? monitorManager.focusedScreen(strategy: state.focusedMonitorStrategy)
        let frame = ScreenPlacementPolicy.shelfFrame(on: targetScreen, expanded: expanded)
        let panel = ensurePanel(frame: frame)
        panel.setFrame(frame, display: true, animate: panel.isVisible)
        panel.orderFrontRegardless()
    }

    private func refreshHotZoneFrames() {
        guard state.hotZoneEnabled, hotZoneWindows.count == 1 else {
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
                self?.showCompact()
            }
        }
        collapseTask = task
        DispatchQueue.main.asyncAfter(deadline: .now() + state.autoCollapseDelay, execute: task)
    }

    private func cancelAutoCollapse() {
        collapseTask?.cancel()
        collapseTask = nil
    }
}
