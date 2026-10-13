import ApplicationServices
import CoreGraphics
import DesktopHelperCore
import Foundation

/// Posts mouse and keyboard events to the system. Each entry point asks for Accessibility itself
/// as its first line, whatever its caller checked.
enum InputEvents {
    private static let eventFailure = SystemError.failed("The system could not make the event.")

    static func click(at point: ScreenPoint, button: MouseButton, count: Int) throws {
        guard AXIsProcessTrusted() else { throw SystemError.accessibilityMissing }
        let place = CGPoint(x: point.x, y: point.y)
        try mouse(.mouseMoved, at: place)
        let right = button == .right
        // A double click is two presses the system is told belong together: state 1, then 2.
        for state in 1...max(1, count) {
            try mouse(right ? .rightMouseDown : .leftMouseDown, at: place, right: right, state: state)
            try mouse(right ? .rightMouseUp : .leftMouseUp, at: place, right: right, state: state)
        }
    }

    static func drag(from start: ScreenPoint, to end: ScreenPoint) throws {
        guard AXIsProcessTrusted() else { throw SystemError.accessibilityMissing }
        let first = CGPoint(x: start.x, y: start.y)
        let last = CGPoint(x: end.x, y: end.y)
        try mouse(.mouseMoved, at: first)
        try mouse(.leftMouseDown, at: first)
        let way = Result<Void, Error> {
            let steps = 12
            for step in 1...steps {
                let part = CGFloat(step) / CGFloat(steps)
                let place = CGPoint(
                    x: first.x + (last.x - first.x) * part, y: first.y + (last.y - first.y) * part
                )
                try mouse(.leftMouseDragged, at: place)
            }
        }
        // Whatever happened on the way, the button is let go; a release that cannot be made is
        // a failed drag, not a finished one.
        try mouse(.leftMouseUp, at: last)
        try way.get()
    }

    /// Lines. The system's wheels count up and left as positive, the contract down and right.
    static func scroll(at point: ScreenPoint, dx: Int, dy: Int) throws {
        guard AXIsProcessTrusted() else { throw SystemError.accessibilityMissing }
        let place = CGPoint(x: point.x, y: point.y)
        // The wheel goes to whatever is under the pointer.
        try mouse(.mouseMoved, at: place)
        guard let event = CGEvent(
            scrollWheelEvent2Source: source(), units: .line, wheelCount: 2,
            wheel1: Int32(-dy), wheel2: Int32(-dx), wheel3: 0
        ) else { throw eventFailure }
        event.location = place
        event.post(tap: .cghidEventTap)
        settle()
    }

    /// A short piece of text as one key press that carries the characters themselves, so the
    /// keyboard layout does not matter.
    static func type(_ chunk: String) throws {
        guard AXIsProcessTrusted() else { throw SystemError.accessibilityMissing }
        let units = Array(chunk.utf16)
        guard !units.isEmpty else { return }
        for pressed in [true, false] {
            guard let event = CGEvent(keyboardEventSource: source(), virtualKey: 0, keyDown: pressed)
            else { throw eventFailure }
            // A modifier somebody holds must not turn text into a shortcut.
            event.flags = []
            event.keyboardSetUnicodeString(stringLength: units.count, unicodeString: units)
            event.post(tap: .cghidEventTap)
        }
        settle()
    }

    static func key(code: UInt16, modifiers: KeyModifiers) throws {
        guard AXIsProcessTrusted() else { throw SystemError.accessibilityMissing }
        for pressed in [true, false] {
            guard let event = CGEvent(keyboardEventSource: source(), virtualKey: code, keyDown: pressed)
            else { throw eventFailure }
            event.flags = flags(modifiers)
            event.post(tap: .cghidEventTap)
        }
        settle()
    }

    private static func flags(_ modifiers: KeyModifiers) -> CGEventFlags {
        var flags: CGEventFlags = []
        if modifiers.contains(.command) { flags.insert(.maskCommand) }
        if modifiers.contains(.shift) { flags.insert(.maskShift) }
        if modifiers.contains(.option) { flags.insert(.maskAlternate) }
        if modifiers.contains(.control) { flags.insert(.maskControl) }
        if modifiers.contains(.function) { flags.insert(.maskSecondaryFn) }
        return flags
    }

    private static func source() -> CGEventSource? {
        CGEventSource(stateID: .hidSystemState)
    }

    /// Reached only from the entry points above, after their own check.
    private static func mouse(
        _ type: CGEventType, at place: CGPoint, right: Bool = false, state: Int = 1
    ) throws {
        guard let event = CGEvent(
            mouseEventSource: source(), mouseType: type, mouseCursorPosition: place,
            mouseButton: right ? .right : .left
        ) else { throw eventFailure }
        event.setIntegerValueField(.mouseEventClickState, value: Int64(state))
        event.post(tap: .cghidEventTap)
        settle()
    }

    /// Applications read events one at a time; a breath between two keeps them in order.
    private static func settle() {
        usleep(12_000)
    }
}
