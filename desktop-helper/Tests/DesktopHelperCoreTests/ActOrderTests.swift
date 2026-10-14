import Foundation
import XCTest
@testable import DesktopHelperCore

/// The order of the six checks of `act`: one test for each two that stand next to each other,
/// each showing which of them is the answer when both would fail.
final class ActOrderTests: HelperTestCase {
    /// A frame id of the right form that the helper never gave out.
    private let stale = "0123456789abcdef-320x180-1"

    func testShapeIsAnsweredBeforeThePreconditions() {
        system.locked = true
        system.asleep = true
        system.accessibility = false
        let malformed: [[String: Any]] = [
            [:],
            ["app": "TextEdit"],
            ["kind": 7, "app": "TextEdit"],
            ["kind": "poke", "app": "TextEdit"],
            ["kind": "Click", "app": "TextEdit", "ref": "a1"],
            ["kind": "key", "keys": "enter"],
            ["kind": "key", "keys": "enter", "app": 7],
            ["kind": "key", "keys": "enter", "app": ""],
            ["kind": "key", "app": "TextEdit"],
            ["kind": "key", "app": "TextEdit", "keys": 13],
            ["kind": "key", "app": "TextEdit", "keys": "cmd+nothing"],
            ["kind": "key", "app": "TextEdit", "keys": "enter", "frame_id": 7],
            ["kind": "type", "app": "TextEdit"],
            ["kind": "type", "app": "TextEdit", "text": 5],
            ["kind": "type", "app": "TextEdit", "text": String(repeating: "x", count: 2001)],
            ["kind": "click", "app": "TextEdit"],
            ["kind": "click", "app": "TextEdit", "x": 1, "y": 1],
            ["kind": "click", "app": "TextEdit", "frame_id": stale, "x": 1],
            ["kind": "click", "app": "TextEdit", "frame_id": stale, "y": 1],
            ["kind": "click", "app": "TextEdit", "frame_id": stale, "x": "1", "y": 1],
            ["kind": "click", "app": "TextEdit", "frame_id": stale, "x": 1, "y": true],
            ["kind": "click", "app": "TextEdit", "ref": 5],
            ["kind": "click", "app": "TextEdit", "ref": "a1"],
            ["kind": "click", "app": "TextEdit", "ref": "a1", "outline": 7],
            ["kind": "right_click", "app": "TextEdit", "ref": "a1"],
            ["kind": "click", "app": "TextEdit", "ref": "a1", "frame_id": stale, "x": 1, "y": 1],
            ["kind": "double_click", "app": "TextEdit", "frame_id": stale],
            ["kind": "right_click", "app": "TextEdit", "x": 1, "y": 1],
            ["kind": "drag", "app": "TextEdit", "frame_id": stale, "x": 1, "y": 1],
            ["kind": "drag", "app": "TextEdit", "frame_id": stale, "x": 1, "y": 1, "to_x": 2],
            ["kind": "drag", "app": "TextEdit", "x": 1, "y": 1, "to_x": 2, "to_y": 2],
            ["kind": "drag", "app": "TextEdit", "frame_id": stale, "to_x": 2, "to_y": 2],
            ["kind": "scroll", "app": "TextEdit", "frame_id": stale, "x": 1, "y": 1, "dx": 0],
            ["kind": "scroll", "app": "TextEdit", "frame_id": stale, "x": 1, "y": 1, "dy": 0],
            ["kind": "scroll", "app": "TextEdit", "frame_id": stale, "x": 1, "y": 1, "dx": 0.5, "dy": 0],
            ["kind": "scroll", "app": "TextEdit", "frame_id": stale, "x": 1, "y": 1, "dx": "1", "dy": 0],
            ["kind": "scroll", "app": "TextEdit", "x": 1, "y": 1, "dx": 0, "dy": 1],
            ["kind": "scroll", "app": "TextEdit", "frame_id": stale, "dx": 0, "dy": 1],
            ["kind": "set_value", "app": "TextEdit", "ref": "a1"],
            ["kind": "set_value", "app": "TextEdit", "text": "x"],
            ["kind": "set_value", "app": "TextEdit", "ref": 1, "text": "x"],
            ["kind": "set_value", "app": "TextEdit", "ref": "a1", "text": 1],
            ["kind": "set_value", "app": "TextEdit", "ref": "a1", "text": "x"],
            ["kind": "set_value", "app": "TextEdit", "ref": "a1", "text": "x", "outline": 7],
            ["kind": "focus_app"],
            ["kind": "focus_app", "app": ""],
            ["kind": "focus_app", "app": 7],
        ]
        for arguments in malformed {
            assertRefused(ask("act", arguments), .badRequest, "\(arguments)")
        }
        XCTAssertEqual(system.calls, [], "a request of the wrong shape asks the machine nothing")

        assertRefused(act("key", ["keys": "enter"]), .locked)
        XCTAssertEqual(system.calls, [.isLocked])
    }

    func testPreconditionsAreAnsweredBeforeBlockedKeys() {
        let blocked: [String: Any] = ["keys": "cmd+ctrl+q"]
        system.locked = true
        system.asleep = true
        system.accessibility = false
        assertRefused(act("key", blocked), .locked)
        system.locked = false
        assertRefused(act("key", blocked), .displayAsleep)
        system.asleep = false
        assertRefused(act("key", blocked), .permissionMissingAccessibility)
        system.accessibility = true

        system.forgetCalls()
        assertRefused(act("key", blocked), .blockedKeys)
        XCTAssertEqual(system.calls, [.isLocked, .isDisplayAsleep, .hasAccessibility])
    }

    func testBlockedKeysAreAnsweredBeforeTheApplication() {
        system.front = Fixture.notes
        assertRefused(act("key", ["keys": "cmd+shift+q"]), .blockedKeys)
        assertRefused(act("key", ["keys": "cmd+opt+esc"], app: "Xcode"), .blockedKeys)
        XCTAssertFalse(system.calls.contains(.frontmostApp), "the application is not looked at")

        assertRefused(act("key", ["keys": "cmd+s"]), .appMismatch)
        XCTAssertEqual(system.actions, [])
    }

    func testApplicationIsAnsweredBeforeSecureInput() {
        readTree([Self.field])
        let writes: [(String, [String: Any])] = [
            ("type", ["text": "hello"]), ("key", ["keys": "enter"]),
            ("set_value", ["ref": "a1", "text": "hello"]),
        ]
        system.secureInput = true
        system.focusedSecure = true
        system.front = Fixture.notes
        system.forgetCalls()
        for (kind, arguments) in writes {
            assertRefused(act(kind, arguments), .appMismatch, kind)
        }
        XCTAssertFalse(system.calls.contains(.isSecureInputOn), "secure input is not looked at")
        XCTAssertEqual(system.touches, [])

        system.front = Fixture.textEdit
        for (kind, arguments) in writes {
            assertRefused(act(kind, arguments), .secureInput, kind)
        }
        XCTAssertEqual(system.actions, [])
    }

    func testSecureInputIsAnsweredBeforeTheFrameAndTheRef() {
        let requests: [(String, [String: Any], ErrorCode)] = [
            ("set_value", ["ref": "a9", "text": "x"], .refUnknown),
            ("key", ["keys": "enter", "frame_id": stale], .frameMismatch),
            ("type", ["text": "x", "frame_id": stale], .frameMismatch),
        ]
        system.secureInput = true
        for (kind, arguments, _) in requests {
            assertRefused(act(kind, arguments), .secureInput, kind)
        }
        XCTAssertFalse(system.calls.contains(.now), "the frame is not looked at")

        system.secureInput = false
        for (kind, arguments, next) in requests {
            assertRefused(act(kind, arguments), next, kind)
        }
        XCTAssertEqual(system.actions, [])
    }

    func testSecureFieldIsAnsweredBeforeTheFrame() {
        let password = RawNode(depth: 1, role: "AXSecureTextField", title: "Password", element: 32)
        readTree([Self.field, password])
        assertRefused(
            act("set_value", ["ref": "a2", "text": "x", "frame_id": stale]), .secureInput
        )
        assertRefused(
            act("set_value", ["ref": "a1", "text": "x", "frame_id": stale]), .frameMismatch
        )

        system.focusedSecure = true
        assertRefused(act("type", ["text": "x", "frame_id": stale]), .secureInput)
        system.focusedSecure = false
        assertRefused(act("type", ["text": "x", "frame_id": stale]), .frameMismatch)
        XCTAssertEqual(system.actions, [])
    }

    func testFrameIsAnsweredBeforeThePointOutsideThePicture() {
        assertRefused(act("click", ["frame_id": stale, "x": 5000, "y": 5000]), .frameMismatch)
        let frame = shoot()
        assertRefused(act("click", ["frame_id": frame, "x": 5000, "y": 5000]), .badRequest)
        XCTAssertEqual(system.actions, [])

        assertOK(act("click", ["frame_id": frame, "x": 160, "y": 90]))
        XCTAssertEqual(system.actions, [.postClick(ScreenPoint(x: 960, y: 540), .left, 1)])
    }

    func testRefIsAnsweredBeforeTheElementWithNoFrame() {
        readTree([Self.field])
        assertRefused(act("click", ["ref": "a2"]), .refUnknown)
        assertRefused(act("click", ["ref": "a1"]), .badRequest)
        XCTAssertEqual(system.actions, [])
    }

    func testChecksFailOneAfterAnotherInTheContractsOrder() {
        system.locked = true
        system.asleep = true
        system.accessibility = false
        system.front = Fixture.notes
        system.secureInput = true

        assertRefused(act("key", ["keys": "cmd+nothing", "frame_id": stale]), .badRequest)
        XCTAssertEqual(system.calls, [])

        let blocked: [String: Any] = ["keys": "cmd+ctrl+q", "frame_id": stale]
        assertRefused(act("key", blocked), .locked)
        system.locked = false
        assertRefused(act("key", blocked), .displayAsleep)
        system.asleep = false
        assertRefused(act("key", blocked), .permissionMissingAccessibility)
        system.accessibility = true
        assertRefused(act("key", blocked), .blockedKeys)

        let allowed: [String: Any] = ["keys": "cmd+s", "frame_id": stale]
        assertRefused(act("key", allowed), .appMismatch)
        system.front = Fixture.textEdit
        assertRefused(act("key", allowed), .secureInput)
        system.secureInput = false
        assertRefused(act("key", allowed), .frameMismatch)
        XCTAssertEqual(system.actions, [], "nothing is posted before all six checks passed")

        assertOK(act("key", ["keys": "cmd+s", "frame_id": shoot()]))
        XCTAssertEqual(system.actions, [.postKey(code: 1, modifiers: [.command])])
    }

    /// Does one action and holds what it asked of the machine against the checks every action
    /// makes, followed by `rest`.
    private func assertAsks(
        _ kind: String, _ arguments: [String: Any], _ rest: [FakeSystem.Call],
        file: StaticString = #filePath, line: UInt = #line
    ) {
        let checks: [FakeSystem.Call] = [.isLocked, .isDisplayAsleep, .hasAccessibility, .frontmostApp]
        system.forgetCalls()
        assertOK(act(kind, arguments), kind, file: file, line: line)
        XCTAssertEqual(system.calls, checks + rest, kind, file: file, line: line)
    }

    func testEveryCheckIsMadeOnceAndThenTheActionIsDoneOnce() {
        readTree([Self.field])
        let frame = shoot()
        assertAsks(
            "key", ["keys": "enter"],
            [.isSecureInputOn, .postKey(code: 36, modifiers: []), .frontmostApp]
        )
        assertAsks(
            "type", ["text": "hi"],
            [.isSecureInputOn, .focusedElementIsSecure(pid: 4242), .postText("hi"), .frontmostApp]
        )
        assertAsks(
            "set_value", ["ref": "a1", "text": "new"],
            [.isSecureInputOn, .setValue(31, "new"), .frontmostApp]
        )
        assertAsks(
            "click", ["frame_id": frame, "x": 160, "y": 90],
            [.now, .postClick(ScreenPoint(x: 960, y: 540), .left, 1), .frontmostApp]
        )
    }
}
