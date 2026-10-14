import Foundation

enum ActKind: String, CaseIterable {
    case click
    case doubleClick = "double_click"
    case rightClick = "right_click"
    case drag
    case scroll
    case type
    case key
    case setValue = "set_value"
    case focusApp = "focus_app"

    /// The kinds that write text or keys: refused while a password is being typed.
    var writes: Bool { self == .type || self == .key || self == .setValue }
}

/// A place in a picture, in its pixels.
struct PixelPoint: Equatable {
    let x: Double
    let y: Double
}

/// An `act` request whose shape has been read: a known kind, `app` given, and what the kind
/// needs given and of the right type. Reading it asks the machine nothing.
struct ActRequest {
    let kind: ActKind
    let app: String
    /// Checked against the last capture whenever it is given, also for a kind that needs none.
    private(set) var frameID: String?
    private(set) var point: PixelPoint?
    private(set) var endPoint: PixelPoint?
    private(set) var ref: String?
    /// The name of the `ax` answer the ref was read in: given with every ref.
    private(set) var outline: String?
    private(set) var dx = 0
    private(set) var dy = 0
    private(set) var text = ""
    private(set) var combo: KeyCombo?

    init(_ arguments: Arguments) throws {
        let name = try arguments.requiredString("kind")
        guard let kind = ActKind(rawValue: name) else {
            let shown = TextTools.cut(name, to: 64)
            throw Refusal.badRequest("There is no kind of action named \(shown).")
        }
        let app = try arguments.requiredString("app")
        guard !app.isEmpty else { throw Refusal.badRequest("`app` is empty.") }
        self.kind = kind
        self.app = app
        frameID = try arguments.string("frame_id")
        switch kind {
        case .click, .doubleClick, .rightClick:
            try readClickTarget(arguments)
        case .drag:
            point = try ActRequest.requiredPoint(arguments, "x", "y")
            endPoint = try ActRequest.requiredPoint(arguments, "to_x", "to_y")
            try requireFrameID()
        case .scroll:
            point = try ActRequest.requiredPoint(arguments, "x", "y")
            dx = try arguments.requiredWhole("dx").clamped(to: Limits.scrollLines)
            dy = try arguments.requiredWhole("dy").clamped(to: Limits.scrollLines)
            try requireFrameID()
        case .type:
            text = try arguments.requiredString("text")
            guard text.unicodeScalars.count <= Limits.maxTextCharacters else {
                throw Refusal.badRequest("`text` is over 2000 characters.")
            }
        case .key:
            guard let combo = KeyCombo.parse(try arguments.requiredString("keys")) else {
                throw Refusal.badRequest("`keys` is not modifiers and one key the helper knows.")
            }
            self.combo = combo
        case .setValue:
            ref = try arguments.requiredString("ref")
            text = try arguments.requiredString("text")
            outline = try arguments.requiredString("outline")
        case .focusApp:
            break
        }
    }

    /// A pixel of a frame, or an element of the last tree: one of the two, not both.
    private mutating func readClickTarget(_ arguments: Arguments) throws {
        ref = try arguments.string("ref")
        point = try ActRequest.point(arguments, "x", "y")
        switch (ref, point) {
        case (nil, nil):
            throw Refusal.badRequest("A click needs `frame_id` with `x` and `y`, or `ref`.")
        case (.some, .some):
            throw Refusal.badRequest("A click takes `ref` or `x` and `y`, not both.")
        case (nil, .some):
            try requireFrameID()
        case (.some, nil):
            outline = try arguments.requiredString("outline")
        }
    }

    private func requireFrameID() throws {
        if frameID == nil { throw Refusal.badRequest("`frame_id` is missing.") }
    }

    private static func point(_ arguments: Arguments, _ across: String, _ down: String) throws
        -> PixelPoint? {
        switch (try arguments.number(across), try arguments.number(down)) {
        case (nil, nil):
            return nil
        case (let x?, let y?):
            return PixelPoint(x: x, y: y)
        case (nil, _):
            throw Refusal.badRequest("`\(across)` is missing.")
        case (_, nil):
            throw Refusal.badRequest("`\(down)` is missing.")
        }
    }

    private static func requiredPoint(_ arguments: Arguments, _ across: String, _ down: String)
        throws -> PixelPoint {
        guard let point = try point(arguments, across, down) else {
            throw Refusal.badRequest("`\(across)` and `\(down)` are missing.")
        }
        return point
    }
}
