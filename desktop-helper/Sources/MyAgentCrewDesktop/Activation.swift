import AppKit
import ApplicationServices
import DesktopHelperCore

enum Activation {
    /// Asks for the application to come to the front. Whether it did is the caller's to see.
    static func bringToFront(pid: Int32) throws {
        guard AXIsProcessTrusted() else { throw SystemError.accessibilityMissing }
        guard let app = NSRunningApplication(processIdentifier: pid), !app.isTerminated else {
            throw SystemError.appGone
        }
        if app.isHidden { app.unhide() }
        app.activate(options: [.activateAllWindows])
        // A background process asking for another application to be activated is a request the
        // system may turn down; told through Accessibility, the application comes forward itself.
        let element = AXUIElementCreateApplication(pid)
        AXUIElementSetMessagingTimeout(element, 1)
        AXUIElementSetAttributeValue(element, kAXFrontmostAttribute as CFString, kCFBooleanTrue)
    }
}
