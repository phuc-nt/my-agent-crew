import Foundation

/// The arguments of one request. A key given as `null` counts as not given.
struct Arguments: Equatable {
    private let values: [String: JSONValue]

    init(_ values: [String: JSONValue]) {
        self.values = values
    }

    private func value(_ key: String) -> JSONValue? {
        guard let value = values[key], value != .null else { return nil }
        return value
    }

    func string(_ key: String) throws -> String? {
        guard let value = value(key) else { return nil }
        guard let text = value.stringValue else { throw Refusal.badRequest("`\(key)` must be text.") }
        return text
    }

    func requiredString(_ key: String) throws -> String {
        guard let text = try string(key) else { throw Refusal.badRequest("`\(key)` is missing.") }
        return text
    }

    func whole(_ key: String) throws -> Int? {
        guard let value = value(key) else { return nil }
        guard let number = value.intValue else {
            throw Refusal.badRequest("`\(key)` must be a whole number.")
        }
        return number
    }

    func requiredWhole(_ key: String) throws -> Int {
        guard let number = try whole(key) else { throw Refusal.badRequest("`\(key)` is missing.") }
        return number
    }

    func number(_ key: String) throws -> Double? {
        guard let value = value(key) else { return nil }
        guard let number = value.numberValue else {
            throw Refusal.badRequest("`\(key)` must be a number.")
        }
        return number
    }
}

public struct Request: Equatable {
    public let id: String
    public let command: String
    let arguments: Arguments
}

public enum ParsedLine: Equatable {
    case request(Request)
    /// Answered `bad_request`; `id` is empty when the line gave none that can be sent back.
    case rejected(id: String, Refusal)
}

public enum RequestParser {
    static let oversize = Refusal.badRequest("The request line is over 64 KiB.")

    /// `line` is one request without its newline.
    public static func parse(_ line: Data) -> ParsedLine {
        guard line.count <= Limits.maxLineBytes else { return .rejected(id: "", oversize) }
        guard case .object(let members)? = JSONValue.parse(line) else {
            return .rejected(id: "", .badRequest("The request is not one JSON object."))
        }
        guard let id = members["id"]?.stringValue else {
            return .rejected(id: "", .badRequest("`id` is missing or is not text."))
        }
        guard id.unicodeScalars.count <= Limits.maxIDCharacters else {
            return .rejected(id: "", .badRequest("`id` is over 64 characters."))
        }
        guard let command = members["cmd"]?.stringValue else {
            return .rejected(id: id, .badRequest("`cmd` is missing or is not text."))
        }
        return .request(Request(id: id, command: command, arguments: Arguments(members)))
    }
}

enum Answer {
    static func ok(id: String, _ fields: [String: JSONValue]) -> JSONValue {
        var members = fields
        members["id"] = .string(id)
        members["ok"] = .bool(true)
        return .object(members)
    }

    static func refused(id: String, _ refusal: Refusal) -> JSONValue {
        .object([
            "id": .string(id),
            "ok": .bool(false),
            "error": .string(refusal.code.rawValue),
            "detail": .string(refusal.detail),
        ])
    }
}
