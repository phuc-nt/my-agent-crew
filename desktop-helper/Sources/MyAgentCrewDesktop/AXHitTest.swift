import ApplicationServices
import DesktopHelperCore
import Foundation

/// What is on top at a point of the screen, asked right before a pointer event goes there.
extension AXReader {
    /// Shorter than a tree's: the answer holds an event back, and no answer refuses it anyway.
    private static let hitTimeout: Float = 0.5
    /// The whole question, the walk up from what is on top included.
    private static let hitTime: TimeInterval = 1.5
    /// No accessibility tree the helper reads is deeper than this.
    private static let parentSteps = 64

    /// `AXUIElementCopyElementAtPosition` takes global coordinates in points with the origin at
    /// the top left corner of the main display, y growing downwards: the space of
    /// `kAXPositionAttribute`, of `CGDisplayBounds` (which the helper's displays come from) and
    /// of a `CGEvent`'s location. A `ScreenPoint` is in that space, so it goes in as it is.
    func hit(at point: ScreenPoint, within token: Int?, clock: () -> TimeInterval) throws -> PointHit? {
        guard AXIsProcessTrusted() else { throw SystemError.accessibilityMissing }
        let target = try token.map { try element($0) }
        let deadline = clock() + AXReader.hitTime
        let systemWide = AXUIElementCreateSystemWide()
        // Set on the system-wide element, the timeout holds for every element of this process
        // until it is set back.
        AXUIElementSetMessagingTimeout(systemWide, AXReader.hitTimeout)
        defer { AXUIElementSetMessagingTimeout(systemWide, AXReader.messagingTimeout) }
        var found: AXUIElement?
        let status = AXUIElementCopyElementAtPosition(systemWide, Float(point.x), Float(point.y), &found)
        switch status {
        case .success:
            break
        case .noValue:
            return nil
        default:
            throw AXAttributes.failure(status)
        }
        guard let found else { return nil }
        var pid: pid_t = 0
        let owner = AXUIElementGetPid(found, &pid)
        guard owner == .success else { throw AXAttributes.failure(owner) }
        guard let target else { return PointHit(pid: pid, insideTarget: false) }
        let inside = try isSelfOrDescendant(found, of: target, deadline: deadline, clock: clock)
        return PointHit(pid: pid, insideTarget: inside)
    }

    /// Up the parents from `element`, a bounded number of steps: an element that never reaches
    /// the target in them is not inside it.
    private func isSelfOrDescendant(
        _ element: AXUIElement, of target: AXUIElement, deadline: TimeInterval,
        clock: () -> TimeInterval
    ) throws -> Bool {
        var current: AXUIElement? = element
        for _ in 0..<AXReader.parentSteps {
            guard let here = current else { return false }
            if CFEqual(here, target) { return true }
            guard clock() < deadline else {
                throw SystemError.failed("The application took too long to say where its element is.")
            }
            current = AXAttributes.element(try AXAttributes.copy(here, kAXParentAttribute))
        }
        return false
    }
}
