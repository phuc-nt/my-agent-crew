import Foundation
import XCTest
@testable import DesktopHelperCore

/// `act` with kind `key` and `type`: what is never sent, how keys are written, how text goes out.
final class ActKeyboardTests: HelperTestCase {
    private let checks: [FakeSystem.Call] = [
        .isLocked, .isDisplayAsleep, .hasAccessibility, .frontmostApp,
    ]

    @discardableResult
    private func key(_ keys: String, app: String? = "TextEdit") -> [String: Any] {
        act("key", ["keys": keys], app: app)
    }

    /// Every order the words can be written in.
    private func orders(_ words: [String]) -> [[String]] {
        guard words.count > 1 else { return [words] }
        return words.indices.flatMap { index -> [[String]] in
            var rest = words
            let first = rest.remove(at: index)
            return orders(rest).map { [first] + $0 }
        }
    }

    private var typed: [String] {
        system.actions.compactMap {
            if case .postText(let chunk) = $0 { return chunk }
            return nil
        }
    }

    // MARK: secure input

    func testSecureEventInputRefusesTypeKeyAndSetValueAndNoOtherKind() {
        let requests = everyKindOfAction()
        system.secureInput = true
        for request in requests {
            let reply = act(request.kind, request.arguments)
            if ["type", "key", "set_value"].contains(request.kind) {
                assertRefused(reply, .secureInput, request.kind)
                XCTAssertEqual(
                    reply["detail"] as? String, "Secure Event Input is on: a password is being typed."
                )
            } else {
                assertOK(reply, request.kind)
            }
        }
        XCTAssertEqual(system.actions.count, 5, "the five kinds that only move the pointer")
        XCTAssertEqual(system.calls.filter { $0 == .isSecureInputOn }.count, 3)
        let wrote = system.actions.contains {
            switch $0 {
            case .postText, .postKey, .setValue: return true
            default: return false
            }
        }
        XCTAssertFalse(wrote)
    }

    func testTypeIsRefusedWhenASecureTextFieldHoldsTheFocus() {
        system.focusedSecure = true
        let reply = act("type", ["text": "hunter2"])
        assertRefused(reply, .secureInput)
        XCTAssertEqual(
            system.calls, checks + [.isSecureInputOn, .focusedElementIsSecure(pid: 4242)]
        )
    }

    func testFocusedElementIsAskedOfTheFrontmostApplication() {
        system.front = Fixture.notes
        assertOK(act("type", ["text": "milk"], app: "Notes"))
        XCTAssertTrue(system.calls.contains(.focusedElementIsSecure(pid: 500)))
    }

    func testKeyAndThePointerAreNotHeldBackByAFocusedSecureTextField() {
        let requests = everyKindOfAction().filter { $0.kind != "type" }
        system.focusedSecure = true
        for request in requests {
            assertOK(act(request.kind, request.arguments), request.kind)
        }
        XCTAssertFalse(system.calls.contains(.focusedElementIsSecure(pid: 4242)))
    }

    // MARK: blocked keys

    func testLockLogOutAndForceQuitAreBlockedInAnyOrderOfTheModifiers() {
        let blocked: [(modifiers: [String], key: String)] = [
            (["cmd", "ctrl"], "q"), (["cmd", "shift"], "q"), (["cmd", "opt", "shift"], "q"),
            (["cmd", "opt"], "esc"), (["cmd", "alt", "shift"], "q"), (["cmd", "alt"], "esc"),
        ]
        var written = 0
        for (modifiers, name) in blocked {
            for order in orders(modifiers) {
                let keys = (order + [name]).joined(separator: "+")
                for form in [keys, keys.uppercased(), keys.capitalized] {
                    let reply = key(form)
                    assertRefused(reply, .blockedKeys, form)
                    XCTAssertEqual(
                        reply["detail"] as? String,
                        "Those keys lock the screen, log out or force quit, so they are never sent."
                    )
                    written += 1
                }
            }
        }
        XCTAssertEqual(written, (2 + 2 + 6 + 2 + 6 + 2) * 3)
        XCTAssertEqual(system.touches, [])
        XCTAssertFalse(system.calls.contains(.frontmostApp), "the application is not looked at")
    }

    func testOneMoreModifierDoesNotGetPastTheBlock() {
        let more = [
            "cmd+ctrl+shift+q", "cmd+ctrl+opt+q", "fn+cmd+ctrl+q", "cmd+ctrl+opt+shift+fn+q",
            "fn+cmd+shift+q", "fn+cmd+opt+esc", "cmd+opt+shift+esc", "cmd+opt+ctrl+esc",
            "ctrl+alt+cmd+shift+fn+esc",
        ]
        for keys in more {
            assertRefused(key(keys), .blockedKeys, keys)
        }
        XCTAssertEqual(system.actions, [])
    }

    func testBlockedKeysAreBlockedWhateverTheApplication() {
        assertRefused(key("cmd+ctrl+q", app: "Notes"), .blockedKeys, "running, not frontmost")
        assertRefused(key("cmd+shift+q", app: "Xcode"), .blockedKeys, "not running")
        assertRefused(key("cmd+opt+esc", app: "com.apple.TextEdit"), .blockedKeys, "frontmost")
        system.front = nil
        assertRefused(key("cmd+opt+shift+q"), .blockedKeys, "no frontmost application")
        XCTAssertEqual(system.actions, [])
    }

    func testKeysNearTheBlockedOnesAreSent() {
        let table: [(String, UInt16, KeyModifiers)] = [
            ("cmd+q", 12, [.command]), ("ctrl+q", 12, [.control]), ("shift+q", 12, [.shift]),
            ("q", 12, []), ("cmd+opt+q", 12, [.command, .option]), ("cmd+fn+q", 12, [.command, .function]),
            ("ctrl+shift+q", 12, [.control, .shift]), ("ctrl+opt+shift+q", 12, [.control, .option, .shift]),
            ("cmd+shift+w", 13, [.command, .shift]), ("cmd+ctrl+w", 13, [.command, .control]),
            ("esc", 53, []), ("cmd+esc", 53, [.command]), ("opt+esc", 53, [.option]),
            ("cmd+shift+esc", 53, [.command, .shift]), ("cmd+ctrl+esc", 53, [.command, .control]),
            ("ctrl+opt+esc", 53, [.control, .option]),
        ]
        for (keys, _, _) in table {
            assertOK(key(keys), keys)
        }
        let expected: [FakeSystem.Call] = table.map { .postKey(code: $0.1, modifiers: $0.2) }
        XCTAssertEqual(system.actions, expected)
    }

    func testBlockedKeysWrittenAsTextAreOnlyText() {
        assertOK(act("type", ["text": "cmd+ctrl+q"]))
        XCTAssertEqual(system.actions, [.postText("cmd+ctrl+q")])
    }

    // MARK: how keys are written

    func testKeysTheContractAllows() {
        let all: KeyModifiers = [.command, .shift, .option, .control, .function]
        let table: [(String, UInt16, KeyModifiers)] = [
            ("s", 1, []), ("cmd+s", 1, [.command]), ("shift+tab", 48, [.shift]), ("enter", 36, []),
            ("CMD+S", 1, [.command]), ("Cmd+Shift+S", 1, [.command, .shift]), ("S", 1, []),
            ("shift+cmd+s", 1, [.command, .shift]), ("ctrl+a", 0, [.control]),
            ("alt+left", 123, [.option]), ("opt+left", 123, [.option]), ("ALT+LEFT", 123, [.option]),
            ("fn+f5", 96, [.function]), ("fn+delete", 117, [.function]),
            ("cmd+shift+opt+ctrl+fn+f12", 111, all), ("fn+ctrl+alt+shift+cmd+f12", 111, all),
            ("space", 49, []), ("esc", 53, []), ("backspace", 51, []), ("delete", 117, []),
            ("tab", 48, []), ("up", 126, []), ("down", 125, []), ("left", 123, []), ("right", 124, []),
            ("home", 115, []), ("end", 119, []), ("pageup", 116, []), ("pagedown", 121, []),
            ("f1", 122, []), ("f12", 111, []), ("0", 29, []), ("9", 25, []), ("cmd+1", 18, [.command]),
            ("-", 27, []), ("cmd+-", 27, [.command]), ("cmd+=", 24, [.command]),
            ("cmd+,", 43, [.command]), ("cmd+`", 50, [.command]), ("cmd+\\", 42, [.command]),
            ("ctrl+[", 33, [.control]), ("cmd+/", 44, [.command]), ("cmd+.", 47, [.command]),
        ]
        for (keys, _, _) in table {
            assertOK(key(keys), keys)
        }
        let expected: [FakeSystem.Call] = table.map { .postKey(code: $0.1, modifiers: $0.2) }
        XCTAssertEqual(system.actions, expected)
    }

    func testCharacterTypedWithShiftIsSentWithShift() {
        let table: [(String, UInt16, KeyModifiers)] = [
            ("?", 44, [.shift]), ("shift+/", 44, [.shift]), ("shift+?", 44, [.shift]),
            ("!", 18, [.shift]), ("cmd+{", 33, [.command, .shift]), ("\"", 39, [.shift]),
            ("~", 50, [.shift]), ("cmd+shift+>", 47, [.command, .shift]), ("_", 27, [.shift]),
        ]
        for (keys, _, _) in table {
            assertOK(key(keys), keys)
        }
        let expected: [FakeSystem.Call] = table.map { .postKey(code: $0.1, modifiers: $0.2) }
        XCTAssertEqual(system.actions, expected)
    }

    func testPlusIsBothTheSeparatorAndAKey() {
        let table: [(String, UInt16, KeyModifiers)] = [
            ("+", 24, [.shift]), ("cmd++", 24, [.command, .shift]),
            ("cmd+shift++", 24, [.command, .shift]), ("ctrl+alt++", 24, [.control, .option, .shift]),
        ]
        for (keys, _, _) in table {
            assertOK(key(keys), keys)
        }
        let expected: [FakeSystem.Call] = table.map { .postKey(code: $0.1, modifiers: $0.2) }
        XCTAssertEqual(system.actions, expected)
    }

    func testKeysTheContractDoesNotAllowAreBadRequestAndTheMachineIsNotAsked() {
        let rejected = [
            "", " ", "cmd+", "+s", "cmd++s", "++", "+++", "cmd+++", "cmd+s+", "cmd+cmd+s",
            "shift+shift+a", "ctrl+alt+opt+x", "super+s", "win+s", "command+s", "control+c",
            "option+a", "meta+a", "cmd+ab", "ab", "12", "power", "f13", "f0", "f123", "s+cmd",
            "enter+cmd", "cmd + s", " cmd+s", "cmd+s ", "cmd+ s", "é", "cmd+é", "cmd+shift", "cmd",
            "fn", "shift", "return", "escape", "del", "pgup", "page up", "capslock", "cmd-s",
            "cmd,s", "cmd s", "⌘s", "⌘+s", "\n", "\t", "cmd+\n", "cmd+space+a", "space+a",
            "a+b", "cmd+a+b", "😀", "cmd+😀",
        ]
        for keys in rejected {
            let reply = key(keys)
            assertRefused(reply, .badRequest, "<\(keys)>")
            XCTAssertEqual(
                reply["detail"] as? String, "`keys` is not modifiers and one key the helper knows.",
                "<\(keys)>"
            )
        }
        XCTAssertEqual(system.calls, [])
    }

    func testEveryKeyTheContractNamesCanBeWrittenAloneAndWithAModifier() {
        let named = [
            "enter", "tab", "space", "esc", "backspace", "delete", "up", "down", "left", "right",
            "home", "end", "pageup", "pagedown",
        ] + (1...12).map { "f\($0)" }
        let letters = "abcdefghijklmnopqrstuvwxyz".map(String.init)
        let digits = "0123456789".map(String.init)
        let punctuation = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~".map(String.init)
        XCTAssertEqual(punctuation.count, 32, "all of the printable ASCII punctuation")
        let every = named + letters + digits + punctuation
        XCTAssertEqual(Set(KeyTable.names), Set(every), "the table holds those keys and no other")
        XCTAssertEqual(KeyTable.names.count, every.count, "and each of them once")

        for name in every {
            guard let alone = KeyCombo.parse(name) else {
                XCTFail("<\(name)> is not read")
                continue
            }
            XCTAssertEqual(alone.key, name)
            guard let held = KeyCombo.parse("ctrl+\(name)") else {
                XCTFail("<ctrl+\(name)> is not read")
                continue
            }
            XCTAssertEqual(held.code, alone.code, name)
            XCTAssertEqual(held.modifiers, alone.modifiers.union(.control), name)
            XCTAssertEqual(KeyCombo.parse(name.uppercased())?.code, alone.code, name)
        }
    }

    func testEveryKeyHasItsOwnCodeAndAShiftedCharacterTheCodeOfItsKey() {
        var plain: [UInt16: String] = [:]
        var shifted: [String: UInt16] = [:]
        for name in KeyTable.names {
            guard let found = KeyTable.lookup(name) else { return XCTFail("<\(name)> is not found") }
            if found.shifted {
                shifted[name] = found.code
            } else {
                XCTAssertNil(plain[found.code], "<\(name)> and <\(plain[found.code] ?? "")> share a code")
                plain[found.code] = name
            }
        }
        XCTAssertEqual(plain.count, 26 + 10 + 26 + 11)
        XCTAssertEqual(shifted.count, 21)
        for (name, code) in shifted {
            XCTAssertNotNil(plain[code], "<\(name)> is on no key")
        }
        let pairs = ["!": "1", "@": "2", "+": "=", "_": "-", "?": "/", "\"": "'", "~": "`", "|": "\\"]
        for (upper, lower) in pairs {
            XCTAssertEqual(KeyTable.lookup(upper)?.code, KeyTable.lookup(lower)?.code, upper)
        }
    }

    // MARK: type

    func testTypeHandsTheTextOverInPiecesOfAtMost20UTF16Units() {
        let text = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRS"
        XCTAssertEqual(text.count, 45)
        system.forgetCalls()
        let reply = act("type", ["text": text])
        assertOK(reply)
        XCTAssertEqual(reply["effect"] as? String, "posted")
        let between: [FakeSystem.Call] = [.frontmostApp, .isSecureInputOn]
        var expected = checks
        expected += [.isSecureInputOn, .focusedElementIsSecure(pid: 4242)]
        expected += [.postText("abcdefghijklmnopqrst")] + between
        expected += [.postText("uvwxyzABCDEFGHIJKLMN")] + between
        expected += [.postText("OPQRS"), .frontmostApp]
        XCTAssertEqual(system.calls, expected)
        XCTAssertEqual(Limits.typingChunkUnits, 20)
    }

    func testTypeSendsTheTextAsItIsWhateverItHolds() {
        let texts = [
            "hello", "Tiếng Việt có dấu, đủ cả: ăâđêôơư", "line one\nline two\ttabbed",
            "enter", "cmd+q", "\"quoted\" \\ back", "😀😃😄😁😆😅😂🤣😊😇🙂🙃😉", "🇻🇳🇯🇵🇺🇸🇫🇷🇩🇪🇮🇹🇪🇸🇬🇧🇨🇦🇧🇷🇮🇳🇰🇷",
            "e\u{301}e\u{301}e\u{301}e\u{301}e\u{301}e\u{301}e\u{301}e\u{301}e\u{301}e\u{301}e\u{301}",
            "👨‍👩‍👧‍👦👨‍👩‍👧‍👦👨‍👩‍👧‍👦", String(repeating: "ab ", count: 40), " ", "x",
        ]
        for text in texts {
            reset()
            assertOK(act("type", ["text": text]), text)
            XCTAssertEqual(typed.joined(), text)
            XCTAssertEqual(
                Array(typed.joined().unicodeScalars), Array(text.unicodeScalars),
                "not one scalar is lost, added or moved"
            )
            for chunk in typed {
                XCTAssertFalse(chunk.isEmpty, text)
                XCTAssertLessThanOrEqual(chunk.utf16.count, 20, text)
            }
            XCTAssertFalse(system.actions.contains { $0 == .postKey(code: 36, modifiers: []) })
        }
    }

    func testTextOf2000CharactersIsTypedAndOf2001IsBadRequest() {
        let most = String(repeating: "x", count: 2000)
        assertOK(act("type", ["text": most]))
        XCTAssertEqual(typed.count, 100)
        XCTAssertEqual(typed.joined(), most)

        reset()
        let over = act("type", ["text": most + "x"])
        assertRefused(over, .badRequest)
        XCTAssertEqual(over["detail"] as? String, "`text` is over 2000 characters.")
        XCTAssertEqual(system.calls, [], "a text that is too long asks the machine nothing")
        XCTAssertEqual(Limits.maxTextCharacters, 2000)
    }

    func testTextLimitCountsUnicodeScalars() {
        let emoji = String(repeating: "😀", count: 2000)
        assertOK(act("type", ["text": emoji]))
        XCTAssertEqual(typed.joined(), emoji)
        XCTAssertEqual(typed.count, 200, "ten of them fill 20 UTF-16 units")

        reset()
        assertRefused(act("type", ["text": emoji + "😀"]), .badRequest)

        reset()
        let flags = String(repeating: "🇻🇳", count: 1000)
        assertOK(act("type", ["text": flags]), "1000 flags are 2000 scalars")
        XCTAssertEqual(typed.joined(), flags)

        reset()
        assertRefused(act("type", ["text": flags + "🇻🇳"]), .badRequest)
        XCTAssertEqual(system.calls, [])
    }

    func testEmptyTextPostsNothingAndIsOK() {
        let reply = act("type", ["text": ""])
        assertOK(reply)
        XCTAssertEqual(reply["effect"] as? String, "posted")
        XCTAssertEqual(system.actions, [])
    }

    func testTypingStopsWhenAnotherApplicationComesToTheFront() {
        system.onCall = { [weak system] call in
            if case .postText = call { system?.front = Fixture.notes }
        }
        let reply = act("type", ["text": String(repeating: "a", count: 50)])
        assertRefused(reply, .appMismatch)
        XCTAssertEqual(
            reply["detail"] as? String,
            "The frontmost application changed after 20 characters were typed."
        )
        XCTAssertEqual(system.actions, [.postText(String(repeating: "a", count: 20))])
    }

    func testTypingStopsWhenSecureEventInputComesOn() {
        var chunks = 0
        system.onCall = { [weak system] call in
            guard case .postText = call else { return }
            chunks += 1
            if chunks == 2 { system?.secureInput = true }
        }
        let reply = act("type", ["text": String(repeating: "b", count: 100)])
        assertRefused(reply, .secureInput)
        XCTAssertEqual(
            reply["detail"] as? String, "Secure Event Input came on after 40 characters were typed."
        )
        XCTAssertEqual(typed, [String(repeating: "b", count: 20), String(repeating: "b", count: 20)])
    }

    func testTypingStopsAtThePieceTheSystemRefuses() {
        var chunks = 0
        system.onCall = { [weak system] call in
            guard case .postText = call else { return }
            chunks += 1
            if chunks == 2 { system?.postError = .failed("The event could not be made.") }
        }
        assertRefused(act("type", ["text": String(repeating: "c", count: 100)]), .internalError)
        XCTAssertEqual(typed.count, 2, "no piece is tried after the one that failed")
    }
}
