import AppKit
import ApplicationServices
import CoreGraphics
import DesktopHelperCore

/// The real machine. Whatever looks at the screen, reads another application or posts an event
/// checks its own permission first, in the code that does it, whatever the caller checked.
final class RealSystem: System {
    private let secureInput = SecureInputProbe()
    private let accessibility = AXReader()

    var canReadSecureInput: Bool { secureInput.isResolved }

    /// Keeps counting while the machine sleeps, so a frame taken before a long sleep is old.
    func now() -> TimeInterval {
        TimeInterval(clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW)) / 1_000_000_000
    }

    func pause(_ seconds: TimeInterval) {
        Thread.sleep(forTimeInterval: seconds)
    }

    /// A process with no session dictionary has no console to act on, which counts as locked.
    func isLocked() -> Bool {
        guard let session = CGSessionCopyCurrentDictionary() as? [String: Any] else { return true }
        return (session["CGSSessionScreenIsLocked"] as? NSNumber)?.boolValue ?? false
    }

    func isDisplayAsleep() -> Bool {
        CGDisplayIsAsleep(CGMainDisplayID()) != 0
    }

    func hasScreenRecording() -> Bool {
        CGPreflightScreenCaptureAccess()
    }

    func hasAccessibility() -> Bool {
        AXIsProcessTrusted()
    }

    func isSecureInputOn() -> Bool {
        secureInput.isOn
    }

    func displays() -> [DisplayInfo] {
        Displays.active()
    }

    func frontmostApp() -> AppInfo? {
        NSWorkspace.shared.frontmostApplication.flatMap(RealSystem.info)
    }

    func runningApps() -> [AppInfo] {
        NSWorkspace.shared.runningApplications
            .filter { $0.activationPolicy == .regular }
            .compactMap(RealSystem.info)
    }

    private static func info(_ app: NSRunningApplication) -> AppInfo? {
        guard !app.isTerminated, app.processIdentifier > 0 else { return nil }
        return AppInfo(
            name: app.localizedName ?? "", bundleID: app.bundleIdentifier ?? "",
            pid: app.processIdentifier, isHidden: app.isHidden
        )
    }

    /// The one place that may show the system's dialogs.
    func requestPermissions() {
        _ = CGRequestScreenCaptureAccess()
        // The value of `kAXTrustedCheckOptionPrompt`.
        _ = AXIsProcessTrustedWithOptions(["AXTrustedCheckOptionPrompt": true] as CFDictionary)
    }

    func windows() throws -> [WindowInfo] {
        try WindowList.onScreen()
    }

    func capture(display: UInt32, width: Int, height: Int) throws -> RawImage {
        try ScreenCapture.capture(display: display, width: width, height: height)
    }

    func accessibilityTree(pid: Int32, maxNodes: Int) throws -> AXSnapshot {
        try accessibility.tree(pid: pid, maxNodes: maxNodes, clock: now)
    }

    func elementFrame(_ element: Int) throws -> ScreenRect? {
        try accessibility.frame(of: element)
    }

    func focusedElementIsSecure(pid: Int32) -> Bool {
        accessibility.focusedIsSecure(pid: pid)
    }

    func setValue(_ element: Int, text: String) throws {
        try accessibility.setValue(element, text: text)
    }

    func topElement(at point: ScreenPoint, within element: Int?) throws -> PointHit? {
        try accessibility.hit(at: point, within: element, clock: now)
    }

    func postClick(at point: ScreenPoint, button: MouseButton, count: Int) throws {
        try InputEvents.click(at: point, button: button, count: count)
    }

    func postDrag(from start: ScreenPoint, to end: ScreenPoint) throws {
        try InputEvents.drag(from: start, to: end)
    }

    func postScroll(at point: ScreenPoint, dx: Int, dy: Int) throws {
        try InputEvents.scroll(at: point, dx: dx, dy: dy)
    }

    func postText(_ chunk: String) throws {
        try InputEvents.type(chunk)
    }

    func postKey(code: UInt16, modifiers: KeyModifiers) throws {
        try InputEvents.key(code: code, modifiers: modifiers)
    }

    func activate(pid: Int32) throws {
        try Activation.bringToFront(pid: pid)
    }
}
