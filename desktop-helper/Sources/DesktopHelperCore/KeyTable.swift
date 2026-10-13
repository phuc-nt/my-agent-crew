import Foundation

/// Virtual key codes of the US ANSI layout, which is what a posted key event carries.
enum KeyTable {
    struct Key: Equatable {
        let code: UInt16
        /// The character sits on the Shift level of its key.
        let shifted: Bool
    }

    static func lookup(_ name: String) -> Key? {
        if let code = plain[name] { return Key(code: code, shifted: false) }
        if let code = shifted[name] { return Key(code: code, shifted: true) }
        return nil
    }

    static var names: [String] { Array(plain.keys) + Array(shifted.keys) }

    private static let plain: [String: UInt16] = letters
        .merging(digits) { first, _ in first }
        .merging(named) { first, _ in first }
        .merging(punctuation) { first, _ in first }

    private static let letters: [String: UInt16] = [
        "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
        "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "o": 31, "u": 32,
        "i": 34, "p": 35, "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
    ]

    private static let digits: [String: UInt16] = [
        "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26, "8": 28, "0": 29,
    ]

    private static let named: [String: UInt16] = [
        "enter": 36, "tab": 48, "space": 49, "esc": 53, "backspace": 51, "delete": 117,
        "up": 126, "down": 125, "left": 123, "right": 124,
        "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
        "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
        "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    ]

    private static let punctuation: [String: UInt16] = [
        "=": 24, "-": 27, "]": 30, "[": 33, "'": 39, ";": 41, "\\": 42, ",": 43, "/": 44,
        ".": 47, "`": 50,
    ]

    private static let shifted: [String: UInt16] = [
        "!": 18, "@": 19, "#": 20, "$": 21, "^": 22, "%": 23, "(": 25, "&": 26, "*": 28, ")": 29,
        "+": 24, "_": 27, "}": 30, "{": 33, "\"": 39, ":": 41, "|": 42, "<": 43, "?": 44,
        ">": 47, "~": 50,
    ]
}
