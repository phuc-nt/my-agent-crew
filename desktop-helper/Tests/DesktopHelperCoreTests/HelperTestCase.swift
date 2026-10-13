import Foundation
import XCTest
@testable import DesktopHelperCore

/// A dispatcher over a fake machine, and the few words the tests share for asking it things.
class HelperTestCase: XCTestCase {
    var system: FakeSystem!
    var dispatcher: Dispatcher!

    override func setUp() {
        super.setUp()
        reset()
    }

    override func tearDown() {
        system?.onCall = nil
        dispatcher = nil
        system = nil
        super.tearDown()
    }

    /// A machine in the fixture's state and a helper that has seen nothing yet.
    func reset() {
        system?.onCall = nil
        system = FakeSystem()
        dispatcher = Dispatcher(system: system)
    }

    /// Sends raw text as one request line and reads the answer line.
    func answer(toLine line: String) -> [String: Any] {
        decode(dispatcher.respond(to: Data(line.utf8)))
    }

    func decode(
        _ answer: String, file: StaticString = #filePath, line: UInt = #line
    ) -> [String: Any] {
        XCTAssertFalse(answer.contains("\n"), "an answer is one line", file: file, line: line)
        let parsed = (try? JSONSerialization.jsonObject(with: Data(answer.utf8))) as? [String: Any]
        XCTAssertNotNil(parsed, "not a JSON object: \(answer.prefix(200))", file: file, line: line)
        return parsed ?? [:]
    }

    @discardableResult
    func ask(_ command: String, _ arguments: [String: Any] = [:], id: String = "1") -> [String: Any] {
        var request = arguments
        request["id"] = id
        request["cmd"] = command
        guard let line = try? JSONSerialization.data(withJSONObject: request) else {
            XCTFail("the test's request is not JSON")
            return [:]
        }
        return decode(dispatcher.respond(to: line))
    }

    @discardableResult
    func act(_ kind: String, _ arguments: [String: Any] = [:], app: String? = "TextEdit")
        -> [String: Any] {
        var request = arguments
        request["kind"] = kind
        if let app { request["app"] = app }
        return ask("act", request)
    }

    func assertOK(
        _ answer: [String: Any], _ note: String = "",
        file: StaticString = #filePath, line: UInt = #line
    ) {
        let why = "\(note) \(answer["error"] ?? "") \(answer["detail"] ?? "")"
        XCTAssertEqual(answer["ok"] as? Bool, true, why, file: file, line: line)
    }

    func assertRefused(
        _ answer: [String: Any], _ code: ErrorCode, _ note: String = "",
        file: StaticString = #filePath, line: UInt = #line
    ) {
        XCTAssertEqual(answer["ok"] as? Bool, false, note, file: file, line: line)
        XCTAssertEqual(answer["error"] as? String, code.rawValue, note, file: file, line: line)
        let detail = answer["detail"] as? String ?? ""
        XCTAssertFalse(detail.isEmpty, "a refusal says why", file: file, line: line)
        XCTAssertEqual(
            Set(answer.keys), ["id", "ok", "error", "detail"], note, file: file, line: line
        )
    }

    /// Whether a decoded JSON value was written as `true` or `false`, not as a number.
    func isBoolean(_ value: Any?) -> Bool {
        guard let value else { return false }
        return CFGetTypeID(value as CFTypeRef) == CFBooleanGetTypeID()
    }

    /// Takes a screenshot and gives its frame id. Small by default, so the tests stay quick.
    func shoot(
        display: Int? = nil, maxPx: Int = 320, file: StaticString = #filePath, line: UInt = #line
    ) -> String {
        var arguments: [String: Any] = ["max_px": maxPx]
        if let display { arguments["display"] = display }
        let answer = ask("screenshot", arguments)
        assertOK(answer, file: file, line: line)
        return answer["frame_id"] as? String ?? ""
    }

    /// Reads a tree of these nodes, so their refs are the ones the helper holds.
    @discardableResult
    func readTree(
        _ nodes: [RawNode], app: String? = nil, file: StaticString = #filePath, line: UInt = #line
    ) -> [String: Any] {
        system.snapshot = AXSnapshot(window: "Untitled", nodes: nodes, truncated: false)
        let answer = ask("ax", app.map { ["app": $0] } ?? [:])
        assertOK(answer, file: file, line: line)
        return answer
    }

    func nodes(_ answer: [String: Any]) -> [[String: Any]] {
        answer["nodes"] as? [[String: Any]] ?? []
    }

    /// A text field for the tests of an action on an element.
    static let field = RawNode(
        depth: 1, role: "AXTextField", title: "Name", value: "old",
        frame: ScreenRect(x: 100, y: 100, width: 200, height: 40), element: 31
    )

    /// Reads a one-field tree of the frontmost application and takes a small picture of the
    /// main display, then gives one well-formed request of every kind of action but `focus_app`.
    func everyKindOfAction() -> [(kind: String, arguments: [String: Any])] {
        readTree([Self.field])
        system.elementFrames[Self.field.element] = ScreenRect(x: 100, y: 100, width: 200, height: 40)
        let frame = shoot()
        system.forgetCalls()
        return [
            ("click", ["frame_id": frame, "x": 160, "y": 90]),
            ("double_click", ["ref": "a1"]),
            ("right_click", ["frame_id": frame, "x": 160, "y": 90]),
            ("drag", ["frame_id": frame, "x": 10, "y": 10, "to_x": 160, "to_y": 90]),
            ("scroll", ["frame_id": frame, "x": 160, "y": 90, "dx": 0, "dy": 3]),
            ("type", ["text": "hello"]),
            ("key", ["keys": "enter"]),
            ("set_value", ["ref": "a1", "text": "hello"]),
        ]
    }
}
