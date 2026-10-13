import Foundation

public struct KeyModifiers: OptionSet, Hashable {
    public let rawValue: Int

    public init(rawValue: Int) {
        self.rawValue = rawValue
    }

    public static let command = KeyModifiers(rawValue: 1)
    public static let shift = KeyModifiers(rawValue: 2)
    public static let option = KeyModifiers(rawValue: 4)
    public static let control = KeyModifiers(rawValue: 8)
    public static let function = KeyModifiers(rawValue: 16)

    static func named(_ word: Substring) -> KeyModifiers? {
        switch word {
        case "cmd": return .command
        case "shift": return .shift
        case "opt", "alt": return .option
        case "ctrl": return .control
        case "fn": return .function
        default: return nil
        }
    }
}

/// One key with its modifiers, as `act` with kind `key` writes it: `cmd+s`, `shift+tab`, `enter`.
public struct KeyCombo: Equatable {
    /// The key as written, lower case: `s`, `esc`, `+`.
    public let key: String
    public let code: UInt16
    /// What was written, plus Shift when the key is a character typed with Shift (`?`, `+`).
    public let modifiers: KeyModifiers

    /// `nil` for anything the contract's grammar does not allow.
    public static func parse(_ text: String) -> KeyCombo? {
        let lowered = text.lowercased()
        guard let (words, key) = split(lowered), let found = KeyTable.lookup(key) else { return nil }
        var modifiers: KeyModifiers = []
        for word in words {
            guard let modifier = KeyModifiers.named(word), !modifiers.contains(modifier) else {
                return nil
            }
            modifiers.insert(modifier)
        }
        if found.shifted { modifiers.insert(.shift) }
        return KeyCombo(key: key, code: found.code, modifiers: modifiers)
    }

    /// The modifier words and the key. `+` is both the separator and a key, so `cmd++` is
    /// Command with the plus key and `+` alone is the plus key.
    private static func split(_ text: String) -> ([Substring], String)? {
        if text == "+" { return ([], "+") }
        let head: Substring
        let key: String
        if text.hasSuffix("++") {
            head = text.dropLast(2)
            key = "+"
        } else if let separator = text.lastIndex(of: "+") {
            head = text[..<separator]
            key = String(text[text.index(after: separator)...])
        } else {
            return ([], text)
        }
        // A separator was written, so at least one modifier must stand before it.
        let words = head.split(separator: "+", omittingEmptySubsequences: false)
        return words.contains(where: \.isEmpty) ? nil : (words, key)
    }
}

/// The combinations the helper never sends, whatever the application and whatever else is held:
/// lock the screen, log out, force quit.
enum BlockedKeys {
    private static let rules: [(key: String, held: KeyModifiers)] = [
        ("q", [.command, .control]),
        ("q", [.command, .shift]),
        ("esc", [.command, .option]),
    ]

    /// A rule holds when its modifiers are all there; one more modifier does not get past it.
    static func blocks(_ combo: KeyCombo) -> Bool {
        rules.contains { combo.key == $0.key && combo.modifiers.isSuperset(of: $0.held) }
    }
}
