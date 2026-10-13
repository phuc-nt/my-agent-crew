import ApplicationServices
import DesktopHelperCore
import Foundation

/// What one accessibility element said about itself.
struct AXValues {
    var role = ""
    var subrole: String?
    var title: String?
    var description: String?
    var value: String?
    var focused: Bool?
    var enabled: Bool?
    var frame: ScreenRect?
    var children: [AXUIElement] = []

    var isSecure: Bool {
        role == AXAttributes.secureRole || subrole == AXAttributes.secureRole
    }
}

/// Reading attributes of an element. Callers have checked Accessibility; nothing here does.
enum AXAttributes {
    static let secureRole = "AXSecureTextField"

    private static let names: [String] = [
        kAXRoleAttribute, kAXSubroleAttribute, kAXTitleAttribute, kAXDescriptionAttribute,
        kAXValueAttribute, kAXFocusedAttribute, kAXEnabledAttribute, kAXPositionAttribute,
        kAXSizeAttribute, kAXChildrenAttribute,
    ]

    /// Everything a node needs in one round trip to the application; `nil` when the element
    /// did not answer. An attribute the element lacks comes back as an error value and reads
    /// as absent.
    static func read(_ element: AXUIElement) -> AXValues? {
        var raw: CFArray?
        let status = AXUIElementCopyMultipleAttributeValues(
            element, names as CFArray, AXCopyMultipleAttributeOptions(rawValue: 0), &raw
        )
        guard status == .success, let items = (raw as NSArray?) as? [AnyObject],
              items.count == names.count
        else { return nil }
        var values = AXValues()
        values.role = items[0] as? String ?? ""
        values.subrole = items[1] as? String
        values.title = items[2] as? String
        values.description = items[3] as? String
        // What a password field holds is never carried further than this line.
        values.value = values.isSecure ? nil : text(items[4])
        values.focused = (items[5] as? NSNumber)?.boolValue
        values.enabled = (items[6] as? NSNumber)?.boolValue
        if let origin = point(items[7]), let size = size(items[8]) {
            values.frame = ScreenRect(x: origin.x, y: origin.y, width: size.width, height: size.height)
        }
        values.children = elements(items[9])
        return values
    }

    /// One attribute; `nil` when the element has none.
    static func copy(_ element: AXUIElement, _ name: String) throws -> AnyObject? {
        var value: CFTypeRef?
        let status = AXUIElementCopyAttributeValue(element, name as CFString, &value)
        switch status {
        case .success:
            return value
        case .noValue, .attributeUnsupported:
            return nil
        default:
            throw failure(status)
        }
    }

    /// An element that is gone or whose application does not answer can no longer be acted on.
    static func failure(_ status: AXError) -> SystemError {
        switch status {
        case .apiDisabled:
            return .accessibilityMissing
        case .invalidUIElement, .cannotComplete:
            return .elementGone
        default:
            return .failed("The accessibility request failed with code \(status.rawValue).")
        }
    }

    static func element(_ item: AnyObject?) -> AXUIElement? {
        guard let item, CFGetTypeID(item) == AXUIElementGetTypeID() else { return nil }
        return (item as! AXUIElement)
    }

    static func point(_ item: AnyObject) -> CGPoint? {
        var point = CGPoint.zero
        guard let value = geometry(item), AXValueGetValue(value, .cgPoint, &point) else { return nil }
        return point
    }

    static func size(_ item: AnyObject) -> CGSize? {
        var size = CGSize.zero
        guard let value = geometry(item), AXValueGetValue(value, .cgSize, &size) else { return nil }
        return size
    }

    private static func geometry(_ item: AnyObject) -> AXValue? {
        guard CFGetTypeID(item) == AXValueGetTypeID() else { return nil }
        return (item as! AXValue)
    }

    private static func elements(_ item: AnyObject) -> [AXUIElement] {
        guard let items = item as? [AnyObject] else { return [] }
        return items.compactMap { element($0) }
    }

    /// Text as it is, and the value of a control (a checkbox, a slider) as its number.
    private static func text(_ item: AnyObject) -> String? {
        if let text = item as? String { return text }
        if let text = item as? NSAttributedString { return text.string }
        if let number = item as? NSNumber { return number.stringValue }
        return nil
    }
}
