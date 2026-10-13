import CoreGraphics
import DesktopHelperCore
import Foundation

enum WindowList {
    /// Every on-screen window, front to back, as the window server lists them.
    static func onScreen() throws -> [WindowInfo] {
        // Asked here whatever the caller asked: the titles of other applications' windows are
        // what Screen Recording guards.
        guard CGPreflightScreenCaptureAccess() else { throw SystemError.screenRecordingMissing }
        guard let rows = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID)
            as? [[String: Any]]
        else {
            throw SystemError.failed("The system gave no list of windows.")
        }
        return rows.compactMap(window)
    }

    private static func window(_ row: [String: Any]) -> WindowInfo? {
        guard let pid = (row[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value,
              let layer = (row[kCGWindowLayer as String] as? NSNumber)?.intValue,
              let raw = row[kCGWindowBounds as String] as? NSDictionary,
              let bounds = CGRect(dictionaryRepresentation: raw as CFDictionary)
        else { return nil }
        return WindowInfo(
            app: row[kCGWindowOwnerName as String] as? String ?? "",
            pid: pid,
            title: row[kCGWindowName as String] as? String ?? "",
            bounds: ScreenRect(
                x: bounds.origin.x, y: bounds.origin.y, width: bounds.width, height: bounds.height
            ),
            layer: layer
        )
    }
}
