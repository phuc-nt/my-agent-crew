import Foundation
import XCTest
@testable import DesktopHelperCore

final class RequestParsingTests: HelperTestCase {
    private func assertBadRequest(
        _ text: String, id: String = "", file: StaticString = #filePath, line: UInt = #line
    ) {
        let reply = answer(toLine: text)
        assertRefused(reply, .badRequest, text, file: file, line: line)
        XCTAssertEqual(reply["id"] as? String, id, text, file: file, line: line)
    }

    private func paddedRequest(bytes: Int) -> Data {
        let empty = #"{"id":"1","cmd":"state","pad":""}"#
        let pad = String(repeating: "a", count: bytes - empty.utf8.count)
        return Data(#"{"id":"1","cmd":"state","pad":"\#(pad)"}"#.utf8)
    }

    func testLineThatIsNotOneJSONObjectIsBadRequestWithAnEmptyID() {
        let lines = [
            "not json", "", "   ", #"{"id":"1","cmd":"state""#, "[1,2]", #"["state"]"#,
            #""state""#, "7", "null", "true",
        ]
        for text in lines { assertBadRequest(text) }
        XCTAssertEqual(system.calls, [])
    }

    func testBytesThatAreNotUTF8AreBadRequest() {
        let reply = decode(dispatcher.respond(to: Data([0x7B, 0xFF, 0xFE, 0x7D])))
        assertRefused(reply, .badRequest)
        XCTAssertEqual(reply["id"] as? String, "")
    }

    func testIDIsSentBackAsItCame() {
        let ids = [
            "1", "", String(repeating: "x", count: 64), String(repeating: "\u{E9}", count: 64),
            String(repeating: "\u{1F600}", count: 64), "a\"b\\c\nd", "req-0001/\u{4E2D}",
        ]
        for id in ids {
            let reply = ask("state", id: id)
            assertOK(reply)
            XCTAssertEqual(reply["id"] as? String, id)
        }
    }

    func testIDOver64CharactersIsBadRequestWithAnEmptyID() {
        let reply = ask("state", id: String(repeating: "x", count: 65))
        assertRefused(reply, .badRequest)
        XCTAssertEqual(reply["id"] as? String, "")
        XCTAssertEqual(system.calls, [])
        XCTAssertEqual(Limits.maxIDCharacters, 64)
    }

    func testIDThatIsMissingOrNotTextIsAnsweredWithAnEmptyID() {
        let lines = [
            #"{"cmd":"state"}"#, #"{"id":7,"cmd":"state"}"#, #"{"id":null,"cmd":"state"}"#,
            #"{"id":["1"],"cmd":"state"}"#, #"{"id":true,"cmd":"state"}"#,
        ]
        for text in lines { assertBadRequest(text) }
        XCTAssertEqual(system.calls, [])
    }

    func testCommandThatIsMissingOrNotTextIsBadRequestWithTheIDSentBack() {
        let lines = [#"{"id":"abc"}"#, #"{"id":"abc","cmd":5}"#, #"{"id":"abc","cmd":null}"#]
        for text in lines { assertBadRequest(text, id: "abc") }
    }

    func testUnknownCommandIsAnsweredAsSuch() {
        for name in ["reboot", "State", "", "screenshot ", String(repeating: "z", count: 300)] {
            let reply = ask(name, id: "x")
            assertRefused(reply, .unknownCommand, name)
            XCTAssertEqual(reply["id"] as? String, "x")
        }
        XCTAssertEqual(system.calls, [])
    }

    func testLineOfExactly64KiBIsAnsweredAndOneByteMoreIsNot() {
        let limit = 64 * 1024
        XCTAssertEqual(Limits.maxLineBytes, limit)
        let fits = paddedRequest(bytes: limit)
        XCTAssertEqual(fits.count, limit)
        assertOK(decode(dispatcher.respond(to: fits)))

        system.forgetCalls()
        let over = paddedRequest(bytes: limit + 1)
        XCTAssertEqual(over.count, limit + 1)
        let reply = decode(dispatcher.respond(to: over))
        assertRefused(reply, .badRequest)
        XCTAssertEqual(reply["id"] as? String, "")
        XCTAssertEqual(system.calls, [])
    }

    func testAnswerToALineThatNeverEndedIsBadRequestWithAnEmptyID() {
        let reply = decode(Dispatcher.oversizeLineAnswer)
        assertRefused(reply, .badRequest)
        XCTAssertEqual(reply["id"] as? String, "")
    }

    func testArgumentGivenAsNullCountsAsNotGiven() {
        let reply = answer(
            toLine: #"{"id":"1","cmd":"screenshot","display":null,"max_px":null,"since":null}"#
        )
        assertOK(reply)
        XCTAssertTrue(system.calls.contains(.capture(display: 1, width: 1456, height: 819)))
    }

    func testKeysTheCommandDoesNotKnowAreIgnored() {
        assertOK(answer(toLine: #"{"id":"1","cmd":"state","extra":{"a":[1,2.5,null]},"x":false}"#))
    }

    func testCarriageReturnBeforeTheNewlineIsHarmless() {
        assertOK(answer(toLine: "{\"id\":\"1\",\"cmd\":\"state\"}\r"))
    }

    func testNumberArgumentTakesNeitherBooleanNorTextNorFraction() {
        for value in ["true", "false", "\"400\"", "400.5", "[400]", "{}"] {
            assertBadRequest("{\"id\":\"9\",\"cmd\":\"screenshot\",\"max_px\":\(value)}", id: "9")
        }
        XCTAssertEqual(system.calls, [])
    }

    func testWholeNumberWrittenWithAFractionPartIsTaken() {
        assertOK(answer(toLine: #"{"id":"1","cmd":"screenshot","max_px":400.0}"#))
        XCTAssertTrue(system.calls.contains(.capture(display: 1, width: 400, height: 225)))
    }

    func testRefusalIsWrittenWithItsFourKeysInAFixedOrder() {
        let text = Answer.refused(id: "7", Refusal(.locked, "The console is locked.")).encoded()
        XCTAssertEqual(
            text, #"{"id":"7","ok":false,"error":"locked","detail":"The console is locked."}"#
        )
    }

    func testAnswerPutsIDAndOKFirstThenTheRestByName() {
        let fields: [String: JSONValue] = [
            "width": .int(3), "scale": .double(2), "app": .null, "main": .bool(true),
            "list": .array([.int(1), .string("a")]),
        ]
        XCTAssertEqual(
            Answer.ok(id: "7", fields).encoded(),
            #"{"id":"7","ok":true,"app":null,"list":[1,"a"],"main":true,"scale":2.0,"width":3}"#
        )
    }

    func testTextIsEscapedSoAnAnswerStaysOneLine() {
        let text = "a\"b\\c\nd\re\tf\u{01}\u{E9}\u{1F600}"
        let written = JSONValue.string(text).encoded()
        XCTAssertEqual(written, "\"a\\\"b\\\\c\\nd\\re\\tf\\u0001\u{E9}\u{1F600}\"")
        XCTAssertEqual(JSONValue.parse(Data(written.utf8)), .string(text))
    }

    func testErrorCodesAreTheContractsSixteen() {
        XCTAssertEqual(ErrorCode.allCases.map(\.rawValue), [
            "bad_request", "unknown_command", "locked", "display_asleep",
            "permission_missing:screen", "permission_missing:accessibility", "frame_mismatch",
            "app_not_running", "app_mismatch", "ref_unknown", "point_covered", "browser_app",
            "secure_input", "blocked_keys", "capture_failed", "internal",
        ])
    }

    func testCommandNamesAreTheContractsSeven() {
        XCTAssertEqual(
            Command.allCases.map(\.rawValue),
            ["state", "request_permissions", "apps", "windows", "screenshot", "ax", "act"]
        )
    }

    func testFailureNobodyForesawIsAnsweredInternal() {
        struct Surprise: Error {}
        system.windowsError = Surprise()
        assertRefused(ask("windows"), .internalError)
    }

    func testWhatTheMachineAnswersBecomesTheContractsCode() {
        let table: [(SystemError, ErrorCode)] = [
            (.screenRecordingMissing, .permissionMissingScreen),
            (.accessibilityMissing, .permissionMissingAccessibility),
            (.captureFailed("no"), .captureFailed),
            (.elementGone, .refUnknown),
            (.secureField, .secureInput),
            (.appGone, .appNotRunning),
            (.unsupported("no"), .badRequest),
            (.failed("no"), .internalError),
        ]
        for (error, code) in table {
            XCTAssertEqual(Refusal(error).code, code, "\(error)")
            XCTAssertFalse(Refusal(error).detail.isEmpty, "\(error)")
        }
    }
}
