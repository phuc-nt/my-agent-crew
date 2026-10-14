import Foundation
import XCTest
@testable import DesktopHelperCore

/// The helper as its client meets it: a socket file, connections, lines. The machine behind it is
/// still the fake one.
final class SocketServerTests: XCTestCase {
    private var system: FakeSystem!
    private var folder = ""
    private var servers: [SocketServer] = []

    private struct NoShortFolder: Error, CustomStringConvertible {
        let description = "No temporary folder is short enough to hold a Unix socket path."
    }

    override func setUpWithError() throws {
        try super.setUpWithError()
        system = FakeSystem()
        folder = try Self.makeFolder()
    }

    override func tearDown() {
        system?.onCall = nil
        servers.forEach { $0.stop() }
        servers = []
        if !folder.isEmpty {
            // A folder a test closed to its owner cannot be emptied until it is opened again.
            chmod(folder, 0o700)
            try? FileManager.default.removeItem(atPath: folder)
        }
        system = nil
        super.tearDown()
    }

    /// A folder of the test's own, mode 0700, short enough to leave room for a socket's name.
    private static func makeFolder() throws -> String {
        let letters = Array("abcdefghijklmnopqrstuvwxyz0123456789")
        let name = "mac-" + String((0..<8).map { _ in letters.randomElement() ?? "x" })
        for base in [NSTemporaryDirectory(), "/tmp"] {
            let path = (base as NSString).appendingPathComponent(name)
            guard path.utf8.count + 40 <= Limits.maxSocketPathBytes else { continue }
            if mkdir(path, 0o700) == 0, chmod(path, 0o700) == 0 { return path }
        }
        throw NoShortFolder()
    }

    private var path: String { folder + "/sock" }

    @discardableResult
    private func serve(_ path: String) throws -> SocketServer {
        let server = SocketServer(path: path, system: system)
        servers.append(server)
        try server.start()
        return server
    }

    /// Why a server could not start; a failure of the test when it did.
    private func refusal(
        of server: SocketServer, file: StaticString = #filePath, line: UInt = #line
    ) -> SocketError? {
        do {
            try server.start()
            servers.append(server)
            XCTFail("the server started", file: file, line: line)
            return nil
        } catch let error as SocketError {
            return error
        } catch {
            XCTFail("\(error)", file: file, line: line)
            return nil
        }
    }

    private func connect(
        _ path: String, file: StaticString = #filePath, line: UInt = #line
    ) throws -> SocketClient {
        try XCTUnwrap(SocketClient(path: path), "nothing listens on \(path)", file: file, line: line)
    }

    private func object(
        _ reply: SocketClient.Reply, file: StaticString = #filePath, line: UInt = #line
    ) -> [String: Any] {
        guard case .line(let text) = reply else {
            XCTFail("no answer line: \(reply)", file: file, line: line)
            return [:]
        }
        let parsed = (try? JSONSerialization.jsonObject(with: Data(text.utf8))) as? [String: Any]
        XCTAssertNotNil(parsed, "not a JSON object: \(text.prefix(200))", file: file, line: line)
        return parsed ?? [:]
    }

    /// Sends one `state` request and holds the answer to it.
    private func assertAnswers(
        _ client: SocketClient, id: String = "1", file: StaticString = #filePath, line: UInt = #line
    ) {
        client.send("{\"id\":\"\(id)\",\"cmd\":\"state\"}\n")
        let answer = object(client.readLine(), file: file, line: line)
        XCTAssertEqual(answer["id"] as? String, id, file: file, line: line)
        XCTAssertEqual(answer["ok"] as? Bool, true, file: file, line: line)
        XCTAssertEqual(answer["protocol"] as? Int, 1, file: file, line: line)
    }

    private func mode(_ path: String) -> mode_t? {
        var info = stat()
        return lstat(path, &info) == 0 ? info.st_mode : nil
    }

    private func exists(_ path: String) -> Bool { mode(path) != nil }

    private func isUnsafeFolder(_ error: SocketError?) -> Bool {
        if case .unsafeFolder? = error { return true }
        return false
    }

    private func isInUse(_ error: SocketError?) -> Bool {
        if case .inUse? = error { return true }
        return false
    }

    // MARK: the folder

    func testMissingFolderIsMadeForItsOwnerOnlyWhateverTheUmask() throws {
        let before = umask(0)
        defer { umask(before) }
        let held = folder + "/held"
        try serve(held + "/sock")
        XCTAssertEqual(mode(held), S_IFDIR | 0o700)
        var info = stat()
        XCTAssertEqual(stat(held, &info), 0)
        XCTAssertEqual(info.st_uid, geteuid())
        try assertAnswers(connect(held + "/sock"))
    }

    func testFolderThatIsThereAndClosedToOthersIsUsedAsItIs() throws {
        try serve(path)
        XCTAssertEqual(mode(folder), S_IFDIR | 0o700)
        try assertAnswers(connect(path))
    }

    func testFolderOpenToGroupOrOthersIsRefusedAndLeftAsItWas() throws {
        let open: [mode_t] = [0o750, 0o705, 0o710, 0o701, 0o720, 0o702, 0o740, 0o704, 0o770, 0o707, 0o777]
        for bits in open {
            let held = folder + "/open-" + String(bits, radix: 8)
            XCTAssertEqual(mkdir(held, 0o700), 0)
            XCTAssertEqual(chmod(held, bits), 0)
            let error = refusal(of: SocketServer(path: held + "/sock", system: system))
            XCTAssertTrue(isUnsafeFolder(error), "\(String(bits, radix: 8)): \(String(describing: error))")
            XCTAssertEqual(
                error?.description, "The folder \(held) is open to group or others; make it 0700."
            )
            XCTAssertFalse(exists(held + "/sock"), "no socket is left in a folder others can enter")
            XCTAssertEqual(mode(held), S_IFDIR | bits, "the helper does not close the folder itself")
        }
    }

    func testFolderOfAnotherUserIsRefused() {
        let stranger = SocketServer(path: path, system: system, owner: geteuid() + 1)
        let error = refusal(of: stranger)
        XCTAssertTrue(isUnsafeFolder(error), String(describing: error))
        XCTAssertEqual(error?.description, "The folder \(folder) is not owned by the current user.")
        XCTAssertFalse(exists(path))
    }

    func testPlaceOfTheFolderThatIsAFileIsRefused() throws {
        let plain = folder + "/plain"
        try Data("keep".utf8).write(to: URL(fileURLWithPath: plain))
        let error = refusal(of: SocketServer(path: plain + "/sock", system: system))
        XCTAssertTrue(isUnsafeFolder(error), String(describing: error))
        XCTAssertEqual(try Data(contentsOf: URL(fileURLWithPath: plain)), Data("keep".utf8))
    }

    // MARK: the socket file

    func testSocketIsForItsOwnerOnlyWhateverTheUmask() throws {
        for mask: mode_t in [0, 0o022, 0o077] {
            let before = umask(mask)
            defer { umask(before) }
            let held = folder + "/mask-" + String(mask, radix: 8)
            XCTAssertEqual(mkdir(held, 0o700), 0)
            XCTAssertEqual(chmod(held, 0o700), 0)
            try serve(held + "/sock")
            XCTAssertEqual(mode(held + "/sock"), S_IFSOCK | 0o600, String(mask, radix: 8))
            XCTAssertEqual(umask(mask), mask, "the process's own umask is put back")
        }
    }

    func testSocketNothingAnswersOnIsReplaced() throws {
        let stale = try SocketSetup.makeListener(at: path, owner: geteuid())
        close(stale)
        XCTAssertEqual(mode(path), S_IFSOCK | 0o600, "the file outlives the helper that made it")
        XCTAssertNil(SocketClient(path: path), "and nothing answers on it")

        try serve(path)
        try assertAnswers(connect(path))
    }

    func testSocketAHelperAnswersOnIsNotReplaced() throws {
        try serve(path)
        let before = try connect(path)
        assertAnswers(before, id: "before")

        let second = SocketServer(path: path, system: system)
        let error = refusal(of: second)
        XCTAssertTrue(isInUse(error), String(describing: error))
        XCTAssertEqual(error?.description, "A helper already answers on \(path): one helper a socket.")

        second.stop()
        XCTAssertEqual(mode(path), S_IFSOCK | 0o600, "the helper that lost leaves the socket alone")
        assertAnswers(before, id: "still")
        try assertAnswers(connect(path), id: "after")
    }

    func testFileThatIsNotASocketIsLeftAlone() throws {
        try Data("keep me".utf8).write(to: URL(fileURLWithPath: path))
        let server = SocketServer(path: path, system: system)
        let error = refusal(of: server)
        XCTAssertTrue(isInUse(error), String(describing: error))
        server.stop()
        XCTAssertEqual(try Data(contentsOf: URL(fileURLWithPath: path)), Data("keep me".utf8))
    }

    func testFolderInThePlaceOfTheSocketIsLeftAlone() {
        XCTAssertEqual(mkdir(path, 0o700), 0)
        XCTAssertTrue(isInUse(refusal(of: SocketServer(path: path, system: system))))
        XCTAssertEqual(mode(path), S_IFDIR | 0o700)
    }

    // MARK: the path

    /// A socket path of exactly `bytes` bytes inside `holder`.
    private func longPath(in holder: String, bytes: Int) -> String {
        holder + "/" + String(repeating: "s", count: bytes - holder.utf8.count - 1)
    }

    func testPathOf103BytesIsServed() throws {
        let longest = longPath(in: folder, bytes: 103)
        XCTAssertEqual(longest.utf8.count, 103)
        try serve(longest)
        XCTAssertEqual(mode(longest), S_IFSOCK | 0o600)
        try assertAnswers(connect(longest))
    }

    func testPathOf104BytesIsRefusedBeforeAnythingIsMade() {
        let held = folder + "/never"
        let long = longPath(in: held, bytes: 104)
        XCTAssertEqual(long.utf8.count, 104)
        let error = refusal(of: SocketServer(path: long, system: system))
        XCTAssertEqual(error, .pathTooLong(bytes: 104))
        XCTAssertEqual(
            error?.description,
            "The socket path is 104 bytes; a Unix socket path on macOS holds at most 103."
        )
        XCTAssertFalse(exists(held), "not even the folder")

        let longer = longPath(in: folder, bytes: 300)
        XCTAssertEqual(refusal(of: SocketServer(path: longer, system: system)), .pathTooLong(bytes: 300))
    }

    func testPathIsMeasuredInBytesNotInCharacters() throws {
        let room = 103 - folder.utf8.count - 1
        let accented = folder + "/" + String(repeating: "é", count: room / 2 + 1)
        XCTAssertLessThan(accented.count, 103)
        XCTAssertGreaterThan(accented.utf8.count, 103)
        let error = refusal(of: SocketServer(path: accented, system: system))
        XCTAssertEqual(error, .pathTooLong(bytes: accented.utf8.count))
        XCTAssertFalse(exists(accented))

        let fits = folder + "/" + String(repeating: "é", count: 10)
        try serve(fits)
        try assertAnswers(connect(fits))
    }

    func testEmptyPathIsRefused() {
        guard case .failed? = refusal(of: SocketServer(path: "", system: system)) else {
            return XCTFail("an empty path is no place for a socket")
        }
    }

    // MARK: lines

    func testSeveralRequestsOnOneConnectionAreAnsweredInTheirOrder() throws {
        try serve(path)
        let client = try connect(path)
        for id in ["a", "b", "c"] {
            assertAnswers(client, id: id)
        }

        client.send("{\"id\":\"p1\",\"cmd\":\"state\"}\n{\"id\":\"p2\",\"cmd\":\"apps\"}\n{\"id\":\"p3\",\"cmd\":\"state\"}\n")
        XCTAssertEqual(object(client.readLine())["id"] as? String, "p1")
        let apps = object(client.readLine())
        XCTAssertEqual(apps["id"] as? String, "p2")
        XCTAssertNotNil(apps["apps"], "each line is answered as the command it names")
        XCTAssertEqual(object(client.readLine())["id"] as? String, "p3")
        XCTAssertEqual(client.readLine(timeout: 0.3), .timedOut, "one answer a request and no more")
    }

    func testRequestMayComeInPieces() throws {
        try serve(path)
        let client = try connect(path)
        client.send("{\"id\":\"sp")
        XCTAssertEqual(client.readLine(timeout: 0.3), .timedOut, "half a line is not answered")
        XCTAssertEqual(system.calls, [])
        client.send("lit\",\"cmd\":")
        client.send("\"state\"}")
        XCTAssertEqual(client.readLine(timeout: 0.3), .timedOut, "nor a line without its newline")
        client.send("\n{\"id\":\"next\",")
        XCTAssertEqual(object(client.readLine())["id"] as? String, "split")
        client.send("\"cmd\":\"state\"}\n")
        XCTAssertEqual(object(client.readLine())["id"] as? String, "next")
    }

    func testAnswerIsOneLineOfJSONEndedByOneNewline() throws {
        system.windowList = [
            WindowInfo(
                app: "TextEdit", pid: 4242, title: "line one\nline two\r\n\u{2028}end",
                bounds: ScreenRect(x: 0, y: 0, width: 100, height: 100), layer: 0
            ),
        ]
        try serve(path)
        let client = try connect(path)
        client.send("{\"id\":\"w\",\"cmd\":\"windows\"}\n")
        let answer = object(client.readLine())
        let windows = answer["windows"] as? [[String: Any]] ?? []
        XCTAssertEqual(windows.first?["title"] as? String, "line one\nline two\r\n\u{2028}end")
        assertAnswers(client, id: "after")
    }

    func testUnknownCommandAndBadLinesAreAnsweredAndTheConnectionStays() throws {
        try serve(path)
        let client = try connect(path)

        client.send("{\"id\":\"1\",\"cmd\":\"dance\"}\n")
        let unknown = object(client.readLine())
        XCTAssertEqual(unknown["id"] as? String, "1")
        XCTAssertEqual(unknown["ok"] as? Bool, false)
        XCTAssertEqual(unknown["error"] as? String, "unknown_command")

        for line in ["not json", "", "[1,2]", "{\"cmd\":\"state\"}", "{\"id\":7,\"cmd\":\"state\"}"] {
            client.send(line + "\n")
            let refused = object(client.readLine())
            XCTAssertEqual(refused["id"] as? String, "", "<\(line)>")
            XCTAssertEqual(refused["ok"] as? Bool, false, "<\(line)>")
            XCTAssertEqual(refused["error"] as? String, "bad_request", "<\(line)>")
        }

        client.send("{\"id\":\"2\"}\n")
        let nameless = object(client.readLine())
        XCTAssertEqual(nameless["id"] as? String, "2")
        XCTAssertEqual(nameless["error"] as? String, "bad_request")
        XCTAssertEqual(system.calls, [], "none of those asked the machine anything")

        assertAnswers(client, id: "3")
    }

    func testLineOverTheLimitIsAnsweredBadRequestAndTheConnectionIsClosed() throws {
        try serve(path)
        let client = try connect(path)
        // One byte over, with no newline: the helper has read all of it when it answers.
        XCTAssertTrue(client.send([UInt8](repeating: 0x78, count: 65_537)))
        let answer = object(client.readLine())
        XCTAssertEqual(Set(answer.keys), ["id", "ok", "error", "detail"])
        XCTAssertEqual(answer["id"] as? String, "")
        XCTAssertEqual(answer["ok"] as? Bool, false)
        XCTAssertEqual(answer["error"] as? String, "bad_request")
        XCTAssertEqual(answer["detail"] as? String, "The request line is over 64 KiB.")
        XCTAssertEqual(client.readLine(), .closed)
        XCTAssertEqual(system.calls, [])

        try assertAnswers(connect(path), id: "another connection is served as before")
    }

    func testLineOverTheLimitIsNotAnsweredAsTheRequestItHolds() throws {
        try serve(path)
        let client = try connect(path)
        let padding = String(repeating: "x", count: 70_000)
        client.send("{\"id\":\"big\",\"cmd\":\"state\",\"pad\":\"\(padding)\"}\n{\"id\":\"2\",\"cmd\":\"state\"}\n")
        let answer = object(client.readLine())
        XCTAssertEqual(answer["id"] as? String, "")
        XCTAssertEqual(answer["error"] as? String, "bad_request")
        XCTAssertEqual(client.readLine(), .closed, "the request after it on the connection is not read")
        XCTAssertEqual(system.calls, [])
    }

    func testRequestBeforeALineOverTheLimitIsStillAnswered() throws {
        try serve(path)
        let client = try connect(path)
        var bytes = Array("{\"id\":\"first\",\"cmd\":\"state\"}\n".utf8)
        bytes += [UInt8](repeating: 0x78, count: 65_537)
        XCTAssertTrue(client.send(bytes))
        XCTAssertEqual(object(client.readLine())["id"] as? String, "first")
        XCTAssertEqual(object(client.readLine())["error"] as? String, "bad_request")
        XCTAssertEqual(client.readLine(), .closed)
    }

    func testLineOfExactly64KiBIsARequestLikeAnyOther() throws {
        try serve(path)
        let client = try connect(path)
        let head = "{\"id\":\"full\",\"cmd\":\"state\",\"pad\":\""
        let tail = "\"}"
        let line = head + String(repeating: "x", count: 65_536 - head.utf8.count - tail.utf8.count) + tail
        XCTAssertEqual(line.utf8.count, 65_536)
        XCTAssertTrue(client.send(line + "\n"))
        let answer = object(client.readLine())
        XCTAssertEqual(answer["id"] as? String, "full")
        XCTAssertEqual(answer["ok"] as? Bool, true)
        assertAnswers(client, id: "after")
    }

    // MARK: connections

    func testConnectionOfAnotherUserIsClosedWithoutAnAnswer() throws {
        let server = SocketServer(path: path, system: system)
        server.allowedPeer = geteuid() + 1
        servers.append(server)
        try server.start()

        let client = try connect(path)
        client.send("{\"id\":\"1\",\"cmd\":\"state\"}\n")
        XCTAssertEqual(client.readLine(), .closed)
        XCTAssertEqual(system.calls, [], "a stranger's request is not read")

        let again = try connect(path)
        XCTAssertEqual(again.readLine(), .closed, "and the helper goes on listening")
    }

    func testRequestOfASecondConnectionWaitsForTheFirst() throws {
        let entered = DispatchSemaphore(value: 0)
        let release = DispatchSemaphore(value: 0)
        defer { release.signal() }
        var held = false
        // Called on the helper's one request queue only, so `held` has one writer.
        system.onCall = { call in
            guard call == .isLocked, !held else { return }
            held = true
            entered.signal()
            release.wait()
        }
        try serve(path)
        let first = try connect(path)
        let second = try connect(path)

        first.send("{\"id\":\"first\",\"cmd\":\"state\"}\n")
        XCTAssertEqual(entered.wait(timeout: .now() + 10), .success, "the first request is being served")
        second.send("{\"id\":\"second\",\"cmd\":\"state\"}\n")
        XCTAssertEqual(second.readLine(timeout: 0.5), .timedOut, "the second waits")
        XCTAssertEqual(first.readLine(timeout: 0.1), .timedOut)
        XCTAssertEqual(
            system.calls.filter { $0 == .isLocked }.count, 1, "nothing of the second was begun"
        )

        release.signal()
        XCTAssertEqual(object(first.readLine())["id"] as? String, "first")
        XCTAssertEqual(object(second.readLine())["id"] as? String, "second")
        XCTAssertEqual(system.calls.filter { $0 == .isLocked }.count, 2)
    }

    func testWhatTheHelperLearnedOnOneConnectionCountsOnAnother() throws {
        try serve(path)
        let eyes = try connect(path)
        eyes.send("{\"id\":\"s\",\"cmd\":\"screenshot\",\"max_px\":320}\n")
        let shot = object(eyes.readLine())
        let frame = try XCTUnwrap(shot["frame_id"] as? String)
        XCTAssertNotNil(shot["png_base64"] as? String)

        let hands = try connect(path)
        let click: [String: Any] = [
            "id": "c", "cmd": "act", "kind": "click", "app": "TextEdit", "frame_id": frame,
            "x": 160, "y": 90,
        ]
        var line = try JSONSerialization.data(withJSONObject: click)
        line.append(0x0A)
        hands.send([UInt8](line))
        let done = object(hands.readLine())
        XCTAssertEqual(done["ok"] as? Bool, true, "\(done["error"] ?? "") \(done["detail"] ?? "")")
        XCTAssertEqual(done["effect"] as? String, "posted")
        XCTAssertEqual(system.actions, [.postClick(ScreenPoint(x: 960, y: 540), .left, 1)])
    }

    func testClientThatHangsUpInTheMiddleOfALineLeavesTheHelperServing() throws {
        try serve(path)
        let gone = try connect(path)
        gone.send("{\"id\":\"1\",\"cmd\":\"sta")
        gone.hangUp()

        let silent = try connect(path)
        silent.hangUp()

        let client = try connect(path)
        assertAnswers(client)
        XCTAssertEqual(system.calls.filter { $0 == .isLocked }.count, 1, "half a request is no request")
    }

    func testClientThatHangsUpBeforeItsAnswerDoesNotEndTheHelper() throws {
        try serve(path)
        for _ in 0..<20 {
            let hasty = try connect(path)
            hasty.send("{\"id\":\"1\",\"cmd\":\"state\"}\n{\"id\":\"2\",\"cmd\":\"state\"}\n")
            hasty.hangUp()
        }
        try assertAnswers(connect(path))
    }

    func testABurstOfConnectionsTheHelperHasNotTakenYetIsNotRefused() throws {
        // Nothing accepts here, as when the helper is slow to: every connection waits in the queue.
        let listener = try SocketSetup.makeListener(at: path, owner: geteuid())
        defer { close(listener) }

        let waiting = try (1...64).map { _ in try connect(path) }

        XCTAssertEqual(waiting.count, 64)
    }

    // MARK: stopping

    func testStopRemovesTheSocketAndEndsEveryConnection() throws {
        let server = try serve(path)
        let one = try connect(path)
        let two = try connect(path)
        assertAnswers(one)
        assertAnswers(two)

        server.stop()
        XCTAssertFalse(exists(path), "the socket file is gone")
        XCTAssertEqual(one.readLine(), .closed)
        XCTAssertEqual(two.readLine(), .closed)
        XCTAssertNil(SocketClient(path: path), "nothing listens any more")
        XCTAssertTrue(exists(folder), "the folder is the owner's to keep")
    }

    func testStoppingTwiceIsHarmlessAndANewHelperCanTakeThePlace() throws {
        let first = try serve(path)
        first.stop()
        first.stop()

        try serve(path)
        let client = try connect(path)
        assertAnswers(client)
        first.stop()
        XCTAssertTrue(exists(path), "a helper that stopped does not remove its successor's socket")
        assertAnswers(client, id: "still")
    }

    func testHelperThatNeverStartedStopsWithoutTouchingThePath() throws {
        try Data("keep".utf8).write(to: URL(fileURLWithPath: path))
        SocketServer(path: path, system: system).stop()
        XCTAssertEqual(try Data(contentsOf: URL(fileURLWithPath: path)), Data("keep".utf8))
    }
}
