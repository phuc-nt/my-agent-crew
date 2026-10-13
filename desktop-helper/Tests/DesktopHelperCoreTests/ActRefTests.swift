import Foundation
import XCTest
@testable import DesktopHelperCore

/// `act` on an element of the last `ax` answer.
final class ActRefTests: HelperTestCase {
    private static let password = RawNode(
        depth: 1, role: "AXSecureTextField", title: "Password",
        frame: ScreenRect(x: 100, y: 200, width: 200, height: 40), element: 32
    )
    private static let button = RawNode(
        depth: 1, role: "AXButton", title: "Save",
        frame: ScreenRect(x: 400, y: 300, width: 80, height: 20), element: 33
    )

    /// A form of a field (`a1`), a password (`a2`) and a button (`a3`), each where its tree said.
    private func readForm() {
        readTree([Self.field, Self.password, Self.button])
        system.elementFrames = [
            31: ScreenRect(x: 100, y: 100, width: 200, height: 40),
            32: ScreenRect(x: 100, y: 200, width: 200, height: 40),
            33: ScreenRect(x: 400, y: 300, width: 80, height: 20),
        ]
        system.forgetCalls()
    }

    private let checks: [FakeSystem.Call] = [
        .isLocked, .isDisplayAsleep, .hasAccessibility, .frontmostApp,
    ]

    // MARK: click

    func testClickOnARefGoesToTheCentreOfTheElement() {
        readForm()
        let reply = act("click", ["ref": "a3"])
        assertOK(reply)
        XCTAssertEqual(reply["effect"] as? String, "posted")
        let rest: [FakeSystem.Call] = [
            .elementFrame(33), .postClick(ScreenPoint(x: 440, y: 310), .left, 1), .frontmostApp,
        ]
        XCTAssertEqual(system.calls, checks + rest)
    }

    func testClickOnARefUsesWhereTheElementIsNowNotWhereTheTreeSaidItWas() {
        readForm()
        system.elementFrames[33] = ScreenRect(x: 1000, y: 700, width: 81, height: 21)
        assertOK(act("click", ["ref": "a3"]))
        XCTAssertEqual(system.actions, [.postClick(ScreenPoint(x: 1040.5, y: 710.5), .left, 1)])
    }

    func testDoubleClickAndRightClickOnARef() {
        readForm()
        assertOK(act("double_click", ["ref": "a1"]))
        assertOK(act("right_click", ["ref": "a1"]))
        let centre = ScreenPoint(x: 200, y: 120)
        XCTAssertEqual(system.actions, [.postClick(centre, .left, 2), .postClick(centre, .right, 1)])
    }

    func testClickOnARefNeedsNoPictureAndAsksForNoTime() {
        readForm()
        assertOK(act("click", ["ref": "a1"]))
        XCTAssertFalse(system.calls.contains(.now))
        XCTAssertFalse(system.calls.contains(.hasScreenRecording))
    }

    func testElementWithNoFrameCannotBeClicked() {
        readForm()
        system.elementFrames[33] = nil
        let reply = act("click", ["ref": "a3"])
        assertRefused(reply, .badRequest)
        XCTAssertEqual(reply["detail"] as? String, "That element has no frame to click.")
        XCTAssertEqual(system.actions, [])
    }

    func testElementThatNoLongerAnswersIsRefUnknown() {
        readForm()
        system.frameError = .elementGone
        let reply = act("click", ["ref": "a3"])
        assertRefused(reply, .refUnknown)
        XCTAssertEqual(
            reply["detail"] as? String, "That element no longer answers; read the tree again."
        )
        XCTAssertEqual(system.actions, [])

        system.frameError = nil
        system.setValueError = .elementGone
        assertRefused(act("set_value", ["ref": "a1", "text": "x"]), .refUnknown)
    }

    // MARK: which refs count

    func testRefIsUnknownBeforeAnyTreeWasRead() {
        assertRefused(act("click", ["ref": "a1"]), .refUnknown)
        assertRefused(act("set_value", ["ref": "a1", "text": "x"]), .refUnknown)
        XCTAssertEqual(system.touches, [])
    }

    func testRefThatIsNotOneOfTheLastAnswerIsRefUnknown() {
        readForm()
        for ref in ["a4", "a0", "a-1", "A1", "", " a1", "a1 ", "a01", "1", "b1", "a1.0", "a", "ref"] {
            assertRefused(act("click", ["ref": ref]), .refUnknown, "<\(ref)>")
            assertRefused(act("set_value", ["ref": ref, "text": "x"]), .refUnknown, "<\(ref)>")
        }
        XCTAssertEqual(system.touches, [], "an unknown ref reaches no element")
    }

    func testRefNamesTheElementOfTheNewestTree() {
        readForm()
        readTree([RawNode(depth: 0, role: "AXTextField", element: 77)])
        system.forgetCalls()
        assertOK(act("set_value", ["ref": "a1", "text": "new"]))
        assertRefused(act("set_value", ["ref": "a2", "text": "new"]), .refUnknown)
        assertRefused(act("click", ["ref": "a3"]), .refUnknown)
        XCTAssertEqual(system.actions, [.setValue(77, "new")])
    }

    func testRefOfAnotherApplicationsTreeIsUnknownWhileThatApplicationIsNotFrontmost() {
        let tree = readTree([Self.button], app: "Notes")
        XCTAssertEqual(tree["pid"] as? Int, 500)
        system.elementFrames[33] = ScreenRect(x: 400, y: 300, width: 80, height: 20)

        assertRefused(act("click", ["ref": "a1"]), .refUnknown, "TextEdit is frontmost")
        assertRefused(act("click", ["ref": "a1"], app: "Notes"), .appMismatch)
        XCTAssertEqual(system.actions, [])

        system.front = Fixture.notes
        assertOK(act("click", ["ref": "a1"], app: "Notes"))
        assertRefused(act("click", ["ref": "a1"]), .appMismatch)
        XCTAssertEqual(system.actions, [.postClick(ScreenPoint(x: 440, y: 310), .left, 1)])
    }

    func testRefOfAnApplicationThatWentToTheBackIsUnknownUntilItIsFrontmostAgain() {
        readForm()
        system.front = Fixture.notes
        assertRefused(act("click", ["ref": "a3"], app: "Notes"), .refUnknown)
        system.front = Fixture.textEdit
        assertOK(act("click", ["ref": "a3"]))
    }

    // MARK: set_value

    func testSetValueSetsTheElementsValueAndSaysSet() {
        readForm()
        let reply = act("set_value", ["ref": "a1", "text": "hello"])
        assertOK(reply)
        XCTAssertEqual(Set(reply.keys), ["id", "ok", "effect", "frontmost"])
        XCTAssertEqual(reply["effect"] as? String, "set")
        let rest: [FakeSystem.Call] = [.isSecureInputOn, .setValue(31, "hello"), .frontmostApp]
        XCTAssertEqual(system.calls, checks + rest)
    }

    func testSetValueTakesAnyTextTheLineCanCarry() {
        readForm()
        let long = String(repeating: "é", count: 5000)
        assertOK(act("set_value", ["ref": "a1", "text": long]))
        assertOK(act("set_value", ["ref": "a1", "text": ""]))
        assertOK(act("set_value", ["ref": "a1", "text": "line one\nline two\t\"quoted\""]))
        XCTAssertEqual(system.actions, [
            .setValue(31, long), .setValue(31, ""), .setValue(31, "line one\nline two\t\"quoted\""),
        ])
    }

    func testSetValueOnASecureTextFieldIsSecureInputAndNothingIsSet() {
        readForm()
        let reply = act("set_value", ["ref": "a2", "text": "hunter2"])
        assertRefused(reply, .secureInput)
        XCTAssertEqual(reply["detail"] as? String, "That element is a secure text field.")
        XCTAssertEqual(system.touches, [])
    }

    func testSecureTextFieldIsKnownByItsSubroleToo() {
        readTree([RawNode(depth: 0, role: "AXTextField", subrole: "AXSecureTextField", element: 40)])
        assertRefused(act("set_value", ["ref": "a1", "text": "x"]), .secureInput)
        XCTAssertEqual(system.actions, [])
    }

    func testSecureTextFieldCanStillBeClicked() {
        readForm()
        assertOK(act("click", ["ref": "a2"]))
        XCTAssertEqual(system.actions, [.postClick(ScreenPoint(x: 200, y: 220), .left, 1)])
    }

    func testSetValueLooksAtTheElementNamedNotAtTheOneThatHoldsTheFocus() {
        readForm()
        system.focusedSecure = true
        assertOK(act("set_value", ["ref": "a1", "text": "hello"]))
        XCTAssertFalse(system.calls.contains(.focusedElementIsSecure(pid: 4242)))
        XCTAssertEqual(system.actions, [.setValue(31, "hello")])
    }

    func testSystemThatFindsTheFieldSecureAtTheLastMomentIsSecureInput() {
        readForm()
        system.setValueError = .secureField
        assertRefused(act("set_value", ["ref": "a1", "text": "x"]), .secureInput)
    }

    func testValueThatCannotBeSetIsBadRequestWithTheSystemsWords() {
        readForm()
        system.setValueError = .unsupported("The value of that element cannot be set.")
        let reply = act("set_value", ["ref": "a3", "text": "x"])
        assertRefused(reply, .badRequest)
        XCTAssertEqual(reply["detail"] as? String, "The value of that element cannot be set.")
    }

    func testSetThatChecksItsPermissionAgainIsAnsweredWithThatCode() {
        readForm()
        system.setValueError = .accessibilityMissing
        assertRefused(act("set_value", ["ref": "a1", "text": "x"]), .permissionMissingAccessibility)
        system.setValueError = .failed("The application did not answer.")
        let reply = act("set_value", ["ref": "a1", "text": "x"])
        assertRefused(reply, .internalError)
        XCTAssertEqual(reply["detail"] as? String, "The application did not answer.")
    }

    func testRefStaysGoodForMoreThanOneAction() {
        readForm()
        assertOK(act("click", ["ref": "a1"]))
        assertOK(act("set_value", ["ref": "a1", "text": "one"]))
        assertOK(act("set_value", ["ref": "a1", "text": "two"]))
        assertOK(ask("screenshot", ["max_px": 320]), "a picture does not forget the tree")
        assertOK(ask("apps"))
        assertOK(act("click", ["ref": "a3"]))
        XCTAssertEqual(system.actions.count, 4)
    }
}
