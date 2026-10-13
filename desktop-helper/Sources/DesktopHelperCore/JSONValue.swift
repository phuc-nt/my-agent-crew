import Foundation

/// A JSON value that keeps whole numbers apart from fractions and booleans apart from numbers,
/// so `true` is never read as 1 and `2.0` is written back as `2.0`.
public enum JSONValue: Equatable {
    case null
    case bool(Bool)
    case int(Int)
    case double(Double)
    case string(String)
    case array([JSONValue])
    case object([String: JSONValue])

    /// `nil` when the bytes are not JSON (or not UTF-8).
    public static func parse(_ data: Data) -> JSONValue? {
        guard let raw = try? JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed]) else {
            return nil
        }
        return JSONValue(foundation: raw)
    }

    init?(foundation raw: Any) {
        switch raw {
        case is NSNull:
            self = .null
        case let number as NSNumber:
            self = JSONValue.number(number)
        case let text as String:
            self = .string(text)
        case let items as [Any]:
            var values: [JSONValue] = []
            for item in items {
                guard let value = JSONValue(foundation: item) else { return nil }
                values.append(value)
            }
            self = .array(values)
        case let members as [String: Any]:
            var values: [String: JSONValue] = [:]
            for (key, member) in members {
                guard let value = JSONValue(foundation: member) else { return nil }
                values[key] = value
            }
            self = .object(values)
        default:
            return nil
        }
    }

    private static func number(_ number: NSNumber) -> JSONValue {
        if CFGetTypeID(number) == CFBooleanGetTypeID() { return .bool(number.boolValue) }
        if CFNumberIsFloatType(number) { return .double(number.doubleValue) }
        let whole = number.int64Value
        // An unsigned value past Int64 wraps in `int64Value`; keep its size as a fraction instead.
        return NSNumber(value: whole) == number ? .int(Int(whole)) : .double(number.doubleValue)
    }

    public var stringValue: String? {
        if case .string(let text) = self { return text }
        return nil
    }

    /// A whole number, also when it was written as `1456.0`.
    public var intValue: Int? {
        switch self {
        case .int(let value):
            return value
        case .double(let value) where value.rounded() == value && abs(value) <= 9_007_199_254_740_992:
            return Int(value)
        default:
            return nil
        }
    }

    public var numberValue: Double? {
        switch self {
        case .int(let value):
            return Double(value)
        case .double(let value) where value.isFinite:
            return value
        default:
            return nil
        }
    }
}

extension JSONValue {
    /// Compact JSON on one line. Object keys come out in a fixed order (`id`, `ok`, `error`,
    /// `detail`, then by name) so a log of answers reads the same every time.
    public func encoded() -> String {
        var out = ""
        write(to: &out)
        return out
    }

    private static let leadingKeys = ["id", "ok", "error", "detail"]

    private func write(to out: inout String) {
        switch self {
        case .null:
            out += "null"
        case .bool(let value):
            out += value ? "true" : "false"
        case .int(let value):
            out += String(value)
        case .double(let value):
            out += value.isFinite ? "\(value)" : "null"
        case .string(let value):
            JSONValue.write(text: value, to: &out)
        case .array(let items):
            out += "["
            for (index, item) in items.enumerated() {
                if index > 0 { out += "," }
                item.write(to: &out)
            }
            out += "]"
        case .object(let members):
            let leading = JSONValue.leadingKeys.filter { members[$0] != nil }
            let rest = members.keys.filter { !JSONValue.leadingKeys.contains($0) }.sorted()
            out += "{"
            for (index, key) in (leading + rest).enumerated() {
                if index > 0 { out += "," }
                JSONValue.write(text: key, to: &out)
                out += ":"
                members[key]?.write(to: &out)
            }
            out += "}"
        }
    }

    private static func write(text: String, to out: inout String) {
        out += "\""
        // A picture's base64 is megabytes of text with nothing to escape: skip the scalar loop.
        if !text.utf8.contains(where: { $0 < 0x20 || $0 == 0x22 || $0 == 0x5C }) {
            out += text
        } else {
            for scalar in text.unicodeScalars {
                switch scalar {
                case "\"": out += "\\\""
                case "\\": out += "\\\\"
                case "\n": out += "\\n"
                case "\r": out += "\\r"
                case "\t": out += "\\t"
                default:
                    if scalar.value < 0x20 {
                        out += String(format: "\\u%04x", scalar.value)
                    } else {
                        out.unicodeScalars.append(scalar)
                    }
                }
            }
        }
        out += "\""
    }
}
