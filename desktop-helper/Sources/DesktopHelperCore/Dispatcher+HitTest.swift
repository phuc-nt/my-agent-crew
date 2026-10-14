import Foundation

extension Dispatcher {
    /// The last check before a pointer event: whatever is on top at each point the event goes to
    /// belongs to the frontmost application, and a click by ref lands on that element or inside
    /// it. Another application's window, a notification, a menu or an overlay over the point
    /// would take the event instead. When the machine cannot say what is there, nothing is posted.
    /// Text, keys and values go to the focus or to an element, not to a point, so they pass.
    func checkPoints(of step: ActStep, front: AppInfo) throws {
        switch step {
        case .click(let point, _, _, let element):
            try checkPoint(point, "the click point", front: front, element: element)
        case .drag(let start, let end):
            // Both ends are looked at before the button goes down.
            try checkPoint(start, "the start of the drag", front: front, element: nil)
            try checkPoint(end, "the end of the drag", front: front, element: nil)
        case .scroll(let point, _, _):
            try checkPoint(point, "the scroll point", front: front, element: nil)
        case .type, .key, .setValue:
            return
        }
    }

    /// The details name the check that failed, never what is on the screen there.
    private func checkPoint(
        _ point: ScreenPoint, _ place: String, front: AppInfo, element: Int?
    ) throws {
        let hit: PointHit?
        do {
            hit = try system.topElement(at: point, within: element)
        } catch {
            throw Refusal(
                .pointCovered,
                "The helper could not tell what is on top at \(place), so nothing was posted."
            )
        }
        guard let hit else {
            throw Refusal(.pointCovered, "No element of any application is on top at \(place).")
        }
        guard hit.pid == front.pid else {
            throw Refusal(
                .pointCovered, "Another application is on top at \(place), not the frontmost one."
            )
        }
        if element != nil && !hit.insideTarget {
            throw Refusal(
                .pointCovered,
                "Another element of the frontmost application is on top of that element at \(place)."
            )
        }
    }
}
