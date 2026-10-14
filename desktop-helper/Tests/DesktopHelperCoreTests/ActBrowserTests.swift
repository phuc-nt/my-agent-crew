import Foundation
import XCTest
@testable import DesktopHelperCore

/// The helper never acts in a web browser and never brings one forward, whatever the agent's
/// list of applications says; it still reads and shows one.
final class ActBrowserTests: HelperTestCase {
    /// Browsers as they come: the plain one, a site saved as an app of its own, an id written in
    /// another case, and a Safari web app.
    private static let browsers = [
        AppInfo(name: "Safari", bundleID: "com.apple.Safari", pid: 800),
        AppInfo(name: "Gmail", bundleID: "com.google.Chrome.app.abc", pid: 801),
        AppInfo(name: "Safari", bundleID: "com.apple.safari", pid: 802),
        AppInfo(
            name: "Calendar", bundleID: "com.apple.Safari.WebApp.6F1C2A9E-3D4B-4C8E-9A1F-2B7D5E0C8A13",
            pid: 803
        ),
    ]
    /// Ids that only start like a browser's, and an app that is no browser at all.
    private static let nearMisses = [
        AppInfo(name: "Chromeish", bundleID: "com.google.Chromeish", pid: 810), Fixture.notes,
    ]
    private static let inFront = "The frontmost application is a web browser; the helper never acts in one."
    private static let forward = "That application is a web browser; the helper never brings one forward."

    func testEveryKindOfActionIsRefusedWhileABrowserIsFrontmost() {
        for browser in Self.browsers {
            reset()
            system.front = browser
            system.apps.append(browser)
            for action in everyKindOfAction() {
                let note = "\(browser.bundleID) \(action.kind)"
                let reply = act(action.kind, action.arguments, app: browser.name)
                assertRefused(reply, .browserApp, note)
                XCTAssertEqual(reply["detail"] as? String, Self.inFront, note)
            }
            assertRefused(act("focus_app", app: browser.name), .browserApp, browser.bundleID)
            XCTAssertEqual(system.touches, [], "nothing is clicked, typed, set or brought forward")
            XCTAssertFalse(system.calls.contains(.isSecureInputOn), "the browser is answered first")
        }
    }

    /// Bringing a listed application forward sends the browser in front nothing: it is how an
    /// agent leaves a browser the owner left there.
    func testFocusAppLeavesABrowserInFrontForAnotherApplication() {
        for browser in Self.browsers {
            reset()
            system.front = browser
            system.apps.append(browser)
            system.onCall = { [weak system] call in
                if call == .activate(pid: Fixture.textEdit.pid) { system?.front = Fixture.textEdit }
            }
            assertOK(act("focus_app", app: "TextEdit"), browser.bundleID)
            XCTAssertEqual(system.actions, [.activate(pid: Fixture.textEdit.pid)], browser.bundleID)
            XCTAssertEqual(system.front, Fixture.textEdit, browser.bundleID)
        }
    }

    func testFocusAppNeverBringsABrowserForward() {
        for browser in Self.browsers {
            reset()
            assertRefused(act("focus_app", app: browser.name), .appNotRunning, browser.bundleID)
            system.apps.append(browser)
            for name in [browser.name, browser.bundleID, browser.bundleID.uppercased()] {
                let reply = act("focus_app", app: name)
                assertRefused(reply, .browserApp, name)
                XCTAssertEqual(reply["detail"] as? String, Self.forward, name)
            }
            XCTAssertEqual(system.touches, [], "no browser is activated")
            XCTAssertEqual(system.front, Fixture.textEdit)
        }
    }

    func testFocusAppOfABrowserIsRefusedWithNoApplicationInFront() {
        system.front = nil
        system.apps.append(Fixture.safari)
        assertRefused(act("focus_app", app: "Safari"), .browserApp)
        XCTAssertEqual(system.touches, [])
    }

    func testApplicationsWhoseIDsOnlyStartLikeABrowsersAreActedIn() {
        for app in Self.nearMisses {
            reset()
            system.front = app
            for action in everyKindOfAction() {
                assertOK(act(action.kind, action.arguments, app: app.name), "\(app.bundleID) \(action.kind)")
            }
            XCTAssertEqual(system.actions.count, 8, app.bundleID)
        }
    }

    func testFocusAppBringsForwardAnApplicationWhoseIDOnlyStartsLikeABrowsers() {
        let chromeish = Self.nearMisses[0]
        system.apps.append(chromeish)
        system.onCall = { [weak system] call in
            if call == .activate(pid: chromeish.pid) { system?.front = chromeish }
        }
        assertOK(act("focus_app", app: "Chromeish"))
        XCTAssertEqual(system.actions, [.activate(pid: chromeish.pid)])
    }

    func testBrowserInFrontIsStillReadAndShown() {
        system.front = Fixture.safari
        system.apps.append(Fixture.safari)
        assertOK(ask("state"))
        assertOK(ask("apps"))
        assertOK(ask("windows"))
        XCTAssertEqual(readTree([Self.field])["pid"] as? Int, Int(Fixture.safari.pid))
        XCTAssertFalse(shoot().isEmpty)
        system.front = Fixture.textEdit
        XCTAssertEqual(readTree([Self.field], app: "Safari")["pid"] as? Int, Int(Fixture.safari.pid))
        XCTAssertEqual(system.actions, [])
    }

    func testTypingStopsWhenABrowserComesToTheFront() {
        // A site saved as an app can carry the very name the agent typed into.
        let site = AppInfo(name: "TextEdit", bundleID: "com.google.Chrome.app.textedit", pid: 4243)
        system.onCall = { [weak system] call in
            if case .postText = call { system?.front = site }
        }
        let reply = act("type", ["text": String(repeating: "a", count: 50)])
        assertRefused(reply, .browserApp)
        XCTAssertEqual(reply["detail"] as? String, "A web browser came to the front after 20 characters were typed.")
        XCTAssertEqual(system.actions, [.postText(String(repeating: "a", count: 20))])
    }

    // MARK: the list

    func testBrowserIDsAreMatchedWhateverTheCaseAndWithAnythingAfterADot() {
        for id in Browsers.bundleIDs {
            XCTAssertTrue(Browsers.contains(bundleID: id), id)
            XCTAssertTrue(Browsers.contains(bundleID: id.uppercased()), id)
            XCTAssertTrue(Browsers.contains(bundleID: id.lowercased() + ".app.site"), id)
            XCTAssertFalse(Browsers.contains(bundleID: "x" + id), id)
            // One letter more is another application, unless the id already goes on from
            // another listed one after a dot (`com.google.chrome.for.testing`).
            let longer = (id + "x").lowercased()
            let underAnother = Browsers.bundleIDs.contains { other in
                other != id && longer.hasPrefix(other.lowercased() + ".")
            }
            XCTAssertEqual(Browsers.contains(bundleID: id + "x"), underAnother, id)
        }
        XCTAssertTrue(Browsers.contains(bundleID: "com.google.chrome.for.testingx"))
        XCTAssertFalse(Browsers.contains(bundleID: "com.apple.Safarix"))
        XCTAssertFalse(Browsers.contains(bundleID: "org.mozilla.firefoxx"))
        for id in ["", ".", "com", "com.apple", "com.google", "com.apple.Notes", "com.google.Chromeish"] {
            XCTAssertFalse(Browsers.contains(bundleID: id), id)
        }
    }

    func testBrowserListIsWellFormed() {
        let ids = Browsers.bundleIDs
        XCTAssertEqual(Set(ids.map { $0.lowercased() }).count, ids.count, "no id twice, whatever the case")
        for id in ids {
            XCTAssertFalse(id.isEmpty)
            XCTAssertFalse(id.hasSuffix(".") || id.hasPrefix("."), id)
            XCTAssertNil(id.rangeOfCharacter(from: .whitespacesAndNewlines), id)
            XCTAssertGreaterThanOrEqual(id.split(separator: ".").count, 2, id)
        }
        for id in ["com.apple.Safari", "com.google.Chrome", "org.mozilla.firefox", "com.microsoft.edgemac"] {
            XCTAssertTrue(ids.contains(id), id)
        }
    }
}
