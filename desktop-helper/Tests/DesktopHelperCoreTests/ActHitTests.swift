import Foundation
import XCTest
@testable import DesktopHelperCore

/// What is on top at each point a pointer event goes to is looked at just before the event:
/// another application's window, a notification or an overlay there would take the event, so
/// nothing is posted. A click by ref must land on that element or inside it.
final class ActHitTests: HelperTestCase {
    private var frame = ""
    /// Where the picture point (160, 90) and the start of the drag, (10, 10), are on the screen.
    private let middle = ScreenPoint(x: 960, y: 540)
    private let corner = ScreenPoint(x: 60, y: 60)
    /// The centre of the field `a1`.
    private let centre = ScreenPoint(x: 200, y: 120)
    private let mailWindow = FakeSystem.Hit(pid: Fixture.mail.pid, element: 90)

    override func setUp() {
        super.setUp()
        readTree([Self.field])
        system.elementFrames[Self.field.element] = Self.field.frame
        frame = shoot()
        system.forgetCalls()
    }

    private var pixel: [String: Any] { ["frame_id": frame, "x": 160, "y": 90] }
    private var drag: [String: Any] { ["frame_id": frame, "x": 10, "y": 10, "to_x": 160, "to_y": 90] }
    private var scroll: [String: Any] { ["frame_id": frame, "x": 160, "y": 90, "dx": 0, "dy": -3] }

    /// Puts `hit` on top over a small square around `point`.
    private func cover(_ point: ScreenPoint, with hit: FakeSystem.Hit?) {
        let area = ScreenRect(x: point.x - 5, y: point.y - 5, width: 10, height: 10)
        system.covers.append(FakeSystem.Cover(area: area, hit: hit))
    }

    private var asked: [FakeSystem.Call] {
        system.calls.filter { if case .topElement = $0 { return true } else { return false } }
    }

    private func assertCovered(
        _ reply: [String: Any], _ detail: String, file: StaticString = #filePath, line: UInt = #line
    ) {
        assertRefused(reply, .pointCovered, file: file, line: line)
        XCTAssertEqual(reply["detail"] as? String, detail, file: file, line: line)
    }

    // MARK: by pixel

    func testClickOfEveryKindWhereAnotherApplicationIsOnTopIsPointCovered() {
        cover(middle, with: mailWindow)
        for kind in ["click", "double_click", "right_click"] {
            let reply = act(kind, pixel)
            assertCovered(reply, "Another application is on top at the click point, not the frontmost one.")
            let detail = reply["detail"] as? String ?? ""
            XCTAssertFalse(detail.contains("Mail") || detail.contains("TextEdit"), "no app is named")
        }
        XCTAssertEqual(asked, Array(repeating: .topElement(middle, within: nil), count: 3))
        XCTAssertEqual(system.actions, [])
    }

    func testClickOnAnyElementOfTheFrontmostApplicationIsPosted() {
        cover(middle, with: FakeSystem.Hit(pid: Fixture.textEdit.pid, element: 77))
        assertOK(act("click", pixel))
        XCTAssertEqual(system.actions, [.postClick(middle, .left, 1)])
    }

    func testWindowBesideThePointDoesNotHoldTheClickBack() {
        let left = ScreenRect(x: 0, y: 0, width: middle.x, height: 1080)
        system.covers = [FakeSystem.Cover(area: left, hit: mailWindow)]
        assertOK(act("click", pixel), "the window ends just before the point")
        XCTAssertEqual(system.actions, [.postClick(middle, .left, 1)])
    }

    func testScrollWhereAnotherApplicationIsOnTopIsPointCovered() {
        cover(middle, with: mailWindow)
        assertCovered(
            act("scroll", scroll), "Another application is on top at the scroll point, not the frontmost one."
        )
        XCTAssertEqual(asked, [.topElement(middle, within: nil)])
        XCTAssertEqual(system.actions, [])
    }

    // MARK: drag

    func testDragWhoseEndIsUnderAnotherApplicationIsRefusedBeforeTheButtonGoesDown() {
        cover(middle, with: mailWindow)
        assertCovered(
            act("drag", drag), "Another application is on top at the end of the drag, not the frontmost one."
        )
        XCTAssertEqual(asked, [.topElement(corner, within: nil), .topElement(middle, within: nil)])
        XCTAssertEqual(system.actions, [], "no part of the drag is posted")
    }

    func testDragWhoseStartIsUnderAnotherApplicationIsRefusedWithoutAskingAboutTheEnd() {
        cover(corner, with: mailWindow)
        assertCovered(
            act("drag", drag), "Another application is on top at the start of the drag, not the frontmost one."
        )
        XCTAssertEqual(asked, [.topElement(corner, within: nil)])
        XCTAssertEqual(system.actions, [])
    }

    func testDragWithBothEndsInTheFrontmostApplicationIsPosted() {
        assertOK(act("drag", drag))
        XCTAssertEqual(system.actions, [.postDrag(corner, middle)])
    }

    // MARK: by ref

    func testClickOnARefWhereAnotherElementOfTheSameApplicationIsOnTopIsPointCovered() {
        let others = [50, 32, FakeSystem.frontWindow]
        for element in others {
            system.covers = []
            cover(centre, with: FakeSystem.Hit(pid: Fixture.textEdit.pid, element: element))
            assertCovered(
                act("click", ["ref": "a1"]),
                "Another element of the frontmost application is on top of that element at the click point."
            )
        }
        XCTAssertEqual(asked, Array(repeating: .topElement(centre, within: 31), count: others.count))
        XCTAssertEqual(system.actions, [])
    }

    func testClickOnARefLandingOnAChildOfTheElementIsPosted() {
        system.parents = [50: 51, 51: 31]
        cover(centre, with: FakeSystem.Hit(pid: Fixture.textEdit.pid, element: 50))
        assertOK(act("click", ["ref": "a1"]))
        assertOK(act("double_click", ["ref": "a1"]))
        assertOK(act("right_click", ["ref": "a1"]))
        XCTAssertEqual(system.actions, [
            .postClick(centre, .left, 1), .postClick(centre, .left, 2), .postClick(centre, .right, 1),
        ])
    }

    func testClickOnARefWhereAnotherApplicationIsOnTopIsPointCovered() {
        cover(centre, with: mailWindow)
        assertCovered(
            act("right_click", ["ref": "a1"]),
            "Another application is on top at the click point, not the frontmost one."
        )
        XCTAssertEqual(system.actions, [])
    }

    // MARK: nothing known

    func testPlaceWhereNoElementIsIsPointCovered() {
        cover(middle, with: nil)
        assertCovered(act("click", pixel), "No element of any application is on top at the click point.")
        assertCovered(act("scroll", scroll), "No element of any application is on top at the scroll point.")
        assertCovered(act("drag", drag), "No element of any application is on top at the end of the drag.")
        XCTAssertEqual(system.actions, [])
    }

    func testMachineThatCannotTellWhatIsOnTopIsPointCoveredWhateverItsError() {
        let errors: [SystemError] = [
            .failed("The application did not answer."), .accessibilityMissing, .elementGone,
            .unsupported("no"), .appGone,
        ]
        let detail = "The helper could not tell what is on top at the click point, so nothing was posted."
        for error in errors {
            system.hitError = error
            assertCovered(act("click", pixel), detail)
            assertCovered(act("click", ["ref": "a1"]), detail)
        }
        system.hitError = .failed("no")
        assertCovered(
            act("drag", drag),
            "The helper could not tell what is on top at the start of the drag, so nothing was posted."
        )
        XCTAssertEqual(system.actions, [])
    }

    // MARK: what is not looked at

    func testTextKeysAndValuesAreNotHeldToWhatIsOnTop() {
        system.covers = [FakeSystem.Cover(area: ScreenRect(x: -1e5, y: -1e5, width: 2e5, height: 2e5), hit: nil)]
        system.hitError = .failed("no")
        assertOK(act("type", ["text": "hi"]))
        assertOK(act("key", ["keys": "enter"]))
        assertOK(act("set_value", ["ref": "a1", "text": "new"]))
        XCTAssertEqual(asked, [])
        XCTAssertEqual(system.actions.count, 3)
    }
}
