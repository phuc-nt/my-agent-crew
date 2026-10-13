import Foundation

extension Dispatcher {
    /// Always answers and never prompts: every read here is one that cannot show a dialog.
    func state() -> [String: JSONValue] {
        [
            "version": .string(HelperInfo.version),
            "protocol": .int(HelperInfo.protocolVersion),
            "locked": .bool(system.isLocked()),
            "display_asleep": .bool(system.isDisplayAsleep()),
            "screen_recording": .bool(system.hasScreenRecording()),
            "accessibility": .bool(system.hasAccessibility()),
            "secure_input": .bool(system.isSecureInputOn()),
            "displays": .array(system.displays().map { displayRow($0) }),
            "frontmost": Shape.frontmost(system.frontmostApp()),
        ]
    }

    private func displayRow(_ info: DisplayInfo) -> JSONValue {
        .object([
            "id": .int(Int(info.id)),
            "width": Shape.whole(info.bounds.width),
            "height": Shape.whole(info.bounds.height),
            "scale": .double(info.scale),
            "main": .bool(info.isMain),
        ])
    }

    /// A dialog on a locked console is one nobody can see, so nothing is asked for there.
    func requestPermissions() throws -> [String: JSONValue] {
        if system.isLocked() {
            throw Refusal(.locked, "The console is locked; nobody would see the system's dialog.")
        }
        system.requestPermissions()
        return [
            "screen_recording": .bool(system.hasScreenRecording()),
            "accessibility": .bool(system.hasAccessibility()),
        ]
    }

    func apps() -> [String: JSONValue] {
        let front = system.frontmostApp()?.pid
        let sorted = system.runningApps().sorted {
            let order = $0.name.compare($1.name, options: [.caseInsensitive])
            return order == .orderedSame ? $0.pid < $1.pid : order == .orderedAscending
        }
        let rows: [JSONValue] = sorted.map { app in
            .object([
                "app": .string(app.name),
                "bundle_id": .string(app.bundleID),
                "pid": .int(Int(app.pid)),
                "frontmost": .bool(app.pid == front),
                "hidden": .bool(app.isHidden),
            ])
        }
        return ["apps": .array(rows)]
    }

    func windows() throws -> [String: JSONValue] {
        let displays = system.displays()
        let ordinary = try system.windows().filter { $0.layer == 0 }.prefix(Limits.maxWindows)
        let rows: [JSONValue] = ordinary.map { window in
            .object([
                "app": .string(window.app),
                "pid": .int(Int(window.pid)),
                "title": .string(TextTools.cut(window.title)),
                "bounds": Shape.rect(window.bounds),
                "display": .int(Int(display(holding: window.bounds, among: displays))),
            ])
        }
        return ["windows": .array(rows)]
    }

    /// The display most of the window is on; the main display when it is on none.
    private func display(holding bounds: ScreenRect, among displays: [DisplayInfo]) -> UInt32 {
        let most = displays.max { $0.bounds.overlap(with: bounds) < $1.bounds.overlap(with: bounds) }
        if let most, most.bounds.overlap(with: bounds) > 0 { return most.id }
        return (displays.first(where: \.isMain) ?? displays.first)?.id ?? 0
    }
}
