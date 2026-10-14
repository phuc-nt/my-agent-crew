import ApplicationServices
import DesktopHelperCore
import Foundation

/// Reads accessibility trees and keeps the elements of the last one, so that a ref of the last
/// answer can be clicked or set. Used from the request queue only.
final class AXReader {
    /// How long one question to an application may take.
    static let messagingTimeout: Float = 1
    /// How long a whole tree may take; what was read by then is the answer.
    private static let walkTime: TimeInterval = 5

    /// The elements of the last tree. A node's `element` is its place here.
    private var elements: [AXUIElement] = []

    func tree(pid: Int32, maxNodes: Int, clock: () -> TimeInterval) throws -> AXSnapshot {
        guard AXIsProcessTrusted() else { throw SystemError.accessibilityMissing }
        elements = []
        // Set on the system-wide element, the timeout holds for every element of this process.
        AXUIElementSetMessagingTimeout(AXUIElementCreateSystemWide(), AXReader.messagingTimeout)
        guard let window = try window(of: AXUIElementCreateApplication(pid)) else {
            return AXSnapshot(window: nil, nodes: [], truncated: false)
        }
        let deadline = clock() + AXReader.walkTime
        var title: String?
        var nodes: [RawNode] = []
        var truncated = false
        var waiting: [(element: AXUIElement, depth: Int)] = [(window, 0)]
        while let next = waiting.popLast() {
            if nodes.count >= maxNodes || clock() >= deadline {
                truncated = true
                break
            }
            guard let values = AXAttributes.read(next.element) else { continue }
            if next.depth == 0 { title = values.title ?? "" }
            nodes.append(RawNode(
                depth: next.depth, role: values.role, subrole: values.subrole, title: values.title,
                description: values.description, value: values.value, focused: values.focused,
                enabled: values.enabled, frame: values.frame, element: elements.count
            ))
            elements.append(next.element)
            // Last in, first out: pushed in reverse, the first child is read next. No more than
            // `maxNodes` of them can ever be answered, however long a table is.
            for child in values.children.prefix(maxNodes).reversed() {
                waiting.append((child, next.depth + 1))
            }
        }
        return AXSnapshot(window: title, nodes: nodes, truncated: truncated)
    }

    /// The focused window, else the main one; `nil` when the application shows neither.
    private func window(of app: AXUIElement) throws -> AXUIElement? {
        for name in [kAXFocusedWindowAttribute, kAXMainWindowAttribute] {
            var value: CFTypeRef?
            let status = AXUIElementCopyAttributeValue(app, name as CFString, &value)
            switch status {
            case .success:
                if let window = AXAttributes.element(value) { return window }
            case .noValue, .attributeUnsupported:
                continue
            case .apiDisabled:
                throw SystemError.accessibilityMissing
            case .invalidUIElement:
                throw SystemError.appGone
            default:
                throw SystemError.failed(
                    "The application did not answer the accessibility request (code \(status.rawValue))."
                )
            }
        }
        return nil
    }

    func element(_ token: Int) throws -> AXUIElement {
        guard elements.indices.contains(token) else { throw SystemError.elementGone }
        return elements[token]
    }

    /// Where the element is at this moment, which may not be where the tree saw it.
    func frame(of token: Int) throws -> ScreenRect? {
        guard AXIsProcessTrusted() else { throw SystemError.accessibilityMissing }
        let element = try element(token)
        guard let origin = try AXAttributes.copy(element, kAXPositionAttribute).flatMap(AXAttributes.point),
              let size = try AXAttributes.copy(element, kAXSizeAttribute).flatMap(AXAttributes.size)
        else { return nil }
        return ScreenRect(x: origin.x, y: origin.y, width: size.width, height: size.height)
    }

    func setValue(_ token: Int, text: String) throws {
        guard AXIsProcessTrusted() else { throw SystemError.accessibilityMissing }
        let element = try element(token)
        // Looked at again now: a field can have become a password field since the tree was read.
        guard let values = AXAttributes.read(element) else { throw SystemError.elementGone }
        if values.isSecure { throw SystemError.secureField }
        var settable: DarwinBoolean = false
        let asked = AXUIElementIsAttributeSettable(element, kAXValueAttribute as CFString, &settable)
        guard asked == .success, settable.boolValue else {
            if asked == .success || asked == .attributeUnsupported || asked == .noValue {
                throw SystemError.unsupported("That element's value cannot be set.")
            }
            throw AXAttributes.failure(asked)
        }
        let status = AXUIElementSetAttributeValue(element, kAXValueAttribute as CFString, text as CFString)
        guard status == .success else { throw AXAttributes.failure(status) }
    }

    /// Whether typing would go into a password field. An application that will not say what
    /// holds the focus has not ruled one out, so that counts as yes.
    func focusedIsSecure(pid: Int32) -> Bool {
        guard AXIsProcessTrusted() else { return true }
        let app = AXUIElementCreateApplication(pid)
        AXUIElementSetMessagingTimeout(app, AXReader.messagingTimeout)
        var value: CFTypeRef?
        switch AXUIElementCopyAttributeValue(app, kAXFocusedUIElementAttribute as CFString, &value) {
        case .success:
            guard let focused = AXAttributes.element(value) else { return false }
            return AXAttributes.read(focused)?.isSecure ?? true
        case .noValue, .attributeUnsupported, .notImplemented:
            return false
        default:
            return true
        }
    }
}
