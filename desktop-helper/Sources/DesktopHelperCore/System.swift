import Foundation

/// The only way the core reaches the machine. The executable holds the real one; the tests hold a
/// fake that records every call.
public protocol System: AnyObject {
    /// Seconds on a clock that never goes back and keeps counting while the machine sleeps.
    func now() -> TimeInterval
    func pause(_ seconds: TimeInterval)

    // Read without ever showing a system dialog.
    func isLocked() -> Bool
    func isDisplayAsleep() -> Bool
    func hasScreenRecording() -> Bool
    func hasAccessibility() -> Bool
    func isSecureInputOn() -> Bool
    func displays() -> [DisplayInfo]
    func frontmostApp() -> AppInfo?
    /// Applications with a Dock presence.
    func runningApps() -> [AppInfo]

    /// The one call that may show the system's permission dialogs.
    func requestPermissions()

    /// On-screen windows of every layer, front to back.
    func windows() throws -> [WindowInfo]
    /// The whole display, scaled to exactly this many pixels.
    func capture(display: UInt32, width: Int, height: Int) throws -> RawImage

    /// The focused (else main) window of that application, depth first, at most `maxNodes`
    /// elements. Elements of an earlier call stop being reachable.
    func accessibilityTree(pid: Int32, maxNodes: Int) throws -> AXSnapshot
    /// Where the element is right now; `nil` when it has no frame.
    func elementFrame(_ element: Int) throws -> ScreenRect?
    func focusedElementIsSecure(pid: Int32) -> Bool
    func setValue(_ element: Int, text: String) throws

    func postClick(at point: ScreenPoint, button: MouseButton, count: Int) throws
    func postDrag(from start: ScreenPoint, to end: ScreenPoint) throws
    /// Lines; a positive `dy` scrolls down, a positive `dx` scrolls right.
    func postScroll(at point: ScreenPoint, dx: Int, dy: Int) throws
    /// At most `Limits.typingChunkUnits` UTF-16 units, typed as they are.
    func postText(_ chunk: String) throws
    func postKey(code: UInt16, modifiers: KeyModifiers) throws
    func activate(pid: Int32) throws
}
