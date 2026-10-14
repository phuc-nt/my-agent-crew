import Foundation
import XCTest
@testable import DesktopHelperCore

/// The order of the checks of `act`: the shape, the preconditions, blocked keys, the application,
/// a web browser in front, secure input, the frame and the ref (with a point outside the
/// picture), then what is on top at the points of a pointer event. One test for each two that
/// stand next to each other, each showing which of them is the answer when both would fail.
final class ActOrderTests: HelperTestCase {
    /// A frame id of the right form that the helper never gave out.
    private let stale = "0123456789abcdef-320x180-1"
    /// A site saved as an app of its own, named like the application the requests name.
    private let siteApp = AppInfo(
        name: "TextEdit", bundleID: "com.google.Chrome.app.textedit", pid: 4242
    )
    /// Another application's window over the whole of both displays.
    private let everywhere = FakeSystem.Cover(
        area: ScreenRect(x: -10_000, y: -10_000, width: 20_000, height: 20_000),
        hit: FakeSystem.Hit(pid: Fixture.mail.pid, element: 90)
    )

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
            ["kind": "type", "app": "TextEdit", "text": "echo ok\u{0F}"],
            ["kind": "set_value", "app": "TextEdit", "ref": "a1", "outline": Self.noOutline, "text": "\u{7F}"],
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

    func testBlockedKeysAreAnsweredBeforeABrowserInFront() {
        system.front = Fixture.safari
        assertRefused(act("key", ["keys": "cmd+ctrl+q"], app: "Safari"), .blockedKeys)
        XCTAssertFalse(system.calls.contains(.frontmostApp), "the application is not looked at")
        assertRefused(act("key", ["keys": "cmd+s"], app: "Safari"), .browserApp)
        XCTAssertEqual(system.actions, [])
    }

    func testApplicationIsAnsweredBeforeABrowserInFront() {
        system.front = Fixture.safari
        assertRefused(act("key", ["keys": "cmd+s"]), .appMismatch, "TextEdit is not in front")
        assertRefused(act("key", ["keys": "cmd+s"], app: "Safari"), .browserApp)
        XCTAssertEqual(system.actions, [])
    }

    func testBrowserInFrontIsAnsweredBeforeSecureInput() {
        let writes: [(String, [String: Any])] = [
            ("type", ["text": "hello"]), ("key", ["keys": "enter"]),
            ("set_value", ["ref": "a1", "text": "hello"]),
        ]
        system.secureInput = true
        system.focusedSecure = true
        system.front = siteApp
        for (kind, arguments) in writes {
            assertRefused(act(kind, arguments), .browserApp, kind)
        }
        XCTAssertFalse(system.calls.contains(.isSecureInputOn), "secure input is not looked at")
        XCTAssertEqual(system.touches, [])

        system.front = Fixture.textEdit
        for (kind, arguments) in writes {
            assertRefused(act(kind, arguments), .secureInput, kind)
        }
        XCTAssertEqual(system.actions, [])
    }

    func testBrowserInFrontIsAnsweredBeforeTheFrameTheRefAndWhatIsOnTop() {
        readTree([Self.field])
        system.elementFrames[31] = Self.field.frame
        let frame = shoot()
        system.covers = [everywhere]
        let requests: [(String, [String: Any], ErrorCode)] = [
            ("click", ["frame_id": stale, "x": 1, "y": 1], .frameMismatch),
            ("click", ["ref": "a9"], .refUnknown),
            ("scroll", ["frame_id": frame, "x": 999, "y": 1, "dx": 0, "dy": 1], .badRequest),
            ("drag", ["frame_id": frame, "x": 1, "y": 1, "to_x": 2, "to_y": 2], .pointCovered),
            ("right_click", ["ref": "a1"], .pointCovered),
        ]
        system.front = siteApp
        system.forgetCalls()
        for (kind, arguments, _) in requests {
            assertRefused(act(kind, arguments), .browserApp, kind)
        }
        XCTAssertEqual(system.touches, [], "neither the frame, the element nor the point is looked at")
        XCTAssertFalse(system.calls.contains(.now))

        system.front = Fixture.textEdit
        for (kind, arguments, next) in requests {
            assertRefused(act(kind, arguments), next, kind)
        }
        XCTAssertEqual(system.actions, [])
    }

    func testFrameRefAndPictureAreAnsweredBeforeWhatIsOnTop() {
        readTree([Self.field])
        let frame = shoot()
        system.covers = [everywhere]
        system.forgetCalls()
        assertRefused(act("click", ["frame_id": stale, "x": 1, "y": 1]), .frameMismatch)
        assertRefused(act("click", ["frame_id": frame, "x": 5000, "y": 1]), .badRequest)
        assertRefused(act("double_click", ["ref": "a9"]), .refUnknown)
        assertRefused(act("double_click", ["ref": "a1"]), .badRequest, "the element has no frame")
        assertRefused(
            act("drag", ["frame_id": frame, "x": 1, "y": 1, "to_x": 1, "to_y": 900]), .badRequest
        )
        XCTAssertFalse(
            system.calls.contains { if case .topElement = $0 { return true } else { return false } },
            "what is on top is not looked at"
        )

        system.elementFrames[31] = Self.field.frame
        assertRefused(act("double_click", ["ref": "a1"]), .pointCovered)
        assertRefused(act("click", ["frame_id": frame, "x": 1, "y": 1]), .pointCovered)
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
        system.front = siteApp
        assertRefused(act("key", allowed), .browserApp)
        system.front = Fixture.textEdit
        assertRefused(act("key", allowed), .secureInput)
        system.secureInput = false
        assertRefused(act("key", allowed), .frameMismatch)
        XCTAssertEqual(system.actions, [], "nothing is posted before every check passed")

        assertOK(act("key", ["keys": "cmd+s", "frame_id": shoot()]))
        XCTAssertEqual(system.actions, [.postKey(code: 1, modifiers: [.command])])
    }

    func testPointerChecksFailOneAfterAnotherInTheContractsOrder() {
        let frame = shoot()
        system.clock += 301
        system.locked = true
        system.asleep = true
        system.accessibility = false
        system.front = Fixture.notes
        system.covers = [everywhere]
        let click: [String: Any] = ["frame_id": frame, "x": 160, "y": 90]

        assertRefused(act("click", click), .locked)
        system.locked = false
        assertRefused(act("click", click), .displayAsleep)
        system.asleep = false
        assertRefused(act("click", click), .permissionMissingAccessibility)
        system.accessibility = true
        assertRefused(act("click", click), .appMismatch)
        system.front = siteApp
        assertRefused(act("click", click), .browserApp)
        system.front = Fixture.textEdit
        assertRefused(act("click", click), .frameMismatch)
        XCTAssertEqual(ask("screenshot", ["max_px": 320, "since": frame])["frame_id"] as? String, frame)
        assertRefused(act("click", click), .pointCovered)
        XCTAssertEqual(system.actions, [], "nothing is posted before every check passed")

        system.covers = []
        assertOK(act("click", click))
        XCTAssertEqual(system.actions, [.postClick(ScreenPoint(x: 960, y: 540), .left, 1)])
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
        system.elementFrames[31] = Self.field.frame
        let frame = shoot()
        let centre = ScreenPoint(x: 960, y: 540)
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
            [.now, .topElement(centre, within: nil), .postClick(centre, .left, 1), .frontmostApp]
        )
        let field = ScreenPoint(x: 200, y: 120)
        assertAsks(
            "right_click", ["ref": "a1"],
            [.elementFrame(31), .topElement(field, within: 31), .postClick(field, .right, 1), .frontmostApp]
        )
        let corner = ScreenPoint(x: 60, y: 60)
        assertAsks(
            "drag", ["frame_id": frame, "x": 10, "y": 10, "to_x": 160, "to_y": 90],
            [
                .now, .topElement(corner, within: nil), .topElement(centre, within: nil),
                .postDrag(corner, centre), .frontmostApp,
            ]
        )
        assertAsks(
            "scroll", ["frame_id": frame, "x": 160, "y": 90, "dx": 0, "dy": 3],
            [.now, .topElement(centre, within: nil), .postScroll(centre, dx: 0, dy: 3), .frontmostApp]
        )
    }
}
