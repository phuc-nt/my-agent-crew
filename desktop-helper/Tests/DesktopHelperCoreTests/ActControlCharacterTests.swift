import Foundation
import XCTest
@testable import DesktopHelperCore

/// `type` and `set_value` never carry a control character but tab, line feed and carriage
/// return: in a terminal one of them interrupts, erases a character or starts an escape, so the
/// text that lands would not be the text the owner approved.
final class ActControlCharacterTests: HelperTestCase {
    /// Texts whose control character would change what a terminal runs.
    private static let refused = [
        "echo ok\u{0F}", "echo ok\u{03}", "sudx\u{08}o ls", "curl x | b\u{08}bash", "\u{1B}[A",
        "a\u{7F}", "a\u{85}", "\u{00}",
    ]

    /// Texts that hold no control character but the three allowed ones, each short enough to be
    /// typed in one piece.
    private static let accepted = [
        "a\tb", "a\nb", "a\rb", "a\r\nb", "Việt, đủ dấu", "ăâđêôơư ỹ",
        "\u{20}\u{7E}\u{A0}\u{AD}", "a\u{200D}b\u{2028}c", "😀",
    ]

    private static func detail(naming code: String) -> String {
        "`text` holds the control character \(code); only tab, line feed and carriage return may be in it."
    }

    private func readField() {
        readTree([Self.field])
        system.elementFrames[Self.field.element] = Self.field.frame
        system.forgetCalls()
    }

    func testTypeOfTextHoldingAControlCharacterIsBadRequestAndAsksTheMachineNothing() {
        let codes = ["U+000F", "U+0003", "U+0008", "U+0008", "U+001B", "U+007F", "U+0085", "U+0000"]
        for (text, code) in zip(Self.refused, codes) {
            system.forgetCalls()
            let reply = act("type", ["text": text])
            assertRefused(reply, .badRequest, text.debugDescription)
            XCTAssertEqual(reply["detail"] as? String, Self.detail(naming: code), text.debugDescription)
            XCTAssertEqual(system.calls, [], "nothing is typed: \(text.debugDescription)")
        }
    }

    func testSetValueOfTextHoldingAControlCharacterIsBadRequestAndSetsNothing() {
        readField()
        for text in Self.refused {
            system.forgetCalls()
            let reply = act("set_value", ["ref": "a1", "text": text])
            assertRefused(reply, .badRequest, text.debugDescription)
            XCTAssertEqual(system.calls, [], "nothing is set: \(text.debugDescription)")
        }
    }

    func testControlCharacterAnywhereInALongTextIsFound() {
        readField()
        let long = String(repeating: "x", count: 1500)
        for text in [long + "\u{07}", "\u{07}" + long, long + "\u{9F}" + long] {
            assertRefused(act("type", ["text": String(text.prefix(2000))]), .badRequest)
            assertRefused(act("set_value", ["ref": "a1", "text": text]), .badRequest)
        }
        XCTAssertEqual(system.actions, [])
    }

    func testEveryControlCharacterButTabLineFeedAndCarriageReturnIsRefusedByBothKinds() {
        readField()
        for value in Array(0x00...0x1F) + Array(0x7F...0x9F) {
            let scalar = Unicode.Scalar(UInt32(value))!
            let text = "a" + String(Character(scalar)) + "b"
            let code = String(format: "U+%04X", value)
            if [0x09, 0x0A, 0x0D].contains(value) {
                assertOK(act("type", ["text": text]), code)
                assertOK(act("set_value", ["ref": "a1", "text": text]), code)
            } else {
                let typed = act("type", ["text": text])
                assertRefused(typed, .badRequest, code)
                XCTAssertEqual(typed["detail"] as? String, Self.detail(naming: code))
                assertRefused(act("set_value", ["ref": "a1", "text": text]), .badRequest, code)
            }
        }
        XCTAssertEqual(system.actions, [
            .postText("a\tb"), .setValue(31, "a\tb"), .postText("a\nb"), .setValue(31, "a\nb"),
            .postText("a\rb"), .setValue(31, "a\rb"),
        ])
    }

    func testTextWithOnlyTheAllowedControlsIsTypedAndSetAsItIs() {
        readField()
        for text in Self.accepted {
            system.forgetCalls()
            assertOK(act("type", ["text": text]), text.debugDescription)
            assertOK(act("set_value", ["ref": "a1", "text": text]), text.debugDescription)
            XCTAssertEqual(system.actions, [.postText(text), .setValue(31, text)], text.debugDescription)
        }
    }

    func testRefusedCharactersAreExactlyUnicodesControlsLessTheThreeAllowed() {
        let allowed: Set<UInt32> = [0x09, 0x0A, 0x0D]
        var refusedCount = 0
        var wrong: [String] = []
        for value in UInt32(0)...0x10FFFF {
            guard let scalar = Unicode.Scalar(value) else { continue }
            let refuse = scalar.properties.generalCategory == .control && !allowed.contains(value)
            let found = TextTools.forbiddenControl(in: String(Character(scalar)))
            if found != (refuse ? scalar : nil) { wrong.append(String(format: "U+%04X", value)) }
            if refuse { refusedCount += 1 }
        }
        XCTAssertEqual(wrong, [], "refused or let through against Unicode's own category")
        XCTAssertEqual(refusedCount, 65 - 3)
    }

    func testFirstForbiddenControlIsTheOneNamed() {
        XCTAssertEqual(TextTools.forbiddenControl(in: "a\tb\u{1B}c\u{7F}"), Unicode.Scalar(0x1B))
        XCTAssertNil(TextTools.forbiddenControl(in: ""))
        XCTAssertNil(TextTools.forbiddenControl(in: "\t\n\r"))
    }
}
