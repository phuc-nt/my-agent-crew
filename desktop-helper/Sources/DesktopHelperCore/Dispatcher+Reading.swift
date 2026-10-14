import Foundation

struct ScreenshotRequest {
    /// `nil` is the main display.
    let display: UInt32?
    let maxPx: Int
    let since: String?

    init(_ arguments: Arguments) throws {
        if let wanted = try arguments.whole("display") {
            guard let id = UInt32(exactly: wanted) else {
                throw Refusal.badRequest("`display` is not a display id.")
            }
            display = id
        } else {
            display = nil
        }
        maxPx = (try arguments.whole("max_px") ?? Limits.defaultMaxPx).clamped(to: Limits.maxPx)
        since = try arguments.string("since")
    }
}

struct AXRequest {
    /// `nil` is the frontmost application.
    let app: String?
    let maxNodes: Int

    init(_ arguments: Arguments) throws {
        app = try arguments.string("app")
        if app?.isEmpty == true { throw Refusal.badRequest("`app` is empty.") }
        maxNodes = (try arguments.whole("max_nodes") ?? Limits.defaultMaxNodes)
            .clamped(to: Limits.maxNodes)
    }
}

extension Dispatcher {
    func screenshot(_ shot: ScreenshotRequest) throws -> [String: JSONValue] {
        let display = try self.display(shot.display)
        let size = PictureSize.fit(display: display, maxPx: shot.maxPx)
        let image = try system.capture(display: display.id, width: size.width, height: size.height)
        guard image.width > 0, image.height > 0,
              image.rgba.count == image.width * image.height * 4
        else {
            throw Refusal(.captureFailed, "The system returned a picture that is not whole.")
        }
        let id = FrameID.make(
            pixels: image.rgba, width: image.width, height: image.height, display: display.id
        )
        // Remembered also when nothing changed: the caller's frame is the latest one again.
        frames.remember(Frame(
            id: id, display: display.id, takenAt: system.now(),
            width: image.width, height: image.height, displayBounds: display.bounds
        ))
        let unchanged = shot.since == id
        var fields: [String: JSONValue] = [
            "frame_id": .string(id),
            "display": .int(Int(display.id)),
            "width": .int(image.width),
            "height": .int(image.height),
            "scale": Shape.ratio(Double(image.width) / max(display.bounds.width, 1)),
            "unchanged": .bool(unchanged),
        ]
        if !unchanged {
            fields["png_base64"] = .string(try PNGEncoder.encode(image).base64EncodedString())
        }
        return fields
    }

    private func display(_ wanted: UInt32?) throws -> DisplayInfo {
        let displays = system.displays()
        if let wanted {
            guard let found = displays.first(where: { $0.id == wanted }) else {
                throw Refusal.badRequest("There is no display with id \(wanted).")
            }
            return found
        }
        guard let main = displays.first(where: \.isMain) ?? displays.first else {
            throw Refusal(.captureFailed, "There is no active display to capture.")
        }
        return main
    }

    func ax(_ query: AXRequest) throws -> [String: JSONValue] {
        let front = system.frontmostApp()
        let target: AppInfo
        if let wanted = query.app {
            guard let found = AppMatch.find(wanted, among: system.runningApps(), front: front) else {
                throw Refusal(.appNotRunning, "No running application is named that.")
            }
            target = found
        } else {
            guard let front else {
                throw Refusal(.appNotRunning, "There is no frontmost application.")
            }
            target = front
        }
        // Forgotten before the read: after it, the machine cannot reach the older elements.
        refs.forget()
        let snapshot = try system.accessibilityTree(pid: target.pid, maxNodes: query.maxNodes)
        let tree = AXShaping.shape(snapshot, limit: query.maxNodes)
        let outline = refs.remember(pid: target.pid, tree.targets)
        return [
            "outline": .string(outline),
            "app": .string(target.name),
            "pid": .int(Int(target.pid)),
            "window": snapshot.window.map { JSONValue.string(TextTools.cut($0)) } ?? .null,
            "truncated": .bool(tree.truncated),
            "nodes": .array(tree.nodes),
        ]
    }
}
