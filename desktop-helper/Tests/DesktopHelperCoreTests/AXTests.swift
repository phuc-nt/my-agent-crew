import Foundation
import XCTest
@testable import DesktopHelperCore

final class AXTests: HelperTestCase {
    /// The two nodes of the contract's example.
    private let exampleNodes = [
        RawNode(depth: 0, role: "AXWindow", title: "Untitled", element: 11),
        RawNode(
            depth: 1, role: "AXTextArea", value: "hello", focused: true, enabled: true,
            frame: ScreenRect(x: 120, y: 96, width: 800, height: 600), element: 12
        ),
    ]

    private func button(_ element: Int, title: String = "OK") -> RawNode {
        RawNode(depth: 1, role: "AXButton", title: title, element: element)
    }

    private func trees() -> [FakeSystem.Call] {
        system.calls.filter {
            if case .accessibilityTree = $0 { return true }
            return false
        }
    }

    func testTreeOfTheFrontmostApplicationAsTheContractWritesIt() {
        system.snapshot = AXSnapshot(window: "Untitled", nodes: exampleNodes, truncated: false)
        let written = dispatcher.respond(to: Data(#"{"id":"9","cmd":"ax"}"#.utf8))
        let name = decode(written)["outline"] as? String ?? "none"
        XCTAssertEqual(
            written,
            #"{"id":"9","ok":true,"app":"TextEdit","nodes":["#
                + #"{"depth":0,"ref":"a1","role":"AXWindow","title":"Untitled"},"#
                + #"{"depth":1,"enabled":true,"focused":true,"frame":[120,96,800,600],"#
                + #""ref":"a2","role":"AXTextArea","value":"hello"}],"#
                + #""outline":"\#(name)","pid":4242,"truncated":false,"window":"Untitled"}"#
        )
        XCTAssertEqual(system.calls, [
            .isLocked, .isDisplayAsleep, .hasAccessibility, .frontmostApp,
            .accessibilityTree(pid: 4242, maxNodes: 400),
        ])
    }

    func testAnswerHasEveryKeyOfTheContract() {
        let reply = readTree(exampleNodes)
        XCTAssertEqual(
            Set(reply.keys), ["id", "ok", "app", "pid", "window", "truncated", "nodes", "outline"]
        )
        XCTAssertEqual(reply["app"] as? String, "TextEdit")
        XCTAssertEqual(reply["pid"] as? Int, 4242)
        XCTAssertEqual(reply["window"] as? String, "Untitled")
        XCTAssertEqual(reply["truncated"] as? Bool, false)
        XCTAssertTrue(isBoolean(reply["truncated"]))
        XCTAssertEqual(nodes(reply).count, 2)
    }

    func testRefsCountFromOneInTheOrderOfTheTree() {
        let reply = readTree((1...12).map { button($0) })
        XCTAssertEqual(nodes(reply).map { $0["ref"] as? String }, (1...12).map { "a\($0)" })
    }

    func testTitleIsTheDescriptionWhenTheElementHasNoTitle() {
        let reply = readTree([
            RawNode(depth: 0, role: "AXButton", title: "Save", description: "Saves the file", element: 1),
            RawNode(depth: 0, role: "AXButton", description: "Close", element: 2),
            RawNode(depth: 0, role: "AXButton", title: "", description: "Minimise", element: 3),
            RawNode(depth: 0, role: "AXButton", title: "", description: "", element: 4),
            RawNode(depth: 0, role: "AXButton", element: 5),
        ])
        let titles = nodes(reply).map { $0["title"] as? String }
        XCTAssertEqual(titles, ["Save", "Close", "Minimise", nil, nil])
    }

    func testTitleAndValueAreCutAt200CharactersAndLeftOutWhenEmpty() {
        let long = String(repeating: "t", count: 250)
        let exact = String(repeating: "v", count: 200)
        let reply = readTree([
            RawNode(depth: 0, role: "AXTextArea", title: long, value: long, element: 1),
            RawNode(depth: 0, role: "AXTextArea", title: exact, value: exact, element: 2),
            RawNode(depth: 0, role: "AXTextArea", title: "", value: "", element: 3),
            RawNode(depth: 0, role: "AXStaticText", description: long, element: 4),
        ])
        let rows = nodes(reply)
        XCTAssertEqual(rows[0]["title"] as? String, String(repeating: "t", count: 200))
        XCTAssertEqual(rows[0]["value"] as? String, String(repeating: "t", count: 200))
        XCTAssertEqual(rows[1]["title"] as? String, exact)
        XCTAssertEqual(rows[1]["value"] as? String, exact)
        XCTAssertEqual(Set(rows[2].keys), ["ref", "depth", "role"])
        XCTAssertEqual(rows[3]["title"] as? String, String(repeating: "t", count: 200))
        XCTAssertEqual(Limits.maxFieldCharacters, 200)
    }

    func testSecureTextFieldIsMarkedAndNeverGivesItsValue() {
        system.snapshot = AXSnapshot(
            window: "Sign in",
            nodes: [
                RawNode(depth: 0, role: "AXSecureTextField", title: "Password", value: "hunter2", element: 1),
                RawNode(
                    depth: 0, role: "AXTextField", subrole: "AXSecureTextField", value: "s3cret-two",
                    element: 2
                ),
                RawNode(depth: 0, role: "AXTextField", title: "Name", value: "phuc", element: 3),
            ],
            truncated: false
        )
        let written = dispatcher.respond(to: Data(#"{"id":"1","cmd":"ax"}"#.utf8))
        XCTAssertFalse(written.contains("hunter2"), "a password is never written out")
        XCTAssertFalse(written.contains("s3cret-two"), "a password is never written out")
        let rows = nodes(decode(written))
        XCTAssertEqual(rows.map { $0["secure"] as? Bool }, [true, true, nil])
        XCTAssertEqual(rows.map { $0["value"] as? String }, [nil, nil, "phuc"])
        XCTAssertEqual(rows[0]["title"] as? String, "Password")
        XCTAssertEqual(rows[1]["role"] as? String, "AXTextField")
    }

    func testFieldTheElementDoesNotReportIsLeftOut() {
        let reply = readTree([
            RawNode(depth: 3, role: "AXGroup", element: 1),
            RawNode(depth: 4, role: "AXCheckBox", focused: false, enabled: false, element: 2),
            RawNode(
                depth: 4, role: "AXImage",
                frame: ScreenRect(x: 10.4, y: -20.6, width: 300.5, height: 199.5), element: 3
            ),
        ])
        let rows = nodes(reply)
        XCTAssertEqual(Set(rows[0].keys), ["ref", "depth", "role"])
        XCTAssertEqual(rows[0]["depth"] as? Int, 3)
        XCTAssertEqual(Set(rows[1].keys), ["ref", "depth", "role", "focused", "enabled"])
        XCTAssertEqual(rows[1]["focused"] as? Bool, false)
        XCTAssertEqual(rows[1]["enabled"] as? Bool, false)
        XCTAssertEqual(Set(rows[2].keys), ["ref", "depth", "role", "frame"])
        XCTAssertEqual(rows[2]["frame"] as? [Int], [10, -21, 301, 200])
    }

    func testMaxNodesIsHeldWithin50And400() {
        let table: [([String: Any], Int)] = [
            ([:], 400), (["max_nodes": 10], 50), (["max_nodes": 0], 50), (["max_nodes": -3], 50),
            (["max_nodes": 50], 50), (["max_nodes": 51], 51), (["max_nodes": 400], 400),
            (["max_nodes": 401], 400), (["max_nodes": 1000], 400), (["max_nodes": 120.0], 120),
        ]
        for (arguments, expected) in table {
            reset()
            assertOK(ask("ax", arguments))
            XCTAssertEqual(trees(), [.accessibilityTree(pid: 4242, maxNodes: expected)], "\(arguments)")
        }
        XCTAssertEqual(Limits.maxNodes, 50...400)
        XCTAssertEqual(Limits.defaultMaxNodes, 400)
    }

    func testArgumentOfTheWrongTypeIsBadRequestAndTheMachineIsNotAsked() {
        let wrong: [[String: Any]] = [
            ["max_nodes": "many"], ["max_nodes": 60.5], ["max_nodes": true], ["app": 5],
            ["app": ["TextEdit"]], ["app": ""],
        ]
        for arguments in wrong {
            assertRefused(ask("ax", arguments), .badRequest, "\(arguments)")
        }
        XCTAssertEqual(system.calls, [])
    }

    func testTruncatedIsWhatTheSystemSaysOfItsWalk() {
        system.snapshot = AXSnapshot(window: "Big", nodes: [button(1)], truncated: true)
        XCTAssertEqual(ask("ax")["truncated"] as? Bool, true)
    }

    func testTreeLongerThanAskedIsCutAndSaysSo() {
        system.snapshot = AXSnapshot(
            window: "Big", nodes: (1...60).map { button($0) }, truncated: false
        )
        let reply = ask("ax", ["max_nodes": 50])
        assertOK(reply)
        outline = reply["outline"] as? String ?? ""
        XCTAssertEqual(reply["truncated"] as? Bool, true)
        XCTAssertEqual(nodes(reply).count, 50)
        XCTAssertEqual(nodes(reply).last?["ref"] as? String, "a50")

        system.elementFrames[50] = ScreenRect(x: 0, y: 0, width: 10, height: 10)
        system.elementFrames[51] = ScreenRect(x: 0, y: 0, width: 10, height: 10)
        assertOK(act("click", ["ref": "a50"]))
        assertRefused(act("click", ["ref": "a51"]), .refUnknown)
    }

    func testTreeOfExactlyTheNumberAskedIsNotTruncated() {
        system.snapshot = AXSnapshot(
            window: "Fits", nodes: (1...50).map { button($0) }, truncated: false
        )
        let reply = ask("ax", ["max_nodes": 50])
        XCTAssertEqual(reply["truncated"] as? Bool, false)
        XCTAssertEqual(nodes(reply).count, 50)
    }

    func testApplicationIsFoundByNameOrBundleIDWhateverTheCase() {
        for name in ["Notes", "notes", "NOTES", "com.apple.Notes", "COM.APPLE.NOTES"] {
            reset()
            let reply = ask("ax", ["app": name])
            assertOK(reply)
            XCTAssertEqual(reply["app"] as? String, "Notes", name)
            XCTAssertEqual(reply["pid"] as? Int, 500, name)
            XCTAssertEqual(trees(), [.accessibilityTree(pid: 500, maxNodes: 400)], name)
        }
    }

    func testApplicationThatIsNotRunningIsAnsweredAsSuchAndNoTreeIsRead() {
        for name in ["Xcode", "Note", "Notes ", "com.apple"] {
            reset()
            assertRefused(ask("ax", ["app": name]), .appNotRunning, name)
            XCTAssertEqual(system.touches, [], name)
        }
    }

    func testNoFrontmostApplicationIsAppNotRunning() {
        system.front = nil
        assertRefused(ask("ax"), .appNotRunning)
        XCTAssertEqual(system.touches, [])
    }

    func testOfTwoProcessesWithTheNameTheFrontmostOneIsReadElseTheOldest() {
        let older = AppInfo(name: "Chrome", bundleID: "com.google.Chrome", pid: 700)
        let newer = AppInfo(name: "Chrome", bundleID: "com.google.Chrome", pid: 900)
        system.apps = [newer, older, Fixture.textEdit]
        XCTAssertEqual(ask("ax", ["app": "Chrome"])["pid"] as? Int, 700)
        system.front = newer
        XCTAssertEqual(ask("ax", ["app": "Chrome"])["pid"] as? Int, 900)
    }

    func testApplicationWithNoWindowHasANullWindow() {
        system.snapshot = AXSnapshot(window: nil, nodes: [], truncated: false)
        let reply = ask("ax")
        assertOK(reply)
        XCTAssertTrue(reply["window"] is NSNull)
        XCTAssertEqual(nodes(reply).count, 0)
    }

    func testWindowTitleIsCutAt200Characters() {
        system.snapshot = AXSnapshot(
            window: String(repeating: "w", count: 250), nodes: [], truncated: false
        )
        XCTAssertEqual(ask("ax")["window"] as? String, String(repeating: "w", count: 200))
    }

    func testRefsOfAnOlderAnswerAreForgotten() {
        system.elementFrames = [
            11: ScreenRect(x: 0, y: 0, width: 10, height: 10),
            12: ScreenRect(x: 100, y: 0, width: 10, height: 10),
            21: ScreenRect(x: 200, y: 0, width: 10, height: 10),
        ]
        readTree([button(11), button(12)])
        assertOK(act("click", ["ref": "a2"]))
        XCTAssertEqual(system.actions, [.postClick(ScreenPoint(x: 105, y: 5), .left, 1)])

        system.forgetCalls()
        readTree([button(21)])
        assertRefused(act("click", ["ref": "a2"]), .refUnknown)
        XCTAssertEqual(system.actions, [])
        assertOK(act("click", ["ref": "a1"]))
        XCTAssertEqual(
            system.actions, [.postClick(ScreenPoint(x: 205, y: 5), .left, 1)],
            "a1 is the first element of the new answer, not of the old one"
        )
    }

    func testEveryAnswerGoesByANameOfItsOwn() {
        var names: Set<String> = []
        for _ in 0..<20 {
            let name = readTree([button(11)])["outline"] as? String ?? ""
            XCTAssertNotNil(
                name.range(of: "^[0-9a-f]{16}$", options: .regularExpression), "<\(name)>"
            )
            names.insert(name)
        }
        XCTAssertEqual(names.count, 20, "the same tree read again is another answer")
    }

    func testRefOfAnOlderAnswerIsUnknownThoughTheNewestHasOneOfThatNumber() {
        system.elementFrames = [
            11: ScreenRect(x: 0, y: 0, width: 10, height: 10),
            21: ScreenRect(x: 200, y: 0, width: 10, height: 10),
        ]
        let older = readTree([button(11, title: "Cancel")])["outline"] as? String ?? ""
        let newest = readTree([button(21, title: "Delete")])["outline"] as? String ?? ""
        system.forgetCalls()

        assertRefused(act("click", ["ref": "a1", "outline": older]), .refUnknown)
        assertRefused(act("set_value", ["ref": "a1", "text": "x", "outline": older]), .refUnknown)
        let others = [Self.noOutline, "", newest.uppercased(), newest + "0", " " + newest]
        for name in others where name != newest {
            assertRefused(act("click", ["ref": "a1", "outline": name]), .refUnknown, "<\(name)>")
        }
        XCTAssertEqual(system.touches, [], "a ref of an older answer reaches no element")

        assertOK(act("click", ["ref": "a1", "outline": newest]))
        XCTAssertEqual(system.actions, [.postClick(ScreenPoint(x: 205, y: 5), .left, 1)])
    }

    func testReadThatFailsLeavesNoRefsBehind() {
        system.elementFrames[11] = ScreenRect(x: 0, y: 0, width: 10, height: 10)
        readTree([button(11)])
        system.treeError = .failed("The application did not answer.")
        assertRefused(ask("ax"), .internalError)
        system.treeError = nil
        assertRefused(act("click", ["ref": "a1"]), .refUnknown)
        XCTAssertEqual(system.actions, [])
    }

    func testWhatTheReadAnswersInsteadOfATreeBecomesTheContractsCode() {
        let table: [(SystemError, ErrorCode)] = [
            (.accessibilityMissing, .permissionMissingAccessibility),
            (.appGone, .appNotRunning),
            (.failed("The application did not answer."), .internalError),
        ]
        for (error, code) in table {
            reset()
            system.treeError = error
            assertRefused(ask("ax"), code, "\(error)")
        }
    }
}
