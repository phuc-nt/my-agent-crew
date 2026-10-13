import Foundation
import XCTest
@testable import DesktopHelperCore

private func isActivate(_ call: FakeSystem.Call) -> Bool {
    if case .activate = call { return true }
    return false
}

/// The application an action is meant for: every kind is held to the frontmost one, and
/// `focus_app` is the one way to change which that is.
final class ActAppTests: HelperTestCase {
    private let checks: [FakeSystem.Call] = [.isLocked, .isDisplayAsleep, .hasAccessibility]

    /// Makes `app` the frontmost application the moment `trigger` says so of a call.
    private func bringForward(_ app: AppInfo?, when trigger: @escaping (FakeSystem.Call) -> Bool) {
        system.onCall = { [weak system] call in
            if trigger(call) { system?.front = app }
        }
    }

    // MARK: every kind but focus_app

    func testEveryKindButFocusAppIsAppMismatchWhenAnotherApplicationIsFrontmost() {
        XCTAssertEqual(ActKind.allCases.count, 9, "a new kind of action needs its row in these tests")
        let requests = everyKindOfAction()
        XCTAssertEqual(
            Set(requests.map { $0.kind }),
            Set(ActKind.allCases.map(\.rawValue)).subtracting(["focus_app"])
        )

        system.front = Fixture.notes
        for request in requests {
            let reply = act(request.kind, request.arguments)
            assertRefused(reply, .appMismatch, request.kind)
            XCTAssertEqual(
                reply["detail"] as? String, "The frontmost application is not the one named in `app`."
            )
        }
        XCTAssertEqual(system.touches, [], "nothing is posted, set or read in another application")

        system.front = Fixture.textEdit
        for request in requests {
            assertOK(act(request.kind, request.arguments), request.kind)
        }
        XCTAssertEqual(system.actions.count, 8)
    }

    func testEveryKindButFocusAppIsAppMismatchWhenNoApplicationIsFrontmost() {
        let requests = everyKindOfAction()
        system.front = nil
        for request in requests {
            assertRefused(act(request.kind, request.arguments), .appMismatch, request.kind)
        }
        XCTAssertEqual(system.touches, [])
    }

    func testApplicationIsMatchedByNameOrBundleIDWhateverTheCase() {
        let same = ["TextEdit", "textedit", "TEXTEDIT", "com.apple.TextEdit", "COM.APPLE.TEXTEDIT"]
        for name in same {
            assertOK(act("key", ["keys": "enter"], app: name), name)
        }
        XCTAssertEqual(system.actions.count, same.count)

        let other = [
            "Text", "TextEdit ", " TextEdit", "TextEdit.app", "com.apple", "com.apple.TextEdit.helper",
            "Notes", "com.apple.Notes", "4242", "*", ".*", "TextEdít",
        ]
        for name in other {
            assertRefused(act("key", ["keys": "enter"], app: name), .appMismatch, "<\(name)>")
        }
        XCTAssertEqual(system.actions.count, same.count)
    }

    func testApplicationThatIsNotRunningIsStillAppMismatchForAnActionThatIsNotFocusApp() {
        assertRefused(act("key", ["keys": "enter"], app: "Xcode"), .appMismatch)
        assertRefused(act("type", ["text": "hi"], app: "Xcode"), .appMismatch)
        let once: [FakeSystem.Call] = checks + [.frontmostApp]
        XCTAssertEqual(system.calls, once + once, "the list of running applications is not read")
    }

    func testAnswerNamesTheApplicationThatIsFrontmostAfterTheAction() {
        bringForward(Fixture.notes) {
            if case .postKey = $0 { return true }
            return false
        }
        let reply = act("key", ["keys": "cmd+tab"])
        assertOK(reply)
        let frontmost = reply["frontmost"] as? [String: Any] ?? [:]
        XCTAssertEqual(frontmost["app"] as? String, "Notes")
        XCTAssertEqual(frontmost["bundle_id"] as? String, "com.apple.Notes")
        XCTAssertEqual(frontmost["pid"] as? Int, 500)
    }

    func testAnswerHasANullFrontmostWhenNoApplicationIsLeftInFront() {
        bringForward(nil) {
            if case .postKey = $0 { return true }
            return false
        }
        let reply = act("key", ["keys": "cmd+w"])
        assertOK(reply)
        XCTAssertEqual(Set(reply.keys), ["id", "ok", "effect", "frontmost"])
        XCTAssertTrue(reply["frontmost"] is NSNull)
    }

    // MARK: focus_app

    func testFocusAppOfAnApplicationThatIsNotRunningIsAppNotRunning() {
        let reply = act("focus_app", app: "Xcode")
        assertRefused(reply, .appNotRunning)
        XCTAssertEqual(reply["detail"] as? String, "No running application is named that.")
        let expected: [FakeSystem.Call] = checks + [.frontmostApp, .runningApps]
        XCTAssertEqual(system.calls, expected)
    }

    func testFocusAppOfTheFrontmostApplicationSaysFocusedAndActivatesNothing() {
        let reply = act("focus_app")
        assertOK(reply)
        XCTAssertEqual(Set(reply.keys), ["id", "ok", "effect", "frontmost"])
        XCTAssertEqual(reply["effect"] as? String, "focused")
        XCTAssertEqual((reply["frontmost"] as? [String: Any])?["app"] as? String, "TextEdit")
        let expected: [FakeSystem.Call] = checks + [.frontmostApp, .runningApps, .frontmostApp]
        XCTAssertEqual(system.calls, expected)
    }

    func testFocusAppIsOKAsSoonAsTheApplicationIsFrontmost() {
        bringForward(Fixture.notes, when: isActivate)
        let reply = act("focus_app", app: "Notes")
        assertOK(reply)
        XCTAssertEqual(reply["effect"] as? String, "focused")
        XCTAssertEqual((reply["frontmost"] as? [String: Any])?["pid"] as? Int, 500)
        let expected: [FakeSystem.Call] = checks + [
            .frontmostApp, .runningApps, .activate(pid: 500), .now, .frontmostApp, .frontmostApp,
        ]
        XCTAssertEqual(system.calls, expected)
    }

    func testFocusAppWaitsUntilTheApplicationIsFrontmost() {
        var pauses = 0
        bringForward(Fixture.notes) { call in
            guard case .pause = call else { return false }
            pauses += 1
            return pauses == 3
        }
        let reply = act("focus_app", app: "Notes")
        assertOK(reply)
        XCTAssertEqual((reply["frontmost"] as? [String: Any])?["app"] as? String, "Notes")
        let look: [FakeSystem.Call] = [.frontmostApp, .now, .pause(0.05)]
        var expected: [FakeSystem.Call] = checks
        expected += [.frontmostApp, .runningApps, .activate(pid: 500), .now]
        expected += look + look + look
        expected += [.frontmostApp, .frontmostApp]
        XCTAssertEqual(system.calls, expected)
    }

    func testFocusAppThatDoesNotComeToTheFrontWithinTwoSecondsIsAppMismatch() {
        let reply = act("focus_app", app: "Notes")
        assertRefused(reply, .appMismatch)
        XCTAssertEqual(
            reply["detail"] as? String, "The application did not come to the front within 2 seconds."
        )
        XCTAssertEqual(system.actions, [.activate(pid: 500)], "it is asked forward once, not again")

        let waited = system.clock - 10_000
        XCTAssertGreaterThanOrEqual(waited, 2)
        XCTAssertLessThan(waited, 2.1)
        let pauses = system.calls.filter {
            if case .pause = $0 { return true }
            return false
        }
        XCTAssertFalse(pauses.isEmpty)
        XCTAssertTrue(pauses.allSatisfy { $0 == .pause(0.05) })
        XCTAssertEqual(Limits.focusWait, 2)
    }

    func testFocusAppThatComesToTheFrontJustBeforeTheTwoSecondsIsOK() {
        bringForward(Fixture.notes) { [weak system] call in
            guard case .pause = call, let system else { return false }
            return system.clock - 10_000 > 1.9
        }
        assertOK(act("focus_app", app: "Notes"))
    }

    func testFocusAppFindsTheApplicationByBundleIDWhateverTheCase() {
        bringForward(Fixture.notes, when: isActivate)
        assertOK(act("focus_app", app: "COM.APPLE.NOTES"))
        XCTAssertEqual(system.actions, [.activate(pid: 500)])
    }

    func testFocusAppBringsAHiddenApplicationForward() {
        bringForward(Fixture.safari, when: isActivate)
        let reply = act("focus_app", app: "Safari")
        assertOK(reply)
        XCTAssertEqual(system.actions, [.activate(pid: 300)])
        XCTAssertEqual((reply["frontmost"] as? [String: Any])?["app"] as? String, "Safari")
    }

    func testFocusAppOfTwoProcessesWithTheNameTakesTheFrontmostOneElseTheOldest() {
        let newer = AppInfo(name: "Notes", bundleID: "example.notes.two", pid: 900)
        let other = AppInfo(name: "notes", bundleID: "example.notes.three", pid: 700)
        system.apps = [newer, Fixture.textEdit, other, Fixture.notes]
        bringForward(Fixture.notes, when: isActivate)
        assertOK(act("focus_app", app: "Notes"))
        XCTAssertEqual(system.actions, [.activate(pid: 500)])

        reset()
        system.apps = [newer, Fixture.textEdit, other, Fixture.notes]
        system.front = newer
        let reply = act("focus_app", app: "Notes")
        assertOK(reply)
        XCTAssertEqual(system.actions, [], "the one in front is already the one meant")
        XCTAssertEqual((reply["frontmost"] as? [String: Any])?["pid"] as? Int, 900)
    }

    func testFocusAppWithNoApplicationInFrontStillBringsItsOwnForward() {
        system.front = nil
        bringForward(Fixture.notes, when: isActivate)
        assertOK(act("focus_app", app: "Notes"))
        XCTAssertEqual(system.actions, [.activate(pid: 500)])
    }

    func testFocusAppIsHeldToThePreconditionsLikeEveryAction() {
        system.locked = true
        system.asleep = true
        system.accessibility = false
        assertRefused(act("focus_app", app: "Notes"), .locked)
        system.locked = false
        assertRefused(act("focus_app", app: "Notes"), .displayAsleep)
        system.asleep = false
        assertRefused(act("focus_app", app: "Notes"), .permissionMissingAccessibility)
        XCTAssertEqual(system.touches, [])
        XCTAssertFalse(system.calls.contains(.runningApps))
    }

    func testFocusAppDoesNotLookAtSecureInputOrAtAnyFrame() {
        system.secureInput = true
        system.focusedSecure = true
        bringForward(Fixture.notes, when: isActivate)
        assertOK(act("focus_app", ["frame_id": "not a frame"], app: "Notes"))
        XCTAssertFalse(system.calls.contains(.isSecureInputOn))
        XCTAssertFalse(system.calls.contains(.focusedElementIsSecure(pid: 500)))
        XCTAssertEqual(system.actions, [.activate(pid: 500)])
    }

    func testApplicationThatQuitWhileItWasAskedForwardIsAppNotRunning() {
        system.activateError = .appGone
        let reply = act("focus_app", app: "Notes")
        assertRefused(reply, .appNotRunning)
        XCTAssertEqual(reply["detail"] as? String, "That application is no longer running.")
        XCTAssertFalse(system.calls.contains(.pause(0.05)), "there is nothing to wait for")
    }

    func testActivationTheSystemRefusesIsAnsweredWithItsCode() {
        system.activateError = .failed("The application could not be activated.")
        let failed = act("focus_app", app: "Notes")
        assertRefused(failed, .internalError)
        XCTAssertEqual(failed["detail"] as? String, "The application could not be activated.")

        system.activateError = .accessibilityMissing
        assertRefused(act("focus_app", app: "Notes"), .permissionMissingAccessibility)
    }

    func testFocusAppThenAnActionInThatApplication() {
        bringForward(Fixture.notes, when: isActivate)
        assertRefused(act("key", ["keys": "cmd+n"], app: "Notes"), .appMismatch)
        assertOK(act("focus_app", app: "Notes"))
        assertOK(act("key", ["keys": "cmd+n"], app: "Notes"))
        assertRefused(act("key", ["keys": "cmd+n"]), .appMismatch, "TextEdit is behind now")
        XCTAssertEqual(
            system.actions, [.activate(pid: 500), .postKey(code: 45, modifiers: [.command])]
        )
    }
}
