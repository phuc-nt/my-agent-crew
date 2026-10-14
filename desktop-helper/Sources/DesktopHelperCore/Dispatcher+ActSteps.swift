import Foundation

/// An action with its place worked out: everything the sixth check leaves to do.
enum ActStep: Equatable {
    case click(ScreenPoint, MouseButton, Int)
    case drag(ScreenPoint, ScreenPoint)
    case scroll(ScreenPoint, dx: Int, dy: Int)
    case type(String)
    case key(KeyCombo)
    case setValue(element: Int, text: String)
}

extension Dispatcher {
    /// The sixth check: the frame (`frame_mismatch`), the element (`ref_unknown`), then the
    /// point (`bad_request` when it is outside the picture).
    func resolve(_ action: ActRequest, front: AppInfo) throws -> ActStep {
        let frame = try action.frameID.map { try frames.frame($0, now: system.now()) }
        let target = try action.ref.map { try element(named: $0, of: action.outline, front: front) }
        switch action.kind {
        case .click:
            return .click(try clickPoint(action, frame, target), .left, 1)
        case .doubleClick:
            return .click(try clickPoint(action, frame, target), .left, 2)
        case .rightClick:
            return .click(try clickPoint(action, frame, target), .right, 1)
        case .drag:
            return .drag(try pixel(action.point, in: frame), try pixel(action.endPoint, in: frame))
        case .scroll:
            return .scroll(try pixel(action.point, in: frame), dx: action.dx, dy: action.dy)
        case .type:
            return .type(action.text)
        case .key:
            guard let combo = action.combo else { throw unread }
            return .key(combo)
        case .setValue:
            guard let target else { throw unread }
            return .setValue(element: target.element, text: action.text)
        case .focusApp:
            throw unread
        }
    }

    /// Reading the request's shape leaves none of these out; this is the answer if it ever did.
    private var unread: Refusal {
        Refusal(.internalError, "The request was read without what its kind needs.")
    }

    /// A ref counts only while its tree is the frontmost application's: the action is held to
    /// that application, and an element of another one would be outside it. And only as a ref
    /// of the last answer, named by the request: the same ref of an answer before it meant
    /// another element.
    private func element(named ref: String, of outline: String?, front: AppInfo) throws
        -> RefTarget {
        guard refs.pid == front.pid, let outline,
            let target = refs.target(for: ref, of: outline)
        else {
            throw Refusal(
                .refUnknown, "That ref is not in the last ax answer for the frontmost application."
            )
        }
        return target
    }

    private func pixel(_ point: PixelPoint?, in frame: Frame?) throws -> ScreenPoint {
        guard let point, let frame else { throw unread }
        guard let place = frame.point(x: point.x, y: point.y) else {
            throw Refusal.badRequest(
                "The point is outside the picture, which is \(frame.width) by \(frame.height) pixels."
            )
        }
        return place
    }

    /// The centre of the element as it is placed right now, or the pixel of the frame.
    private func clickPoint(_ action: ActRequest, _ frame: Frame?, _ target: RefTarget?) throws
        -> ScreenPoint {
        guard let target else { return try pixel(action.point, in: frame) }
        guard let place = try system.elementFrame(target.element) else {
            throw Refusal.badRequest("That element has no frame to click.")
        }
        return place.center
    }
}
