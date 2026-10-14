import Foundation
import XCTest
@testable import DesktopHelperCore

/// `act` at a point of a picture: which frame ids count, and where a pixel lands on the screen.
final class ActPointerTests: HelperTestCase {
    @discardableResult
    private func click(_ frame: String, _ x: Double, _ y: Double, kind: String = "click")
        -> [String: Any] {
        act(kind, ["frame_id": frame, "x": x, "y": y])
    }

    private var clicked: [ScreenPoint] {
        system.actions.compactMap {
            if case .postClick(let point, _, _) = $0 { return point }
            return nil
        }
    }

    // MARK: pixel to point

    func testPixelOfAScaledPictureLandsOnADisplayWhoseOriginIsNotZero() {
        let frame = shoot(display: 2, maxPx: 1456)
        XCTAssertTrue(frame.hasSuffix("-1456x819-2"), frame)
        assertOK(click(frame, 728, 409.5))
        assertOK(click(frame, 0, 0))
        assertOK(click(frame, 91, 91))
        XCTAssertEqual(clicked, [
            ScreenPoint(x: 3200, y: 520), ScreenPoint(x: 1920, y: -200), ScreenPoint(x: 2080, y: -40),
        ])
    }

    func testPixelOfAPictureOfARetinaDisplayIsReadInPointsNotInTheDisplaysOwnPixels() {
        let frame = shoot(maxPx: 1456)
        assertOK(click(frame, 728, 409.5))
        assertOK(click(frame, 1455, 818))
        XCTAssertEqual(clicked.first, ScreenPoint(x: 960, y: 540))
        guard clicked.count == 2, let corner = clicked.last else {
            return XCTFail("two clicks were expected, got \(clicked.count)")
        }
        XCTAssertEqual(corner.x, 1455.0 * 1920 / 1456, accuracy: 1e-9)
        XCTAssertEqual(corner.y, 818.0 * 1080 / 819, accuracy: 1e-9)
        XCTAssertLessThan(corner.x, 1920)
        XCTAssertLessThan(corner.y, 1080)
    }

    func testPixelOfASmallPictureIsScaledUpToItsOwnDisplay() {
        let main = shoot()
        system.pixel = 0x41
        let side = shoot(display: 2)
        XCTAssertTrue(main.hasSuffix("-320x180-1"), main)
        XCTAssertTrue(side.hasSuffix("-320x180-2"), side)
        assertOK(click(main, 160, 90))
        assertOK(click(side, 160, 90))
        assertOK(click(side, 1, 1))
        assertOK(click(main, 0.5, 0.5))
        XCTAssertEqual(clicked, [
            ScreenPoint(x: 960, y: 540), ScreenPoint(x: 3200, y: 520),
            ScreenPoint(x: 1928, y: -192), ScreenPoint(x: 3, y: 3),
        ])
    }

    func testPointIsReadAgainstThePictureTheSystemGaveBack() {
        system.captured = RawImage(
            width: 100, height: 50, rgba: Data(repeating: 9, count: 100 * 50 * 4)
        )
        let frame = shoot()
        assertOK(click(frame, 50, 25))
        assertRefused(click(frame, 100, 25), .badRequest)
        assertRefused(click(frame, 50, 50), .badRequest)
        XCTAssertEqual(clicked, [ScreenPoint(x: 960, y: 540)])
    }

    func testPlaceOfTheDisplayIsTheOneItHadWhenThePictureWasTaken() {
        let frame = shoot(display: 2)
        system.displayList = [
            Fixture.main,
            DisplayInfo(
                id: 2, bounds: ScreenRect(x: -2560, y: 0, width: 2560, height: 1440), scale: 1,
                isMain: false
            ),
        ]
        system.forgetCalls()
        assertOK(click(frame, 160, 90))
        XCTAssertEqual(clicked, [ScreenPoint(x: 3200, y: 520)])
        XCTAssertFalse(system.calls.contains(.displays), "an action does not list the displays again")
    }

    // MARK: kinds

    func testDoubleClickAndRightClick() {
        let frame = shoot()
        assertOK(click(frame, 160, 90, kind: "double_click"))
        assertOK(click(frame, 160, 90, kind: "right_click"))
        assertOK(click(frame, 160, 90))
        let point = ScreenPoint(x: 960, y: 540)
        XCTAssertEqual(system.actions, [
            .postClick(point, .left, 2), .postClick(point, .right, 1), .postClick(point, .left, 1),
        ])
    }

    func testAnswerNamesTheEffectAndTheFrontmostApplication() {
        let frame = shoot()
        system.forgetCalls()
        let reply = click(frame, 160, 90)
        assertOK(reply)
        XCTAssertEqual(Set(reply.keys), ["id", "ok", "effect", "frontmost"])
        XCTAssertEqual(reply["effect"] as? String, "posted")
        let frontmost = reply["frontmost"] as? [String: Any] ?? [:]
        XCTAssertEqual(Set(frontmost.keys), ["app", "bundle_id", "pid"])
        XCTAssertEqual(frontmost["app"] as? String, "TextEdit")
        XCTAssertEqual(frontmost["bundle_id"] as? String, "com.apple.TextEdit")
        XCTAssertEqual(frontmost["pid"] as? Int, 4242)
        XCTAssertEqual(system.calls, [
            .isLocked, .isDisplayAsleep, .hasAccessibility, .frontmostApp, .now,
            .topElement(ScreenPoint(x: 960, y: 540), within: nil),
            .postClick(ScreenPoint(x: 960, y: 540), .left, 1), .frontmostApp,
        ])
    }

    func testActLineAsItIsWritten() {
        let frame = shoot()
        let request = #"{"id":"12","cmd":"act","kind":"click","app":"textedit","frame_id":"\#(frame)","x":1,"y":2}"#
        XCTAssertEqual(
            dispatcher.respond(to: Data(request.utf8)),
            #"{"id":"12","ok":true,"effect":"posted","#
                + #""frontmost":{"app":"TextEdit","bundle_id":"com.apple.TextEdit","pid":4242}}"#
        )
    }

    func testDragPressesAtTheFirstPointAndReleasesAtTheSecond() {
        let frame = shoot(display: 2)
        let reply = act("drag", ["frame_id": frame, "x": 0, "y": 0, "to_x": 160, "to_y": 90])
        assertOK(reply)
        XCTAssertEqual(reply["effect"] as? String, "posted")
        XCTAssertEqual(system.actions, [
            .postDrag(ScreenPoint(x: 1920, y: -200), ScreenPoint(x: 3200, y: 520)),
        ])
    }

    func testDragWithEitherPointOutsideThePictureIsBadRequest() {
        let frame = shoot()
        let outside: [[String: Any]] = [
            ["x": 320, "y": 10, "to_x": 10, "to_y": 10], ["x": 10, "y": 180, "to_x": 10, "to_y": 10],
            ["x": 10, "y": 10, "to_x": 320, "to_y": 10], ["x": 10, "y": 10, "to_x": 10, "to_y": 180],
            ["x": -1, "y": 10, "to_x": 10, "to_y": 10], ["x": 10, "y": 10, "to_x": 10, "to_y": -0.5],
        ]
        for points in outside {
            var arguments = points
            arguments["frame_id"] = frame
            assertRefused(act("drag", arguments), .badRequest, "\(points)")
        }
        XCTAssertEqual(system.actions, [])
    }

    func testScrollIsByLinesAtThePoint() {
        let frame = shoot()
        assertOK(act("scroll", ["frame_id": frame, "x": 160, "y": 90, "dx": 0, "dy": 3]))
        assertOK(act("scroll", ["frame_id": frame, "x": 160, "y": 90, "dx": -2, "dy": 0]))
        assertOK(act("scroll", ["frame_id": frame, "x": 160, "y": 90, "dx": 4.0, "dy": -7.0]))
        let point = ScreenPoint(x: 960, y: 540)
        XCTAssertEqual(system.actions, [
            .postScroll(point, dx: 0, dy: 3), .postScroll(point, dx: -2, dy: 0),
            .postScroll(point, dx: 4, dy: -7),
        ])
    }

    func testScrollIsHeldWithin50LinesEachWay() {
        let frame = shoot()
        let table: [(Int, Int, Int, Int)] = [
            (999, -999, 50, -50), (-51, 51, -50, 50), (50, -50, 50, -50), (49, -49, 49, -49),
            (0, 0, 0, 0), (1_000_000_000, -1_000_000_000, 50, -50),
        ]
        for (dx, dy, _, _) in table {
            assertOK(act("scroll", ["frame_id": frame, "x": 1, "y": 1, "dx": dx, "dy": dy]), "\(dx) \(dy)")
        }
        let point = ScreenPoint(x: 6, y: 6)
        let expected: [FakeSystem.Call] = table.map { .postScroll(point, dx: $0.2, dy: $0.3) }
        XCTAssertEqual(system.actions, expected)
        XCTAssertEqual(Limits.scrollLines, -50...50)
    }

    func testScrollOutsideThePictureIsBadRequest() {
        let frame = shoot()
        assertRefused(
            act("scroll", ["frame_id": frame, "x": 320, "y": 90, "dx": 0, "dy": 1]), .badRequest
        )
        XCTAssertEqual(system.actions, [])
    }

    // MARK: the frame

    func testFrameThatIsNotTheLastOfItsDisplayIsRefused() {
        let first = shoot()
        system.pixel = 0x41
        let second = shoot()
        XCTAssertNotEqual(first, second)

        let reply = click(first, 1, 1)
        assertRefused(reply, .frameMismatch)
        XCTAssertEqual(
            reply["detail"] as? String,
            "That is not the last frame captured of display 1; take a new screenshot."
        )
        XCTAssertEqual(system.actions, [])
        assertOK(click(second, 1, 1))
    }

    func testFrameCountsFor300SecondsAndNoLonger() {
        let frame = shoot()
        system.clock = 10_299
        assertOK(click(frame, 1, 1))
        system.clock = 10_300
        assertOK(click(frame, 1, 1), "exactly 300 seconds old is still at most 300")
        system.forgetCalls()

        system.clock = 10_300.5
        let late = click(frame, 1, 1)
        assertRefused(late, .frameMismatch)
        XCTAssertEqual(
            late["detail"] as? String, "That frame is over 300 seconds old; take a new screenshot."
        )
        system.clock = 99_999
        assertRefused(click(frame, 1, 1), .frameMismatch)
        XCTAssertEqual(system.actions, [])
        XCTAssertEqual(Limits.maxFrameAge, 300)
    }

    func testNewPictureOfTheSameScreenMakesTheFrameFreshAgain() {
        let frame = shoot()
        system.clock = 10_400
        assertRefused(click(frame, 1, 1), .frameMismatch)

        let again = ask("screenshot", ["max_px": 320, "since": frame])
        XCTAssertEqual(again["unchanged"] as? Bool, true)
        XCTAssertEqual(again["frame_id"] as? String, frame)
        assertOK(click(frame, 1, 1))
        system.clock = 10_700
        assertOK(click(frame, 1, 1))
        system.clock = 10_701
        assertRefused(click(frame, 1, 1), .frameMismatch)
    }

    func testFrameIDOfAnotherDisplayIsRefused() {
        let main = shoot()
        let forged = main.replacingOccurrences(of: "-320x180-1", with: "-320x180-2")
        XCTAssertNotEqual(forged, main)
        assertRefused(click(forged, 1, 1), .frameMismatch, "no picture of display 2 was taken")

        system.pixel = 0x41
        let side = shoot(display: 2)
        let reply = click(forged, 1, 1)
        assertRefused(reply, .frameMismatch, "the pixels are those of display 1")
        XCTAssertEqual(
            reply["detail"] as? String,
            "That is not the last frame captured of display 2; take a new screenshot."
        )
        let crossed = side.replacingOccurrences(of: "-320x180-2", with: "-320x180-1")
        assertRefused(click(crossed, 1, 1), .frameMismatch)
        XCTAssertEqual(system.actions, [])
    }

    func testEachDisplayKeepsItsOwnLastFrame() {
        let main = shoot()
        system.pixel = 0x41
        let side = shoot(display: 2)
        assertOK(click(main, 160, 90), "a picture of another display does not make this one old")
        assertOK(click(side, 160, 90))

        system.pixel = 0x42
        let newer = shoot(display: 2)
        assertRefused(click(side, 160, 90), .frameMismatch)
        assertOK(click(main, 160, 90))
        assertOK(click(newer, 160, 90))
        XCTAssertEqual(clicked, [
            ScreenPoint(x: 960, y: 540), ScreenPoint(x: 3200, y: 520),
            ScreenPoint(x: 960, y: 540), ScreenPoint(x: 3200, y: 520),
        ])
    }

    func testFrameOfAnotherSizeOfTheSameScreenIsAnotherFrame() {
        let small = shoot(maxPx: 320)
        let larger = shoot(maxPx: 400)
        XCTAssertTrue(larger.hasSuffix("-400x225-1"), larger)
        assertRefused(click(small, 1, 1), .frameMismatch)
        assertOK(click(larger, 399, 224))
    }

    func testTextThatIsNoFrameIDIsFrameMismatch() {
        let real = shoot()
        let hash = String(real.prefix(16))
        let garbage = [
            "", " ", "abc", "latest", hash, "\(hash)-320x180", "\(hash)-320x180-1-1",
            "\(hash)-320x180-", "\(hash)--1", "\(hash)-320-1", "\(hash)-320x-1", "\(hash)-x180-1",
            "\(hash)-320x180x2-1", "\(hash)-0x180-1", "\(hash)-320x0-1", "\(hash)-0x140x180-1",
            "\(hash)-320x180-one", "\(hash)-320x180--1", "\(hash)-320x180-4294967296",
            "\(hash)-320x180-99999999999", "\(hash)-32000000000x180-1", "\(hash.uppercased())X-320x180-1",
            "\(hash.dropLast())-320x180-1", "\(hash)0-320x180-1", "\(hash.dropLast())g-320x180-1",
            " \(real)", "\(real) ", "\(real)\n", real.replacingOccurrences(of: "x", with: "X"),
            "\(hash)-320x180-01",
        ]
        for id in garbage {
            assertRefused(click(id, 1, 1), .frameMismatch, "<\(id)>")
        }
        XCTAssertEqual(system.actions, [])
        assertOK(click(real, 1, 1), "the frame is still there after all that")
    }

    func testUpperCaseHexIsNotTheFrameTheHelperGaveOut() {
        system.captured = RawImage(width: 2, height: 1, rgba: Data("abcdefgh".utf8))
        let real = shoot()
        let hash = String(real.prefix(16))
        XCTAssertNotEqual(hash.uppercased(), hash, "the fixture's hash has a letter in it")
        assertRefused(click("\(hash.uppercased())-2x1-1", 0, 0), .frameMismatch)
        assertOK(click(real, 0, 0))
    }

    func testFrameIsCheckedForAKindThatNeedsNone() {
        readTree([Self.field])
        system.elementFrames[31] = ScreenRect(x: 100, y: 100, width: 200, height: 40)
        let stale = "0123456789abcdef-320x180-1"
        let requests: [(String, [String: Any])] = [
            ("key", ["keys": "enter"]), ("type", ["text": "hi"]),
            ("set_value", ["ref": "a1", "text": "hi"]), ("click", ["ref": "a1"]),
        ]
        for (kind, arguments) in requests {
            var withStale = arguments
            withStale["frame_id"] = stale
            assertRefused(act(kind, withStale), .frameMismatch, kind)
        }
        XCTAssertEqual(system.actions, [])

        let frame = shoot()
        for (kind, arguments) in requests {
            var withFrame = arguments
            withFrame["frame_id"] = frame
            assertOK(act(kind, withFrame), kind)
        }
        XCTAssertEqual(system.actions.count, 4)
    }

    func testCaptureThatFailsLeavesTheEarlierFrameInPlace() {
        let frame = shoot()
        system.captureError = .captureFailed("The display went away.")
        assertRefused(ask("screenshot", ["max_px": 320]), .captureFailed)
        system.captureError = nil
        assertOK(click(frame, 1, 1))
    }

    // MARK: the point

    func testPointOutsideThePictureIsBadRequestAndNothingIsPosted() {
        let frame = shoot()
        let outside: [(Double, Double)] = [
            (320, 90), (160, 180), (320, 180), (-0.01, 90), (160, -1), (-1, -1), (1e9, 1e9),
            (320.5, 0), (0, 180.5),
        ]
        for (x, y) in outside {
            let reply = click(frame, x, y)
            assertRefused(reply, .badRequest, "\(x) \(y)")
            XCTAssertEqual(
                reply["detail"] as? String, "The point is outside the picture, which is 320 by 180 pixels."
            )
        }
        XCTAssertEqual(system.actions, [])
    }

    func testEdgesOfThePictureAreInsideIt() {
        let frame = shoot()
        assertOK(click(frame, 0, 0))
        assertOK(click(frame, 319, 179))
        assertOK(click(frame, 319.99, 179.99))
        XCTAssertEqual(clicked.count, 3)
        XCTAssertEqual(clicked.first, ScreenPoint(x: 0, y: 0))
        XCTAssertEqual(clicked.dropFirst().first, ScreenPoint(x: 1914, y: 1074))
        guard let last = clicked.last else { return XCTFail("no click was posted") }
        XCTAssertLessThan(last.x, 1920)
        XCTAssertLessThan(last.y, 1080)
    }

    // MARK: the system's own answers

    func testPostThatChecksItsPermissionAgainIsAnsweredWithThatCode() {
        let frame = shoot()
        system.postError = .accessibilityMissing
        assertRefused(click(frame, 1, 1), .permissionMissingAccessibility)
        assertRefused(
            act("drag", ["frame_id": frame, "x": 1, "y": 1, "to_x": 2, "to_y": 2]),
            .permissionMissingAccessibility
        )
        assertRefused(
            act("scroll", ["frame_id": frame, "x": 1, "y": 1, "dx": 0, "dy": 1]),
            .permissionMissingAccessibility
        )
        assertRefused(act("key", ["keys": "enter"]), .permissionMissingAccessibility)
        assertRefused(act("type", ["text": "hi"]), .permissionMissingAccessibility)
    }

    func testPostThatFailsIsInternalWithTheSystemsWords() {
        let frame = shoot()
        system.postError = .failed("The event could not be made.")
        let reply = click(frame, 1, 1)
        assertRefused(reply, .internalError)
        XCTAssertEqual(reply["detail"] as? String, "The event could not be made.")
    }
}
