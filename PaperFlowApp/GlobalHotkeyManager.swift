import Carbon
import Foundation

@MainActor
final class GlobalHotkeyManager {
    private enum HotkeyID: UInt32 {
        case commandWindow = 1
        case dropShelfEqual = 2
        case finderSelectionIngest = 3
        case dropShelfKeypadPlus = 4
    }

    private var handlerRef: EventHandlerRef?
    private var hotKeyRefs: [EventHotKeyRef?] = []
    private weak var state: AppState?

    func register(state: AppState) {
        self.state = state
        unregister()

        var eventType = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard),
            eventKind: UInt32(kEventHotKeyPressed)
        )
        let selfPointer = Unmanaged.passUnretained(self).toOpaque()
        let status = InstallEventHandler(
            GetApplicationEventTarget(),
            { _, event, userData in
                guard let event, let userData else {
                    return noErr
                }
                var hotKeyID = EventHotKeyID()
                let status = GetEventParameter(
                    event,
                    EventParamName(kEventParamDirectObject),
                    EventParamType(typeEventHotKeyID),
                    nil,
                    MemoryLayout<EventHotKeyID>.size,
                    nil,
                    &hotKeyID
                )
                guard status == noErr else {
                    return status
                }
                let manager = Unmanaged<GlobalHotkeyManager>
                    .fromOpaque(userData)
                    .takeUnretainedValue()
                Task { @MainActor in
                    manager.handleHotkey(id: hotKeyID.id)
                }
                return noErr
            },
            1,
            &eventType,
            selfPointer,
            &handlerRef
        )
        guard status == noErr else {
            state.invalidDropWarnings.append("Global hotkey handler failed to install: \(status)")
            return
        }

        registerKey(UInt32(kVK_Space), modifiers: UInt32(optionKey), id: .commandWindow)
        registerKey(UInt32(kVK_ANSI_Equal), modifiers: UInt32(controlKey | shiftKey | cmdKey), id: .dropShelfEqual)
        registerKey(UInt32(kVK_ANSI_KeypadPlus), modifiers: UInt32(controlKey | shiftKey | cmdKey), id: .dropShelfKeypadPlus)
        registerKey(UInt32(kVK_ANSI_I), modifiers: UInt32(optionKey | shiftKey), id: .finderSelectionIngest)
    }

    func unregister() {
        for ref in hotKeyRefs {
            if let ref {
                UnregisterEventHotKey(ref)
            }
        }
        hotKeyRefs.removeAll()
        if let handlerRef {
            RemoveEventHandler(handlerRef)
            self.handlerRef = nil
        }
    }

    private func registerKey(_ keyCode: UInt32, modifiers: UInt32, id: HotkeyID) {
        var ref: EventHotKeyRef?
        let hotKeyID = EventHotKeyID(signature: Self.signature, id: id.rawValue)
        let status = RegisterEventHotKey(
            keyCode,
            modifiers,
            hotKeyID,
            GetApplicationEventTarget(),
            0,
            &ref
        )
        if status == noErr {
            hotKeyRefs.append(ref)
        } else {
            state?.invalidDropWarnings.append("Global shortcut \(id) failed to register: \(status)")
        }
    }

    private func handleHotkey(id: UInt32) {
        guard let hotkey = HotkeyID(rawValue: id) else {
            return
        }
        switch hotkey {
        case .commandWindow:
            AppServices.shared.commandPopupWindow?.toggle()
        case .dropShelfEqual, .dropShelfKeypadPlus:
            AppServices.shared.shelfController?.toggleShelf()
        case .finderSelectionIngest:
            state?.invalidDropWarnings = ["Finder selection ingest is planned but not implemented yet."]
            AppServices.shared.shelfController?.showExpanded()
        }
    }

    private static let signature: OSType = {
        let scalars = Array("PFLW".unicodeScalars)
        return scalars.reduce(OSType(0)) { result, scalar in
            (result << 8) + OSType(scalar.value)
        }
    }()
}
