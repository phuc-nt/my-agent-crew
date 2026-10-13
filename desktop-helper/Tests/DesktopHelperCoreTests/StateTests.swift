import Foundation
import XCTest
@testable import DesktopHelperCore

final class StateTests: HelperTestCase {
    private let stateKeys: Set<String> = [
        "id", "ok", "version", "protocol", "locked", "display_asleep", "screen_recording",
        "accessibility", "secure_input", "displays", "frontmost",
    ]

    func testStateAnswersEveryKeyOfTheContract() {
        let reply = ask("state")
        assertOK(reply)
        XCTAssertEqual(Set(reply.keys), stateKeys)
        XCTAssertEqual(reply["version"] as? String, "0.1.0")
        XCTAssertEqual(reply["protocol"] as? Int, 1)
        XCTAssertFalse(isBoolean(reply["protocol"]))
        for key in ["locked", "display_asleep", "screen_recording", "accessibility", "secure_input"] {
            XCTAssertTrue(isBoolean(reply[key]), key)
        }
        XCTAssertEqual(reply["locked"] as? Bool, false)
        XCTAssertEqual(reply["display_asleep"] as? Bool, false)
        XCTAssertEqual(reply["screen_recording"] as? Bool, true)
        XCTAssertEqual(reply["accessibility"] as? Bool, true)
        XCTAssertEqual(reply["secure_input"] as? Bool, false)

        let displays = reply["displays"] as? [[String: Any]] ?? []
        guard displays.count == 2 else { return XCTFail("\(displays.count) displays, not two") }
        XCTAssertEqual(Set(displays[0].keys), ["id", "width", "height", "scale", "main"])
        XCTAssertEqual(displays[0]["id"] as? Int, 1)
        XCTAssertEqual(displays[0]["width"] as? Int, 1920)
        XCTAssertEqual(displays[0]["height"] as? Int, 1080)
        XCTAssertEqual(displays[0]["scale"] as? Double, 2)
        XCTAssertEqual(displays[0]["main"] as? Bool, true)
        XCTAssertEqual(displays[1]["id"] as? Int, 2)
        XCTAssertEqual(displays[1]["width"] as? Int, 2560)
        XCTAssertEqual(displays[1]["main"] as? Bool, false)

        let frontmost = reply["frontmost"] as? [String: Any] ?? [:]
        XCTAssertEqual(Set(frontmost.keys), ["app", "bundle_id", "pid"])
        XCTAssertEqual(frontmost["app"] as? String, "TextEdit")
        XCTAssertEqual(frontmost["bundle_id"] as? String, "com.apple.TextEdit")
        XCTAssertEqual(frontmost["pid"] as? Int, 4242)
    }

    func testStateLineForTheContractsExample() {
        system.displayList = [Fixture.main]
        let written = dispatcher.respond(to: Data(#"{"id":"1","cmd":"state"}"#.utf8))
        XCTAssertEqual(
            written,
            #"{"id":"1","ok":true,"accessibility":true,"display_asleep":false,"#
                + #""displays":[{"id":1,"height":1080,"main":true,"scale":2.0,"width":1920}],"#
                + #""frontmost":{"app":"TextEdit","bundle_id":"com.apple.TextEdit","pid":4242},"#
                + #""locked":false,"protocol":1,"screen_recording":true,"secure_input":false,"#
                + #""version":"0.1.0"}"#
        )
    }

    func testStateAnswersOnALockedSleepingMachineWithNothingGranted() {
        system.locked = true
        system.asleep = true
        system.screenRecording = false
        system.accessibility = false
        system.secureInput = true
        system.front = nil
        system.displayList = []
        let reply = ask("state")
        assertOK(reply)
        XCTAssertEqual(Set(reply.keys), stateKeys)
        XCTAssertEqual(reply["locked"] as? Bool, true)
        XCTAssertEqual(reply["display_asleep"] as? Bool, true)
        XCTAssertEqual(reply["screen_recording"] as? Bool, false)
        XCTAssertEqual(reply["accessibility"] as? Bool, false)
        XCTAssertEqual(reply["secure_input"] as? Bool, true)
        XCTAssertEqual((reply["displays"] as? [Any])?.count, 0)
        XCTAssertTrue(reply["frontmost"] is NSNull)
    }

    func testStateMakesOnlyTheReadsThatCannotShowADialog() {
        ask("state")
        XCTAssertEqual(system.touches, [])
        XCTAssertEqual(
            system.calls.map { "\($0)" }.sorted(),
            [
                "displays", "frontmostApp", "hasAccessibility", "hasScreenRecording",
                "isDisplayAsleep", "isLocked", "isSecureInputOn",
            ]
        )
    }

    func testDisplayScaleIsWrittenAsAFraction() {
        system.displayList = [
            DisplayInfo(
                id: 69_734_112, bounds: ScreenRect(x: 0, y: 0, width: 1512, height: 982),
                scale: 1.5, isMain: true
            ),
        ]
        let written = dispatcher.respond(to: Data(#"{"id":"1","cmd":"state"}"#.utf8))
        XCTAssertTrue(
            written.contains(#"{"id":69734112,"height":982,"main":true,"scale":1.5,"width":1512}"#),
            written
        )
    }

    func testRequestPermissionsOnALockedConsoleAsksForNothing() {
        system.locked = true
        system.screenRecording = false
        system.accessibility = false
        assertRefused(ask("request_permissions"), .locked)
        XCTAssertEqual(system.calls, [.isLocked])
    }

    func testRequestPermissionsAsksOnceAndSaysWhatIsGrantedNow() {
        system.screenRecording = false
        system.accessibility = false
        let reply = ask("request_permissions")
        assertOK(reply)
        XCTAssertEqual(Set(reply.keys), ["id", "ok", "screen_recording", "accessibility"])
        XCTAssertTrue(isBoolean(reply["screen_recording"]))
        XCTAssertTrue(isBoolean(reply["accessibility"]))
        XCTAssertEqual(reply["screen_recording"] as? Bool, false)
        XCTAssertEqual(reply["accessibility"] as? Bool, false)
        XCTAssertEqual(
            system.calls, [.isLocked, .requestPermissions, .hasScreenRecording, .hasAccessibility]
        )
    }

    func testRequestPermissionsReadsTheGrantsAfterAsking() {
        system.screenRecording = false
        system.accessibility = false
        system.grantsOnRequest = true
        let reply = ask("request_permissions")
        assertOK(reply)
        XCTAssertEqual(reply["screen_recording"] as? Bool, true)
        XCTAssertEqual(reply["accessibility"] as? Bool, true)
    }

    func testRequestPermissionsDoesNotCareThatTheDisplaySleeps() {
        system.asleep = true
        assertOK(ask("request_permissions"))
        XCTAssertFalse(system.calls.contains(.isDisplayAsleep))
        XCTAssertEqual(system.calls.filter { $0 == .requestPermissions }.count, 1)
    }

    func testHelperSaysWhichVersionAndProtocolItIs() {
        XCTAssertEqual(HelperInfo.version, "0.1.0")
        XCTAssertEqual(HelperInfo.protocolVersion, 1)
        XCTAssertEqual(
            HelperInfo.defaultSocketPath(home: "/Users/someone"),
            "/Users/someone/.my-agent-crew/desktop/sock"
        )
    }
}
