import CryptoKit
import Foundation
import XCTest
@testable import DesktopHelperCore

final class ScreenshotTests: HelperTestCase {
    private let shotKeys: Set<String> = [
        "id", "ok", "frame_id", "display", "width", "height", "scale", "unchanged", "png_base64",
    ]

    /// The frame id the contract defines, worked out here from the pixels alone.
    private func expectedFrameID(pixel: UInt8, width: Int, height: Int, display: Int) -> String {
        let pixels = Data(repeating: pixel, count: width * height * 4)
        let hash = SHA256.hash(data: pixels).prefix(8).map { String(format: "%02x", $0) }.joined()
        return "\(hash)-\(width)x\(height)-\(display)"
    }

    private func captures() -> [FakeSystem.Call] {
        system.calls.filter {
            if case .capture = $0 { return true }
            return false
        }
    }

    private func picture(_ reply: [String: Any]) -> Data {
        Data(base64Encoded: reply["png_base64"] as? String ?? "") ?? Data()
    }

    /// Width and height as the PNG's own header gives them.
    private func headerSize(_ png: Data) -> [Int] {
        guard png.count >= 24 else { return [] }
        let bytes = [UInt8](png)
        func number(at start: Int) -> Int {
            bytes[start..<start + 4].reduce(0) { $0 << 8 | Int($1) }
        }
        return [number(at: 16), number(at: 20)]
    }

    func testScreenshotOfTheMainDisplayAtTheDefaultSize() {
        let reply = ask("screenshot", id: "7")
        assertOK(reply)
        XCTAssertEqual(Set(reply.keys), shotKeys)
        XCTAssertEqual(reply["display"] as? Int, 1)
        XCTAssertEqual(reply["width"] as? Int, 1456)
        XCTAssertEqual(reply["height"] as? Int, 819)
        XCTAssertEqual(reply["scale"] as? Double, 0.7583)
        XCTAssertEqual(reply["unchanged"] as? Bool, false)
        XCTAssertTrue(isBoolean(reply["unchanged"]))

        let frameID = reply["frame_id"] as? String ?? ""
        XCTAssertNotNil(
            frameID.range(of: "^[0-9a-f]{16}-1456x819-1$", options: .regularExpression), frameID
        )
        XCTAssertEqual(frameID, expectedFrameID(pixel: 0x40, width: 1456, height: 819, display: 1))

        let png = picture(reply)
        XCTAssertEqual([UInt8](png.prefix(8)), [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
        XCTAssertEqual(headerSize(png), [1456, 819])
        XCTAssertEqual(system.calls, [
            .isLocked, .isDisplayAsleep, .hasScreenRecording, .displays,
            .capture(display: 1, width: 1456, height: 819), .now,
        ])
    }

    func testMaxPxIsHeldWithin320And2000() {
        let table: [(Int, Int, Int)] = [
            (100, 320, 180), (0, 320, 180), (-5, 320, 180), (319, 320, 180), (320, 320, 180),
            (321, 321, 181), (800, 800, 450), (2000, 2000, 1125), (2001, 2000, 1125),
            (5000, 2000, 1125),
        ]
        for (asked, width, height) in table {
            reset()
            let reply = ask("screenshot", ["max_px": asked])
            assertOK(reply)
            XCTAssertEqual(captures(), [.capture(display: 1, width: width, height: height)], "\(asked)")
            XCTAssertEqual(reply["width"] as? Int, width, "\(asked)")
            XCTAssertEqual(reply["height"] as? Int, height, "\(asked)")
            XCTAssertEqual(headerSize(picture(reply)), [width, height], "\(asked)")
        }
        XCTAssertEqual(Limits.maxPx, 320...2000)
        XCTAssertEqual(Limits.defaultMaxPx, 1456)
    }

    func testPictureIsNeverMadeLargerThanTheDisplay() {
        for arguments in [[:], ["max_px": 2000]] as [[String: Any]] {
            reset()
            system.displayList = [
                DisplayInfo(
                    id: 7, bounds: ScreenRect(x: 0, y: 0, width: 800, height: 600), scale: 1,
                    isMain: true
                ),
            ]
            let reply = ask("screenshot", arguments)
            assertOK(reply)
            XCTAssertEqual(captures(), [.capture(display: 7, width: 800, height: 600)])
            XCTAssertEqual(reply["scale"] as? Double, 1)
            XCTAssertEqual(reply["display"] as? Int, 7)
        }
    }

    func testScreenshotOfAnotherDisplay() {
        let reply = ask("screenshot", ["display": 2, "max_px": 320])
        assertOK(reply)
        XCTAssertEqual(captures(), [.capture(display: 2, width: 320, height: 180)])
        XCTAssertEqual(reply["display"] as? Int, 2)
        XCTAssertEqual(reply["scale"] as? Double, 0.125)
        XCTAssertEqual(
            reply["frame_id"] as? String,
            expectedFrameID(pixel: 0x40, width: 320, height: 180, display: 2)
        )
    }

    func testMainDisplayIsTheOneMarkedMainNotTheFirstListed() {
        system.displayList = [Fixture.side, Fixture.main]
        assertOK(ask("screenshot", ["max_px": 320]))
        XCTAssertEqual(captures(), [.capture(display: 1, width: 320, height: 180)])
    }

    func testDisplayThatIsNotThereIsBadRequestAndNothingIsCaptured() {
        for display in [99, 0, -1, 4_294_967_296] {
            reset()
            assertRefused(ask("screenshot", ["display": display]), .badRequest, "\(display)")
            XCTAssertEqual(system.touches, [], "\(display)")
        }
    }

    func testArgumentOfTheWrongTypeIsBadRequestAndTheMachineIsNotAsked() {
        let wrong: [[String: Any]] = [
            ["display": "1"], ["display": 1.5], ["display": true], ["max_px": "800"],
            ["max_px": 800.5], ["max_px": [800]], ["since": 5], ["since": ["a"]], ["since": false],
        ]
        for arguments in wrong {
            assertRefused(ask("screenshot", arguments), .badRequest, "\(arguments)")
        }
        XCTAssertEqual(system.calls, [])
    }

    func testSinceThatNamesTheSameFrameLeavesThePictureOut() {
        let first = ask("screenshot", ["max_px": 320])
        let frameID = first["frame_id"] as? String ?? ""
        let again = ask("screenshot", ["max_px": 320, "since": frameID])
        assertOK(again)
        XCTAssertEqual(again["unchanged"] as? Bool, true)
        XCTAssertNil(again["png_base64"])
        XCTAssertEqual(Set(again.keys), shotKeys.subtracting(["png_base64"]))
        XCTAssertEqual(again["frame_id"] as? String, frameID)
        XCTAssertEqual(again["width"] as? Int, 320)
        XCTAssertEqual(again["height"] as? Int, 180)
        XCTAssertEqual(again["display"] as? Int, 1)
        XCTAssertEqual(again["scale"] as? Double, 0.1667)
        XCTAssertEqual(captures().count, 2, "the screen is captured again to see that it is the same")
    }

    func testSinceThatNamesAnotherFrameGetsThePicture() {
        let first = ask("screenshot", ["max_px": 320])
        let before = first["frame_id"] as? String ?? ""
        system.pixel = 0x41
        let after = ask("screenshot", ["max_px": 320, "since": before])
        assertOK(after)
        XCTAssertEqual(after["unchanged"] as? Bool, false)
        XCTAssertEqual(Set(after.keys), shotKeys)
        XCTAssertNotEqual(after["frame_id"] as? String, before)
        XCTAssertEqual(
            after["frame_id"] as? String,
            expectedFrameID(pixel: 0x41, width: 320, height: 180, display: 1)
        )
        XCTAssertFalse(picture(after).isEmpty)
    }

    func testSinceThatIsNoFrameIDAtAllGetsThePicture() {
        for since in ["", "latest", "0000000000000000-320x180-1"] {
            let reply = ask("screenshot", ["max_px": 320, "since": since])
            assertOK(reply)
            XCTAssertEqual(reply["unchanged"] as? Bool, false, since)
            XCTAssertNotNil(reply["png_base64"], since)
        }
    }

    func testSameScreenOfAnotherDisplayIsNotUnchanged() {
        let main = ask("screenshot", ["max_px": 320])["frame_id"] as? String ?? ""
        let side = ask("screenshot", ["max_px": 320, "display": 2, "since": main])
        XCTAssertEqual(side["unchanged"] as? Bool, false)
        XCTAssertNotEqual(side["frame_id"] as? String, main)
    }

    func testPictureIsTheSizeTheSystemGaveBack() {
        system.captured = RawImage(
            width: 100, height: 50, rgba: Data(repeating: 9, count: 100 * 50 * 4)
        )
        let reply = ask("screenshot", ["max_px": 320])
        assertOK(reply)
        XCTAssertEqual(reply["width"] as? Int, 100)
        XCTAssertEqual(reply["height"] as? Int, 50)
        XCTAssertEqual(reply["scale"] as? Double, 0.0521)
        XCTAssertEqual(
            reply["frame_id"] as? String,
            expectedFrameID(pixel: 9, width: 100, height: 50, display: 1)
        )
        XCTAssertEqual(headerSize(picture(reply)), [100, 50])
    }

    func testCaptureTheSystemRefusesIsCaptureFailedWithItsMessage() {
        system.captureError = .captureFailed("The display is being mirrored and cannot be captured.")
        let reply = ask("screenshot")
        assertRefused(reply, .captureFailed)
        XCTAssertEqual(
            reply["detail"] as? String, "The display is being mirrored and cannot be captured."
        )
    }

    func testCaptureThatChecksItsPermissionAgainIsAnsweredWithThatCode() {
        system.captureError = .screenRecordingMissing
        assertRefused(ask("screenshot"), .permissionMissingScreen)
    }

    func testPictureThatIsNotWholeIsCaptureFailed() {
        let broken = [
            RawImage(width: 10, height: 10, rgba: Data(count: 399)),
            RawImage(width: 10, height: 10, rgba: Data(count: 401)),
            RawImage(width: 0, height: 10, rgba: Data()),
            RawImage(width: 10, height: 0, rgba: Data()),
            RawImage(width: -1, height: -1, rgba: Data(count: 4)),
        ]
        for image in broken {
            reset()
            system.captured = image
            assertRefused(ask("screenshot"), .captureFailed, "\(image.width)x\(image.height)")
        }
    }

    func testMachineWithNoDisplayIsCaptureFailedAndNothingIsCaptured() {
        system.displayList = []
        assertRefused(ask("screenshot"), .captureFailed)
        XCTAssertEqual(system.touches, [])
    }

    func testScreenshotLineAsItIsWritten() {
        system.captured = RawImage(width: 2, height: 1, rgba: Data(repeating: 0, count: 8))
        let first = ask("screenshot", id: "7")
        let frameID = first["frame_id"] as? String ?? ""
        let request = #"{"id":"7","cmd":"screenshot","since":"\#(frameID)"}"#
        XCTAssertEqual(
            dispatcher.respond(to: Data(request.utf8)),
            #"{"id":"7","ok":true,"display":1,"frame_id":"\#(frameID)","height":1,"#
                + #""scale":0.001,"unchanged":true,"width":2}"#
        )
    }
}
