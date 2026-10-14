import Foundation

struct RefTarget: Equatable {
    let element: Int
    let secure: Bool
}

/// The elements of the last `ax` answer and nothing older.
struct RefStore {
    /// The application the last answer was read from.
    private(set) var pid: Int32?
    /// What the last answer goes by. Refs are counted from 1 in every answer, so a ref says
    /// which element it means only together with the name of the answer it was read in.
    private(set) var outline: String?
    private var targets: [String: RefTarget] = [:]

    mutating func forget() {
        pid = nil
        outline = nil
        targets = [:]
    }

    /// Keeps the answer's elements and gives the name the answer goes by, made for it alone.
    mutating func remember(pid: Int32, _ targets: [String: RefTarget]) -> String {
        let name = String(format: "%016llx", UInt64.random(in: .min ... .max))
        self.pid = pid
        self.outline = name
        self.targets = targets
        return name
    }

    /// The element a ref of the answer named `outline` means; none when that is not the last.
    func target(for ref: String, of outline: String) -> RefTarget? {
        self.outline == outline ? targets[ref] : nil
    }
}

enum AXShaping {
    static let secureRole = "AXSecureTextField"

    struct Tree {
        let nodes: [JSONValue]
        let targets: [String: RefTarget]
        let truncated: Bool
    }

    static func isSecure(_ node: RawNode) -> Bool {
        node.role == secureRole || node.subrole == secureRole
    }

    /// The contract's nodes: refs counted from 1, texts cut, a secure field without its value.
    static func shape(_ snapshot: AXSnapshot, limit: Int) -> Tree {
        var nodes: [JSONValue] = []
        var targets: [String: RefTarget] = [:]
        for (index, node) in snapshot.nodes.prefix(limit).enumerated() {
            let ref = "a\(index + 1)"
            let secure = isSecure(node)
            targets[ref] = RefTarget(element: node.element, secure: secure)
            nodes.append(shape(node, ref: ref, secure: secure))
        }
        let cutShort = snapshot.truncated || snapshot.nodes.count > limit
        return Tree(nodes: nodes, targets: targets, truncated: cutShort)
    }

    private static func shape(_ node: RawNode, ref: String, secure: Bool) -> JSONValue {
        var fields: [String: JSONValue] = [
            "ref": .string(ref),
            "depth": .int(node.depth),
            "role": .string(node.role),
        ]
        if let title = text(node.title) ?? text(node.description) { fields["title"] = .string(title) }
        if !secure, let value = text(node.value) { fields["value"] = .string(value) }
        if let focused = node.focused { fields["focused"] = .bool(focused) }
        if let enabled = node.enabled { fields["enabled"] = .bool(enabled) }
        if let frame = node.frame { fields["frame"] = Shape.rect(frame) }
        if secure { fields["secure"] = .bool(true) }
        return .object(fields)
    }

    private static func text(_ raw: String?) -> String? {
        guard let raw, !raw.isEmpty else { return nil }
        return TextTools.cut(raw)
    }
}
