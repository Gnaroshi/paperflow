import AppKit
import ApplicationServices

@MainActor
final class MultiMonitorManager {
    func targetScreens(for state: AppState) -> [NSScreen] {
        switch state.displayMode {
        case .allMonitors:
            return NSScreen.screens
        case .primaryMonitor:
            return [NSScreen.screens.first ?? NSScreen.main].compactMap { $0 }
        case .cursorMonitor:
            return [cursorScreen()]
        case .focusedMonitor:
            return [appFocusedScreen() ?? focusedScreen(strategy: state.focusedMonitorStrategy)]
        }
    }

    func focusedScreen(strategy: FocusedMonitorStrategy) -> NSScreen {
        switch strategy {
        case .keyboardMainScreen:
            return appFocusedScreen() ?? NSScreen.main ?? cursorScreen()
        case .cursorScreen:
            return cursorScreen()
        case .frontmostAppWindowScreen:
            guard AXIsProcessTrusted() else {
                return cursorScreen()
            }
            // Placeholder: mapping the frontmost app's focused window to a screen needs
            // Accessibility window bounds. Fall back to cursor screen until that bridge is added.
            return cursorScreen()
        }
    }

    func cursorScreen() -> NSScreen {
        let point = NSEvent.mouseLocation
        return NSScreen.screens.first { $0.frame.contains(point) }
            ?? NSScreen.main
            ?? NSScreen.screens.first
            ?? {
                fatalError("PaperFlow could not find any NSScreen instances.")
            }()
    }

    private func appFocusedScreen() -> NSScreen? {
        if let keyScreen = NSApp.keyWindow?.screen {
            return keyScreen
        }
        if let mainScreen = NSApp.mainWindow?.screen {
            return mainScreen
        }
        return nil
    }

    func screenDescription() -> String {
        NSScreen.screens.enumerated().map { index, screen in
            "Screen \(index): frame=\(screen.frame), visible=\(screen.visibleFrame)"
        }
        .joined(separator: "\n")
    }
}
