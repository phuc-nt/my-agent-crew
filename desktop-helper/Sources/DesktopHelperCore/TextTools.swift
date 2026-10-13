import Foundation

enum TextTools {
    /// At most `limit` characters (Unicode scalars), never cut inside what reads as one character.
    static func cut(_ text: String, to limit: Int = Limits.maxFieldCharacters) -> String {
        var kept = String.UnicodeScalarView()
        var used = 0
        for character in text {
            let size = character.unicodeScalars.count
            if used + size > limit { return String(kept) }
            kept.append(contentsOf: character.unicodeScalars)
            used += size
        }
        return text
    }

    /// The text in pieces of at most `limit` UTF-16 units, which is what one keyboard event
    /// carries. A piece ends between characters; a single character longer than a piece is split
    /// between its scalars, never inside a surrogate pair.
    static func typingChunks(_ text: String, limit: Int = Limits.typingChunkUnits) -> [String] {
        var chunks: [String] = []
        var current = ""
        var units = 0
        func flush() {
            if !current.isEmpty { chunks.append(current) }
            current = ""
            units = 0
        }
        for character in text {
            let size = character.utf16.count
            if size > limit {
                flush()
                for scalar in character.unicodeScalars {
                    let scalarSize = UTF16.width(scalar)
                    if units + scalarSize > limit { flush() }
                    current.unicodeScalars.append(scalar)
                    units += scalarSize
                }
                flush()
                continue
            }
            if units + size > limit { flush() }
            current.append(character)
            units += size
        }
        flush()
        return chunks
    }
}

/// How the contract writes sizes and places: whole numbers, and ratios to four decimals.
enum Shape {
    static func whole(_ value: Double) -> JSONValue {
        guard value.isFinite else { return .int(0) }
        return .int(Int(value.rounded().clamped(to: -1e12...1e12)))
    }

    static func rect(_ rect: ScreenRect) -> JSONValue {
        .array([whole(rect.x), whole(rect.y), whole(rect.width), whole(rect.height)])
    }

    static func ratio(_ value: Double) -> JSONValue {
        guard value.isFinite else { return .double(0) }
        return .double((value * 10_000).rounded() / 10_000)
    }

    static func frontmost(_ app: AppInfo?) -> JSONValue {
        guard let app else { return .null }
        return .object([
            "app": .string(app.name),
            "bundle_id": .string(app.bundleID),
            "pid": .int(Int(app.pid)),
        ])
    }
}

enum AppMatch {
    /// By name or bundle id, whatever the case.
    static func matches(_ wanted: String, _ app: AppInfo) -> Bool {
        same(wanted, app.name) || same(wanted, app.bundleID)
    }

    private static func same(_ wanted: String, _ held: String) -> Bool {
        !held.isEmpty && wanted.compare(held, options: [.caseInsensitive]) == .orderedSame
    }

    /// The frontmost application when it is the one meant, else the oldest process that is.
    static func find(_ wanted: String, among apps: [AppInfo], front: AppInfo?) -> AppInfo? {
        if let front, matches(wanted, front) { return front }
        return apps.filter { matches(wanted, $0) }.min { $0.pid < $1.pid }
    }
}
