import Foundation
import XCTest
@testable import DesktopHelperCore

final class ListingTests: HelperTestCase {
    private func rows(_ reply: [String: Any], _ key: String) -> [[String: Any]] {
        reply[key] as? [[String: Any]] ?? []
    }

    private func window(
        _ title: String, at bounds: ScreenRect = ScreenRect(x: 100, y: 100, width: 800, height: 600),
        layer: Int = 0, app: AppInfo = Fixture.textEdit
    ) -> WindowInfo {
        WindowInfo(app: app.name, pid: app.pid, title: title, bounds: bounds, layer: layer)
    }

    // MARK: apps

    func testAppsAreSortedByNameWithTheFrontmostAndTheHiddenMarked() {
        let reply = ask("apps")
        assertOK(reply)
        XCTAssertEqual(Set(reply.keys), ["id", "ok", "apps"])
        let apps = rows(reply, "apps")
        XCTAssertEqual(apps.map { $0["app"] as? String }, ["Notes", "Safari", "TextEdit"])
        XCTAssertEqual(
            apps.map { $0["bundle_id"] as? String },
            ["com.apple.Notes", "com.apple.Safari", "com.apple.TextEdit"]
        )
        XCTAssertEqual(apps.map { $0["pid"] as? Int }, [500, 300, 4242])
        XCTAssertEqual(apps.map { $0["frontmost"] as? Bool }, [false, false, true])
        XCTAssertEqual(apps.map { $0["hidden"] as? Bool }, [false, true, false])
        for row in apps {
            XCTAssertEqual(Set(row.keys), ["app", "bundle_id", "pid", "frontmost", "hidden"])
            XCTAssertTrue(isBoolean(row["frontmost"]))
            XCTAssertTrue(isBoolean(row["hidden"]))
        }
    }

    func testAppsLineAsItIsWritten() {
        system.apps = [Fixture.textEdit]
        XCTAssertEqual(
            dispatcher.respond(to: Data(#"{"id":"4","cmd":"apps"}"#.utf8)),
            #"{"id":"4","ok":true,"apps":[{"app":"TextEdit","bundle_id":"com.apple.TextEdit","#
                + #""frontmost":true,"hidden":false,"pid":4242}]}"#
        )
    }

    func testAppsSortTakesNoNoticeOfCaseAndPutsEqualNamesByPid() {
        system.apps = [
            AppInfo(name: "beta", bundleID: "b.one", pid: 30),
            AppInfo(name: "Alpha", bundleID: "a.one", pid: 20),
            AppInfo(name: "Beta", bundleID: "b.two", pid: 10),
            AppInfo(name: "alpha", bundleID: "a.two", pid: 5),
            AppInfo(name: "Zed", bundleID: "z", pid: 1),
        ]
        XCTAssertEqual(rows(ask("apps"), "apps").map { $0["pid"] as? Int }, [5, 20, 10, 30, 1])
    }

    func testAppsWithNoFrontmostApplicationMarkNone() {
        system.front = nil
        let apps = rows(ask("apps"), "apps")
        XCTAssertEqual(apps.count, 3)
        XCTAssertEqual(apps.map { $0["frontmost"] as? Bool }, [false, false, false])
    }

    func testAppsOfAMachineThatRunsNoneIsAnEmptyList() {
        system.apps = []
        let reply = ask("apps")
        assertOK(reply)
        XCTAssertEqual((reply["apps"] as? [Any])?.count, 0)
    }

    func testAppsNeedNoPermissionAndTouchNothingAPermissionGuards() {
        system.screenRecording = false
        system.accessibility = false
        assertOK(ask("apps"))
        XCTAssertEqual(system.calls, [.isLocked, .isDisplayAsleep, .frontmostApp, .runningApps])
        XCTAssertEqual(system.touches, [])
    }

    // MARK: windows

    func testWindowsOfLayerZeroFrontToBack() {
        system.windowList = [
            window("Untitled"),
            window("Dock", layer: 20, app: AppInfo(name: "Dock", bundleID: "com.apple.dock", pid: 77)),
            window("Shopping", at: ScreenRect(x: 2000, y: 0, width: 500, height: 400), app: Fixture.notes),
            window("Menu", layer: 25),
            window("", at: ScreenRect(x: 5, y: 6, width: 7, height: 8), layer: -1),
        ]
        let reply = ask("windows")
        assertOK(reply)
        XCTAssertEqual(Set(reply.keys), ["id", "ok", "windows"])
        let windows = rows(reply, "windows")
        XCTAssertEqual(windows.map { $0["title"] as? String }, ["Untitled", "Shopping"])
        XCTAssertEqual(windows.map { $0["app"] as? String }, ["TextEdit", "Notes"])
        XCTAssertEqual(windows.map { $0["pid"] as? Int }, [4242, 500])
        XCTAssertEqual(windows.map { $0["display"] as? Int }, [1, 2])
        XCTAssertEqual(windows.first?["bounds"] as? [Int], [100, 100, 800, 600])
        XCTAssertEqual(windows.last?["bounds"] as? [Int], [2000, 0, 500, 400])
        for row in windows {
            XCTAssertEqual(Set(row.keys), ["app", "pid", "title", "bounds", "display"])
        }
        XCTAssertEqual(
            system.calls, [.isLocked, .isDisplayAsleep, .hasScreenRecording, .displays, .windows]
        )
    }

    func testWindowsLineAsItIsWritten() {
        system.windowList = [window("Untitled")]
        XCTAssertEqual(
            dispatcher.respond(to: Data(#"{"id":"5","cmd":"windows"}"#.utf8)),
            #"{"id":"5","ok":true,"windows":[{"app":"TextEdit","bounds":[100,100,800,600],"#
                + #""display":1,"pid":4242,"title":"Untitled"}]}"#
        )
    }

    func testWindowsStopAtAHundred() {
        system.windowList = (0..<150).flatMap { index in
            [window("w\(index)"), window("overlay \(index)", layer: 25)]
        }
        let windows = rows(ask("windows"), "windows")
        XCTAssertEqual(windows.count, 100)
        XCTAssertEqual(windows.map { $0["title"] as? String }, (0..<100).map { "w\($0)" })
        XCTAssertEqual(Limits.maxWindows, 100)
    }

    func testWindowTitleIsCutAt200Characters() {
        system.windowList = [
            window(String(repeating: "x", count: 250)), window(String(repeating: "y", count: 200)),
            window(""),
        ]
        let titles = rows(ask("windows"), "windows").map { $0["title"] as? String ?? "?" }
        XCTAssertEqual(titles, [
            String(repeating: "x", count: 200), String(repeating: "y", count: 200), "",
        ])
    }

    func testWindowBoundsAreWholeGlobalPoints() {
        system.windowList = [
            window("a", at: ScreenRect(x: 10.4, y: -20.6, width: 300.5, height: 199.5)),
            window("b", at: ScreenRect(x: -1930.2, y: 1079.5, width: 0.4, height: 0)),
        ]
        let bounds = rows(ask("windows"), "windows").map { $0["bounds"] as? [Int] }
        XCTAssertEqual(bounds, [[10, -21, 301, 200], [-1930, 1080, 0, 0]])
    }

    func testWindowIsOnTheDisplayThatHoldsMostOfIt() {
        system.windowList = [
            window("mostly side", at: ScreenRect(x: 1800, y: 0, width: 400, height: 300)),
            window("mostly main", at: ScreenRect(x: 1700, y: 0, width: 400, height: 300)),
            window("above the main one", at: ScreenRect(x: 2000, y: -150, width: 100, height: 100)),
            window("nowhere", at: ScreenRect(x: -9000, y: -9000, width: 100, height: 100)),
        ]
        let displays = rows(ask("windows"), "windows").map { $0["display"] as? Int }
        XCTAssertEqual(displays, [2, 1, 2, 1])
    }

    func testWindowOnNoDisplayGoesToTheMainOneWhereverItIsListed() {
        system.displayList = [Fixture.side, Fixture.main]
        system.windowList = [window("nowhere", at: ScreenRect(x: -9000, y: 0, width: 10, height: 10))]
        XCTAssertEqual(rows(ask("windows"), "windows").map { $0["display"] as? Int }, [1])
    }

    func testWindowsOfAnEmptyScreenIsAnEmptyList() {
        let reply = ask("windows")
        assertOK(reply)
        XCTAssertEqual((reply["windows"] as? [Any])?.count, 0)
    }

    func testWindowListThatChecksItsPermissionAgainIsAnsweredWithThatCode() {
        system.windowsError = SystemError.screenRecordingMissing
        assertRefused(ask("windows"), .permissionMissingScreen)
    }

    func testWindowListThatFailsIsInternalWithTheSystemsWords() {
        system.windowsError = SystemError.failed("The window server gave no list.")
        let reply = ask("windows")
        assertRefused(reply, .internalError)
        XCTAssertEqual(reply["detail"] as? String, "The window server gave no list.")
    }
}
