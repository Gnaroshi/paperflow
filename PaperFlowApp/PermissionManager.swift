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
            filesAndFolders: "Uses selected project/vault folders. If a command fails, grant Files and Folders access in System Settings.",
            accessibility: AXIsProcessTrusted()
                ? "Granted"
                : "Not granted. Needed only for frontmost-app window screen detection.",
            inputMonitoring: "Not required for default Carbon global hotkeys.",
            loginItem: launchAtLogin ? "Requested" : "Off"
        )
    }

    static func openAccessibilitySettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility") {
            NSWorkspace.shared.open(url)
        }
    }
}
