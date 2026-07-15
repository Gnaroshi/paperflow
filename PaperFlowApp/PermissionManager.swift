import AppKit
import ApplicationServices
import Foundation
import ServiceManagement

struct PermissionStatus {
    let filesAndFolders: String
    let accessibility: String
    let inputMonitoring: String
    let loginItem: String
}

enum PermissionManager {
    static func status(launchAtLogin: Bool) -> PermissionStatus {
        PermissionStatus(
            filesAndFolders: "Uses only the PDF library and source folders you choose. If a file cannot be opened, allow Files and Folders access in System Settings.",
            accessibility: AXIsProcessTrusted()
                ? "On"
                : "Off. Enable only if you want PaperFlow to choose a screen from the frontmost window.",
            inputMonitoring: "Not required for the default shortcuts.",
            loginItem: launchAtLogin ? "On" : "Off"
        )
    }

    static func openAccessibilitySettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility") {
            NSWorkspace.shared.open(url)
        }
    }
}
