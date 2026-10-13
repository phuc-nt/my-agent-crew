import CoreGraphics
import Foundation
import ImageIO
import XCTest
@testable import DesktopHelperCore

/// The small parts the commands are made of, each on its own.
final class HelperPiecesTests: XCTestCase {
    private let empty = "e3b0c44298fc1c14"

    private func refusal(
        _ work: @autoclosure () throws -> Any, file: StaticString = #filePath, line: UInt = #line
    ) -> Refusal? {
        do {
            _ = try work()
            XCTFail("nothing was refused", file: file, line: line)
            return nil
        } catch {
            XCTAssertTrue(error is Refusal, "\(error)", file: file, line: line)
            return error as? Refusal
        }
    }

    // MARK: frame ids

    func testFrameIDIsTheStartOfTheSHA256ThenTheSizeThenTheDisplay() {
        XCTAssertEqual(
            FrameID.make(pixels: Data(), width: 3, height: 2, display: 7), "\(empty)-3x2-7"
        )
        XCTAssertEqual(
            FrameID.make(pixels: Data("abc".utf8), width: 1456, height: 819, display: 4_294_967_295),
            "ba7816bf8f01cfea-1456x819-4294967295"
        )
    }

    func testFrameIDChangesWithAnyByteOfThePictureItsSizeAndItsDisplay() {
        let pixels = Data(repeating: 0x40, count: 64)
        var other = pixels
        other[63] = 0x41
        let ids = [
            FrameID.make(pixels: pixels, width: 4, height: 4, display: 1),
            FrameID.make(pixels: other, width: 4, height: 4, display: 1),
            FrameID.make(pixels: pixels, width: 8, height: 2, display: 1),
            FrameID.make(pixels: pixels, width: 4, height: 4, display: 2),
        ]
        XCTAssertEqual(Set(ids).count, 4)
        XCTAssertEqual(ids[0], FrameID.make(pixels: pixels, width: 4, height: 4, display: 1))
    }

    func testFrameIDIsReadBackIntoItsParts() {
        XCTAssertEqual(
            FrameID.parse("\(empty)-3x2-7"),
            FrameID.Parts(hash: empty, width: 3, height: 2, display: 7)
        )
        XCTAssertEqual(FrameID.parse("\(empty)-1456x819-4294967295")?.display, 4_294_967_295)
        XCTAssertEqual(FrameID.parse("\(empty)-3x2-0")?.display, 0)
        XCTAssertEqual(FrameID.parse("\(empty)-3x2-01")?.display, 1, "read, and then never the id held")
        let made = FrameID.make(pixels: Data([1, 2, 3]), width: 320, height: 180, display: 69_734_112)
        XCTAssertEqual(FrameID.parse(made)?.width, 320)
        XCTAssertEqual(FrameID.parse(made)?.height, 180)
        XCTAssertEqual(FrameID.parse(made)?.display, 69_734_112)
    }

    func testTextThatIsNotAFrameIDIsNotRead() {
        let wrong = [
            "", "abc", empty, "\(empty)-3x2", "\(empty)-3x2-", "\(empty)--7", "-3x2-7",
            "E3B0C44298FC1C14-3x2-7", "e3b0c44298fc1c1-3x2-7", "e3b0c44298fc1c144-3x2-7",
            "e3b0c44298fc1c1g-3x2-7", "\(empty)-3X2-7", "\(empty)-3x2x1-7", "\(empty)-3-7",
            "\(empty)-0x2-7", "\(empty)-3x0-7", "\(empty)-x2-7", "\(empty)-3x-7",
            "\(empty)-3x2--7", "\(empty)-3x2-7-", "\(empty)-3x2-7-1", "\(empty)-3x2-4294967296",
            "\(empty)-3x2-99999999999", "\(empty)-12345678901x2-7", "\(empty)-3x2-seven",
            "\(empty)-3x2-7 ", " \(empty)-3x2-7", "\(empty)- 3x2-7", "\(empty)-3x2-+7",
            "\(empty)-3x2-٧", "\(empty)-3.0x2-7", "\(empty)-3x2-7\n", "\(empty)_3x2_7",
        ]
        for text in wrong {
            XCTAssertNil(FrameID.parse(text), "<\(text)>")
        }
    }

    // MARK: frames

    private func frame(
        _ pixels: UInt8, display: UInt32 = 1, at time: TimeInterval = 100,
        bounds: ScreenRect = ScreenRect(x: 0, y: 0, width: 1920, height: 1080)
    ) -> Frame {
        let id = FrameID.make(pixels: Data([pixels]), width: 320, height: 180, display: display)
        return Frame(
            id: id, display: display, takenAt: time, width: 320, height: 180, displayBounds: bounds
        )
    }

    func testStoreGivesBackTheLastFrameOfADisplayAndNoOlderOne() throws {
        var store = FrameStore()
        let first = frame(1)
        let second = frame(2, at: 150)
        store.remember(first)
        XCTAssertEqual(try store.frame(first.id, now: 100), first)

        store.remember(second)
        XCTAssertEqual(try store.frame(second.id, now: 150), second)
        let old = refusal(try store.frame(first.id, now: 150))
        XCTAssertEqual(old?.code, .frameMismatch)
        XCTAssertEqual(
            old?.detail, "That is not the last frame captured of display 1; take a new screenshot."
        )

        store.remember(first)
        XCTAssertEqual(try store.frame(first.id, now: 150), first, "the same picture again is the last")
        XCTAssertEqual(refusal(try store.frame(second.id, now: 150))?.code, .frameMismatch)
    }

    func testStoreKeepsAFrameFor300SecondsAndNotAMomentMore() throws {
        var store = FrameStore()
        let taken = frame(1, at: 1_000)
        store.remember(taken)
        XCTAssertEqual(try store.frame(taken.id, now: 1_000), taken)
        XCTAssertEqual(try store.frame(taken.id, now: 1_299.9), taken)
        XCTAssertEqual(try store.frame(taken.id, now: 1_300), taken)
        let late = refusal(try store.frame(taken.id, now: 1_300.001))
        XCTAssertEqual(late?.code, .frameMismatch)
        XCTAssertEqual(late?.detail, "That frame is over 300 seconds old; take a new screenshot.")
        XCTAssertEqual(refusal(try store.frame(taken.id, now: 99_999))?.code, .frameMismatch)
    }

    func testStoreKeepsOneFrameForEachDisplay() throws {
        var store = FrameStore()
        let main = frame(1, display: 1)
        let side = frame(1, display: 2, bounds: ScreenRect(x: 1920, y: -200, width: 2560, height: 1440))
        XCTAssertNotEqual(main.id, side.id)
        store.remember(main)
        store.remember(side)
        XCTAssertEqual(try store.frame(main.id, now: 100), main)
        XCTAssertEqual(try store.frame(side.id, now: 100), side)

        let third = FrameID.make(pixels: Data([1]), width: 320, height: 180, display: 3)
        XCTAssertEqual(
            refusal(try store.frame(third, now: 100))?.detail,
            "That is not the last frame captured of display 3; take a new screenshot."
        )
    }

    func testStoreSaysSoOfTextThatIsNoFrameID() {
        var store = FrameStore()
        let held = frame(1)
        store.remember(held)
        for text in ["", "latest", held.id.uppercased(), held.id + " ", "\(held.id)-1"] {
            let refused = refusal(try store.frame(text, now: 100))
            XCTAssertEqual(refused?.code, .frameMismatch, "<\(text)>")
            XCTAssertEqual(refused?.detail, "That is not a frame id the helper gave out.", "<\(text)>")
        }
        let padded = String(held.id.dropLast()) + "01"
        XCTAssertEqual(
            refusal(try store.frame(padded, now: 100))?.detail,
            "That is not the last frame captured of display 1; take a new screenshot.",
            "another way of writing the display is not the id the helper gave"
        )
        XCTAssertEqual(refusal(try FrameStore().frame(held.id, now: 100))?.code, .frameMismatch)
    }

    func testPixelOfAPictureIsAPointOfItsDisplay() {
        let side = Frame(
            id: "x", display: 2, takenAt: 0, width: 1456, height: 819,
            displayBounds: ScreenRect(x: 1920, y: -200, width: 2560, height: 1440)
        )
        XCTAssertEqual(side.point(x: 0, y: 0), ScreenPoint(x: 1920, y: -200))
        XCTAssertEqual(side.point(x: 728, y: 409.5), ScreenPoint(x: 3200, y: 520))
        XCTAssertEqual(side.point(x: 91, y: 91), ScreenPoint(x: 2080, y: -40))

        let left = Frame(
            id: "x", display: 3, takenAt: 0, width: 200, height: 100,
            displayBounds: ScreenRect(x: -800, y: 300, width: 800, height: 400)
        )
        XCTAssertEqual(left.point(x: 100, y: 50), ScreenPoint(x: -400, y: 500))
        XCTAssertEqual(left.point(x: 199.5, y: 99.5), ScreenPoint(x: -2, y: 698))
    }

    func testPixelOutsideThePictureIsNoPoint() {
        let small = frame(1)
        XCTAssertNotNil(small.point(x: 0, y: 0))
        XCTAssertNotNil(small.point(x: 319.999, y: 179.999))
        let outside: [(Double, Double)] = [
            (320, 0), (0, 180), (320, 180), (-0.001, 0), (0, -0.001), (-1, -1), (1e9, 1), (1, 1e9),
            (.nan, 1), (1, .nan), (.infinity, 1), (1, -.infinity),
        ]
        for (x, y) in outside {
            XCTAssertNil(small.point(x: x, y: y), "\(x), \(y)")
        }
    }

    // MARK: picture size

    private func size(_ width: Double, _ height: Double, scale: Double, maxPx: Int) -> PictureSize {
        let display = DisplayInfo(
            id: 1, bounds: ScreenRect(x: 0, y: 0, width: width, height: height), scale: scale,
            isMain: true
        )
        return PictureSize.fit(display: display, maxPx: maxPx)
    }

    func testPictureIsScaledDownUntilItsLongerSideFits() {
        XCTAssertEqual(size(1920, 1080, scale: 2, maxPx: 1456), PictureSize(width: 1456, height: 819))
        XCTAssertEqual(size(1080, 1920, scale: 2, maxPx: 1456), PictureSize(width: 819, height: 1456))
        XCTAssertEqual(size(1512, 982, scale: 2, maxPx: 1456), PictureSize(width: 1456, height: 946))
        XCTAssertEqual(size(1920, 1080, scale: 2, maxPx: 320), PictureSize(width: 320, height: 180))
        XCTAssertEqual(size(1920, 1080, scale: 2, maxPx: 2000), PictureSize(width: 2000, height: 1125))
        XCTAssertEqual(size(2560, 1440, scale: 1, maxPx: 1456), PictureSize(width: 1456, height: 819))
        XCTAssertEqual(size(1000, 1000, scale: 1, maxPx: 320), PictureSize(width: 320, height: 320))
    }

    func testPictureIsNeverMadeLargerThanTheDisplay() {
        XCTAssertEqual(size(800, 600, scale: 1, maxPx: 1456), PictureSize(width: 800, height: 600))
        XCTAssertEqual(size(1456, 900, scale: 1, maxPx: 1456), PictureSize(width: 1456, height: 900))
        XCTAssertEqual(size(1457, 900, scale: 1, maxPx: 1456), PictureSize(width: 1456, height: 899))
        XCTAssertEqual(size(640, 480, scale: 2, maxPx: 2000), PictureSize(width: 1280, height: 960))
        XCTAssertEqual(size(100, 50, scale: 1, maxPx: 320), PictureSize(width: 100, height: 50))
    }

    func testPictureOfADisplayThatMakesNoSenseStillHasASize() {
        XCTAssertEqual(size(0, 0, scale: 2, maxPx: 320), PictureSize(width: 1, height: 1))
        XCTAssertEqual(size(1920, 1080, scale: 0, maxPx: 320), PictureSize(width: 1, height: 1))
        XCTAssertEqual(size(1920, 1080, scale: .nan, maxPx: 320), PictureSize(width: 1, height: 1))
        XCTAssertEqual(size(-5, -5, scale: 1, maxPx: 320), PictureSize(width: 1, height: 1))
        XCTAssertEqual(size(5000, 1, scale: 1, maxPx: 320), PictureSize(width: 320, height: 1))
        let huge = size(.infinity, 1080, scale: 1, maxPx: 2000)
        XCTAssertEqual(huge, PictureSize(width: 1, height: 1080), "a side that is no number counts as 1")
        let wide = size(1e9, 1e9, scale: 1, maxPx: 2000)
        XCTAssertEqual(wide, PictureSize(width: 2000, height: 2000))
    }

    // MARK: applications

    func testApplicationIsTheOneMeantByItsNameOrItsBundleID() {
        let app = Fixture.textEdit
        for wanted in ["TextEdit", "textedit", "TEXTEDIT", "com.apple.TextEdit", "COM.APPLE.TEXTEDIT"] {
            XCTAssertTrue(AppMatch.matches(wanted, app), wanted)
        }
        let others = [
            "", " ", "Text", "TextEdit ", " TextEdit", "TextEdit.app", "Text Edit", "apple.TextEdit",
            "com.apple", "com.apple.TextEdit.helper", "4242", "*", "Notes",
        ]
        for wanted in others {
            XCTAssertFalse(AppMatch.matches(wanted, app), "<\(wanted)>")
        }
    }

    func testApplicationNameIsComparedWithItsAccents() {
        let notes = AppInfo(name: "Ghi chú", bundleID: "com.example.GhiChu", pid: 7)
        XCTAssertTrue(AppMatch.matches("GHI CHÚ", notes))
        XCTAssertTrue(AppMatch.matches("ghi chu\u{301}", notes), "the same letters written another way")
        XCTAssertFalse(AppMatch.matches("Ghi chu", notes))
    }

    func testApplicationWithNoBundleIDIsNotMeantByAnEmptyName() {
        let bare = AppInfo(name: "Ghost", bundleID: "", pid: 9)
        XCTAssertFalse(AppMatch.matches("", bare))
        XCTAssertTrue(AppMatch.matches("ghost", bare))
        let nameless = AppInfo(name: "", bundleID: "com.example.tool", pid: 10)
        XCTAssertFalse(AppMatch.matches("", nameless))
        XCTAssertTrue(AppMatch.matches("com.example.tool", nameless))
    }

    func testOfSeveralProcessesTheFrontmostIsMeantElseTheOldest() {
        let old = AppInfo(name: "Code", bundleID: "com.example.code", pid: 100)
        let new = AppInfo(name: "Code", bundleID: "com.example.code", pid: 900)
        let other = AppInfo(name: "Mail", bundleID: "com.example.mail", pid: 50)
        let all = [new, other, old]
        XCTAssertEqual(AppMatch.find("code", among: all, front: new), new)
        XCTAssertEqual(AppMatch.find("code", among: all, front: other), old)
        XCTAssertEqual(AppMatch.find("code", among: all, front: nil), old)
        XCTAssertEqual(AppMatch.find("com.example.mail", among: all, front: new), other)
        XCTAssertNil(AppMatch.find("Xcode", among: all, front: new))
        XCTAssertNil(AppMatch.find("code", among: [], front: nil))
        XCTAssertEqual(
            AppMatch.find("code", among: [], front: new), new,
            "the frontmost application is running whatever the list says"
        )
    }

    // MARK: text

    func testCutKeepsAtMostThatManyCharacters() {
        let exact = String(repeating: "a", count: 200)
        XCTAssertEqual(TextTools.cut(""), "")
        XCTAssertEqual(TextTools.cut("short"), "short")
        XCTAssertEqual(TextTools.cut(exact), exact)
        XCTAssertEqual(TextTools.cut(exact + "b"), exact)
        XCTAssertEqual(TextTools.cut(String(repeating: "é", count: 500)).unicodeScalars.count, 200)
        XCTAssertEqual(TextTools.cut("abcdef", to: 3), "abc")
        XCTAssertEqual(TextTools.cut("abcdef", to: 0), "")
        XCTAssertEqual(TextTools.cut("abc", to: 3), "abc")
        XCTAssertEqual(Limits.maxFieldCharacters, 200)
    }

    func testCutCountsScalarsAndNeverEndsInsideWhatReadsAsOneCharacter() {
        let flags = "🇻🇳🇯🇵🇺🇸"
        XCTAssertEqual(TextTools.cut(flags, to: 6), flags)
        XCTAssertEqual(TextTools.cut(flags, to: 5), "🇻🇳🇯🇵")
        XCTAssertEqual(TextTools.cut(flags, to: 4), "🇻🇳🇯🇵")
        XCTAssertEqual(TextTools.cut(flags, to: 3), "🇻🇳")
        XCTAssertEqual(TextTools.cut(flags, to: 1), "")

        let accented = "e\u{301}e\u{301}e\u{301}"
        XCTAssertEqual(Array(TextTools.cut(accented, to: 3).unicodeScalars), Array("e\u{301}".unicodeScalars))
        XCTAssertEqual(Array(TextTools.cut(accented, to: 4).unicodeScalars).count, 4)

        let family = "👨‍👩‍👧‍👦"
        XCTAssertEqual(family.unicodeScalars.count, 7)
        XCTAssertEqual(TextTools.cut("ab" + family + "cd", to: 8), "ab")
        XCTAssertEqual(TextTools.cut("ab" + family + "cd", to: 9), "ab" + family)
        XCTAssertEqual(TextTools.cut("ab" + family + "cd", to: 10), "ab" + family + "c")

        let long = String(repeating: "🇻🇳", count: 150)
        XCTAssertEqual(TextTools.cut(long).unicodeScalars.count, 200)
        XCTAssertEqual(TextTools.cut(long + "x").unicodeScalars.count, 200)
        XCTAssertEqual(TextTools.cut("x" + long).unicodeScalars.count, 199, "one flag short, not half a flag")
    }

    func testTypingChunksAreAtMost20UTF16UnitsAndJoinToTheText() {
        XCTAssertEqual(TextTools.typingChunks(""), [])
        XCTAssertEqual(TextTools.typingChunks("a"), ["a"])
        let twenty = String(repeating: "a", count: 20)
        XCTAssertEqual(TextTools.typingChunks(twenty), [twenty])
        XCTAssertEqual(TextTools.typingChunks(twenty + "b"), [twenty, "b"])
        XCTAssertEqual(TextTools.typingChunks("abcdef", limit: 4), ["abcd", "ef"])

        let faces = String(repeating: "😀", count: 11)
        XCTAssertEqual(TextTools.typingChunks(faces), [String(repeating: "😀", count: 10), "😀"])
        let straddling = String(repeating: "a", count: 19) + "😀b"
        XCTAssertEqual(
            TextTools.typingChunks(straddling), [String(repeating: "a", count: 19), "😀b"],
            "a pair of surrogates is never split"
        )
    }

    func testCharacterLongerThanAChunkIsSplitBetweenItsScalars() {
        let stacked = "e" + String(repeating: "\u{301}", count: 30)
        XCTAssertEqual(stacked.count, 1)
        let pieces = TextTools.typingChunks("ab" + stacked + "cd")
        XCTAssertEqual(pieces.count, 4)
        XCTAssertEqual(pieces.first, "ab")
        XCTAssertEqual(pieces.last, "cd")
        XCTAssertEqual(pieces.map { $0.utf16.count }, [2, 20, 11, 2])
        XCTAssertEqual(
            pieces.flatMap { Array($0.unicodeScalars) }, Array(("ab" + stacked + "cd").unicodeScalars)
        )

        let flag = TextTools.typingChunks("🇻🇳", limit: 3)
        XCTAssertEqual(flag.map { Array($0.unicodeScalars).count }, [1, 1])
        XCTAssertEqual(flag.map { $0.utf16.count }, [2, 2], "each half is a whole pair of surrogates")
        XCTAssertEqual(flag.flatMap { Array($0.unicodeScalars) }, Array("🇻🇳".unicodeScalars))
    }

    func testTypingChunksLoseNothingOfAnyText() {
        let texts = [
            "Tiếng Việt có dấu: ăâđêôơư ĂÂĐÊÔƠƯ, và một câu đủ dài để phải chia nhiều lần.",
            String(repeating: "👨‍👩‍👧‍👦", count: 9), String(repeating: "🇻🇳", count: 33),
            "line\nline\r\nline\ttab", String(repeating: "z", count: 2000),
            "a" + String(repeating: "\u{301}", count: 100) + "b",
        ]
        for text in texts {
            for limit in [1, 2, 3, 7, 20, 64] {
                let pieces = TextTools.typingChunks(text, limit: limit)
                XCTAssertEqual(
                    pieces.flatMap { Array($0.unicodeScalars) }, Array(text.unicodeScalars),
                    "limit \(limit)"
                )
                // One scalar outside the first plane is two units, so a limit of 1 cannot hold it.
                let most = max(limit, 2)
                XCTAssertTrue(pieces.allSatisfy { !$0.isEmpty && $0.utf16.count <= most }, "limit \(limit)")
            }
        }
    }

    // MARK: numbers on the wire

    func testSizesAndPlacesAreWrittenAsWholeNumbers() {
        XCTAssertEqual(Shape.whole(1.4), .int(1))
        XCTAssertEqual(Shape.whole(1.5), .int(2))
        XCTAssertEqual(Shape.whole(-200.4), .int(-200))
        XCTAssertEqual(Shape.whole(-0.5), .int(-1))
        XCTAssertEqual(Shape.whole(0), .int(0))
        XCTAssertEqual(Shape.whole(.nan), .int(0))
        XCTAssertEqual(Shape.whole(.infinity), .int(0))
        XCTAssertEqual(Shape.whole(1e300), .int(1_000_000_000_000))
        XCTAssertEqual(Shape.whole(-1e300), .int(-1_000_000_000_000))
        XCTAssertEqual(
            Shape.rect(ScreenRect(x: 1920, y: -200.2, width: 2560.5, height: 1439.6)),
            .array([.int(1920), .int(-200), .int(2561), .int(1440)])
        )
    }

    func testRatiosAreWrittenToFourDecimals() {
        XCTAssertEqual(Shape.ratio(1456.0 / 3840.0), .double(0.3792))
        XCTAssertEqual(Shape.ratio(1.23456), .double(1.2346))
        XCTAssertEqual(Shape.ratio(2), .double(2))
        XCTAssertEqual(Shape.ratio(2).encoded(), "2.0", "a ratio is a fraction on the wire")
        XCTAssertEqual(Shape.ratio(1.0 / 3.0).encoded(), "0.3333")
        XCTAssertEqual(Shape.ratio(.nan), .double(0))
        XCTAssertEqual(Shape.ratio(-.infinity), .double(0))
    }

    func testFrontmostApplicationIsAnObjectOrNull() {
        XCTAssertEqual(Shape.frontmost(nil), .null)
        XCTAssertEqual(
            Shape.frontmost(Fixture.textEdit).encoded(),
            #"{"app":"TextEdit","bundle_id":"com.apple.TextEdit","pid":4242}"#
        )
    }

    // MARK: lines

    private func bytes(_ text: String) -> [UInt8] { Array(text.utf8) }
    private func line(_ text: String) -> LineReader.Event { .line(Data(text.utf8)) }

    func testReaderCutsTheStreamAtEveryNewline() {
        var reader = LineReader()
        XCTAssertEqual(reader.feed(bytes("abc\n")), [line("abc")])
        XCTAssertEqual(reader.feed(bytes("one\ntwo\nthree\n")), [line("one"), line("two"), line("three")])
        XCTAssertEqual(reader.feed(bytes("\n")), [line("")], "an empty line is a line")
        XCTAssertEqual(reader.feed(bytes("\n\n")), [line(""), line("")])
        XCTAssertEqual(reader.feed([]), [])
    }

    func testReaderHoldsAHalfLineUntilItsNewlineComes() {
        var reader = LineReader()
        XCTAssertEqual(reader.feed(bytes("ab")), [])
        XCTAssertEqual(reader.feed(bytes("c\nde")), [line("abc")])
        XCTAssertEqual(reader.feed(bytes("")), [])
        XCTAssertEqual(reader.feed(bytes("f")), [])
        XCTAssertEqual(reader.feed(bytes("\ngh\ni")), [line("def"), line("gh")])
        XCTAssertEqual(reader.feed(bytes("\n")), [line("i")])

        var slow = LineReader()
        var events: [LineReader.Event] = []
        for byte in bytes("{\"id\":\"1\"}\n{\"id\":\"2\"}\n") {
            events += slow.feed([byte])
        }
        XCTAssertEqual(events, [line("{\"id\":\"1\"}"), line("{\"id\":\"2\"}")])
    }

    func testReaderCountsALineWithoutItsNewline() {
        var exact = LineReader(limit: 8)
        XCTAssertEqual(exact.feed(bytes("12345678\n")), [line("12345678")])
        XCTAssertEqual(exact.feed(bytes("12345678")), [], "eight bytes may still be a whole line")
        XCTAssertEqual(exact.feed(bytes("\n")), [line("12345678")])

        var over = LineReader(limit: 8)
        XCTAssertEqual(over.feed(bytes("123456789\n")), [.overflow])
    }

    func testReaderNoticesALineOverTheLimitBeforeItsNewlineComes() {
        var reader = LineReader(limit: 8)
        XCTAssertEqual(reader.feed(bytes("1234")), [])
        XCTAssertEqual(reader.feed(bytes("5678")), [])
        XCTAssertEqual(reader.feed(bytes("9")), [.overflow])
    }

    func testReaderGivesTheLinesBeforeTheOneThatIsTooLongAndNothingAfterIt() {
        var reader = LineReader(limit: 8)
        XCTAssertEqual(reader.feed(bytes("ok\nfine\n123456789")), [line("ok"), line("fine"), .overflow])
        XCTAssertEqual(reader.feed(bytes("\nok\n")), [])
        XCTAssertEqual(reader.feed(bytes("more\n")), [])

        var whole = LineReader(limit: 8)
        XCTAssertEqual(whole.feed(bytes("ok\n123456789\nlater\n")), [line("ok"), .overflow])
        XCTAssertEqual(whole.feed(bytes("later\n")), [])
    }

    func testReadersLimitIs64KiB() {
        XCTAssertEqual(Limits.maxLineBytes, 65_536)
        var most = LineReader()
        let full = [UInt8](repeating: 0x78, count: 65_536)
        XCTAssertEqual(most.feed(full), [])
        XCTAssertEqual(most.feed([0x0A]), [.line(Data(full))])

        var over = LineReader()
        XCTAssertEqual(over.feed(full), [])
        XCTAssertEqual(over.feed([0x78]), [.overflow])
    }

    // MARK: pictures

    /// The picture's pixels as RGBA rows from the top, read back through the system's decoder.
    private func decode(_ png: Data) throws -> (width: Int, height: Int, rgba: [UInt8]) {
        let source = try XCTUnwrap(CGImageSourceCreateWithData(png as CFData, nil))
        XCTAssertEqual(CGImageSourceGetType(source) as String?, "public.png")
        let image = try XCTUnwrap(CGImageSourceCreateImageAtIndex(source, 0, nil))
        var pixels = [UInt8](repeating: 0, count: image.width * image.height * 4)
        let space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        try pixels.withUnsafeMutableBytes { buffer in
            let context = try XCTUnwrap(CGContext(
                data: buffer.baseAddress, width: image.width, height: image.height,
                bitsPerComponent: 8, bytesPerRow: image.width * 4, space: space,
                bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
            ))
            context.interpolationQuality = .none
            context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        }
        return (image.width, image.height, pixels)
    }

    private func colours(_ rgba: [UInt8]) -> [[UInt8]] {
        stride(from: 0, to: rgba.count, by: 4).map { Array(rgba[$0..<$0 + 3]) }
    }

    func testPictureIsWrittenAsAPNGOfItsOwnSize() throws {
        let image = RawImage(width: 5, height: 3, rgba: Data(repeating: 0x40, count: 5 * 3 * 4))
        let png = try PNGEncoder.encode(image)
        XCTAssertEqual(Array(png.prefix(8)), [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
        XCTAssertEqual(Array(png[12..<16]), Array("IHDR".utf8))
        XCTAssertEqual(Array(png[16..<24]), [0, 0, 0, 5, 0, 0, 0, 3], "width then height, big end first")
        XCTAssertEqual(Array(png.suffix(8).prefix(4)), Array("IEND".utf8))
    }

    func testPictureReadsBackPixelForPixel() throws {
        let rows: [[[UInt8]]] = [
            [[255, 0, 0], [0, 255, 0], [0, 0, 255]],
            [[0, 0, 0], [255, 255, 255], [128, 128, 128]],
        ]
        var rgba = Data()
        for pixel in rows.flatMap({ $0 }) {
            rgba.append(contentsOf: pixel + [255])
        }
        let png = try PNGEncoder.encode(RawImage(width: 3, height: 2, rgba: rgba))
        let back = try decode(png)
        XCTAssertEqual(back.width, 3)
        XCTAssertEqual(back.height, 2)
        XCTAssertEqual(colours(back.rgba), rows.flatMap { $0 }, "rows from the top, red first")
    }

    func testPictureLeavesTheFourthByteOfEveryPixelOut() throws {
        let colour: [UInt8] = [200, 100, 50]
        var clear = Data()
        var solid = Data()
        for _ in 0..<16 {
            clear.append(contentsOf: colour + [0])
            solid.append(contentsOf: colour + [255])
        }
        let fromClear = try decode(PNGEncoder.encode(RawImage(width: 4, height: 4, rgba: clear)))
        let fromSolid = try decode(PNGEncoder.encode(RawImage(width: 4, height: 4, rgba: solid)))
        XCTAssertEqual(colours(fromClear.rgba), Array(repeating: colour, count: 16))
        XCTAssertEqual(colours(fromClear.rgba), colours(fromSolid.rgba))
    }

    func testPixelsThatDoNotFillThePictureAreNotWritten() {
        let short = RawImage(width: 4, height: 4, rgba: Data(repeating: 0, count: 63))
        let long = RawImage(width: 4, height: 4, rgba: Data(repeating: 0, count: 65))
        let none = RawImage(width: 0, height: 0, rgba: Data())
        let flat = RawImage(width: 4, height: 0, rgba: Data())
        let negative = RawImage(width: -2, height: -2, rgba: Data(repeating: 0, count: 16))
        for image in [short, long, none, flat, negative] {
            let refused = refusal(try PNGEncoder.encode(image))
            XCTAssertEqual(refused?.code, .captureFailed, "\(image.width) by \(image.height)")
        }
    }

    // MARK: command line

    func testNoArgumentServesOnTheDefaultSocket() {
        XCTAssertEqual(
            CommandLineOptions.parse([], home: "/Users/someone"),
            .serve(socketPath: "/Users/someone/.my-agent-crew/desktop/sock", ignored: [])
        )
        XCTAssertEqual(
            HelperInfo.defaultSocketPath(home: "/Users/someone"),
            "/Users/someone/.my-agent-crew/desktop/sock"
        )
    }

    func testSocketArgumentNamesThePath() {
        XCTAssertEqual(
            CommandLineOptions.parse(["--socket", "/tmp/x/sock"], home: "/h"),
            .serve(socketPath: "/tmp/x/sock", ignored: [])
        )
        XCTAssertEqual(
            CommandLineOptions.parse(["--socket", "relative/sock"], home: "/h"),
            .serve(socketPath: "relative/sock", ignored: [])
        )
        XCTAssertEqual(
            CommandLineOptions.parse(["--socket", "/a", "--socket", "/b"], home: "/h"),
            .serve(socketPath: "/b", ignored: [])
        )
    }

    func testSocketArgumentWithoutAPathIsAUsageError() {
        let usage = CommandLineOptions.usage("--socket needs a path: MyAgentCrewDesktop --socket <path>")
        XCTAssertEqual(CommandLineOptions.parse(["--socket"], home: "/h"), usage)
        XCTAssertEqual(CommandLineOptions.parse(["--socket", ""], home: "/h"), usage)
        XCTAssertEqual(CommandLineOptions.parse(["--socket", "/a", "--socket"], home: "/h"), usage)
    }

    func testVersionArgumentWinsWhereverItStands() {
        XCTAssertEqual(CommandLineOptions.parse(["--version"], home: "/h"), .version)
        XCTAssertEqual(CommandLineOptions.parse(["--socket", "/a", "--version"], home: "/h"), .version)
        XCTAssertEqual(CommandLineOptions.parse(["--version", "--socket"], home: "/h"), .version)
        XCTAssertEqual(CommandLineOptions.parse(["-v"], home: "/h"), .serve(
            socketPath: "/h/.my-agent-crew/desktop/sock", ignored: ["-v"]
        ))
    }

    func testAnyOtherArgumentIsCarriedAsIgnoredAndChangesNothing() {
        XCTAssertEqual(
            CommandLineOptions.parse(["--verbose", "--socket", "/a", "extra", "--install"], home: "/h"),
            .serve(socketPath: "/a", ignored: ["--verbose", "extra", "--install"])
        )
        XCTAssertEqual(
            CommandLineOptions.parse(["--socket=/a"], home: "/h"),
            .serve(socketPath: "/h/.my-agent-crew/desktop/sock", ignored: ["--socket=/a"])
        )
    }

    // MARK: JSON

    private func parsed(_ text: String) -> JSONValue? { JSONValue.parse(Data(text.utf8)) }

    func testJSONKeepsTrueApartFromOneAndAWholeNumberApartFromAFraction() {
        XCTAssertEqual(parsed("true"), .bool(true))
        XCTAssertEqual(parsed("false"), .bool(false))
        XCTAssertEqual(parsed("1"), .int(1))
        XCTAssertEqual(parsed("0"), .int(0))
        XCTAssertEqual(parsed("-7"), .int(-7))
        XCTAssertEqual(parsed("1.0"), .double(1))
        XCTAssertEqual(parsed("1.5"), .double(1.5))
        XCTAssertEqual(parsed("null"), .null)
        XCTAssertEqual(parsed("\"1\""), .string("1"))
        XCTAssertEqual(
            parsed(#"{"a":[1,true,null,"x",{"b":2.5}]}"#),
            .object(["a": .array([.int(1), .bool(true), .null, .string("x"), .object(["b": .double(2.5)])])])
        )
        XCTAssertNotEqual(parsed("true"), parsed("1"))
        XCTAssertNotEqual(parsed("1"), parsed("1.0"))
    }

    func testJSONThatIsNotJSONIsNothing() {
        // Forms every JSON reader refuses. A trailing comma is not among them: the system's reader
        // takes `[1,]` on some macOS versions and not on others, and the helper follows it.
        for text in ["", " ", "{", "}", "nope", "{\"a\":}", "[1 2]", "{'a':1}", "{\"a\":1}{\"b\":2}", "NaN"] {
            XCTAssertNil(parsed(text), "<\(text)>")
        }
        XCTAssertNil(JSONValue.parse(Data([0x7B, 0x22, 0x61, 0x22, 0x3A, 0x22, 0xC3, 0x28, 0x22, 0x7D])))
    }

    func testJSONNumberIsReadAsAWholeNumberOnlyWhenItIsOne() {
        XCTAssertEqual(JSONValue.int(5).intValue, 5)
        XCTAssertEqual(JSONValue.double(5).intValue, 5)
        XCTAssertEqual(JSONValue.double(-3).intValue, -3)
        XCTAssertNil(JSONValue.double(5.5).intValue)
        XCTAssertNil(JSONValue.double(1e300).intValue)
        XCTAssertNil(JSONValue.double(.nan).intValue)
        XCTAssertNil(JSONValue.double(.infinity).intValue)
        XCTAssertNil(JSONValue.bool(true).intValue)
        XCTAssertNil(JSONValue.string("5").intValue)
        XCTAssertNil(JSONValue.null.intValue)

        XCTAssertEqual(JSONValue.int(2).numberValue, 2)
        XCTAssertEqual(JSONValue.double(2.5).numberValue, 2.5)
        XCTAssertNil(JSONValue.double(.infinity).numberValue)
        XCTAssertNil(JSONValue.bool(false).numberValue)
        XCTAssertNil(JSONValue.string("2").numberValue)

        XCTAssertEqual(JSONValue.string("x").stringValue, "x")
        XCTAssertNil(JSONValue.int(1).stringValue)
        XCTAssertNil(JSONValue.null.stringValue)
    }

    func testJSONNumberTooLargeForAWholeNumberKeepsItsSize() {
        XCTAssertEqual(parsed("9223372036854775807"), .int(Int.max))
        XCTAssertEqual(parsed("18446744073709551615")?.numberValue, 18_446_744_073_709_551_615.0)
        XCTAssertNil(parsed("18446744073709551615")?.intValue)
        XCTAssertNil(parsed("1e400")?.intValue)
    }

    func testAnswerIsWrittenWithItsKeysInAFixedOrder() {
        let answer = JSONValue.object([
            "zeta": .int(1), "detail": .string("d"), "alpha": .null, "ok": .bool(false),
            "error": .string("e"), "id": .string("7"), "Beta": .array([]),
        ])
        XCTAssertEqual(
            answer.encoded(), #"{"id":"7","ok":false,"error":"e","detail":"d","Beta":[],"alpha":null,"zeta":1}"#
        )
        XCTAssertEqual(JSONValue.object([:]).encoded(), "{}")
        XCTAssertEqual(
            JSONValue.object(["b": .object(["ok": .bool(true), "a": .int(1)])]).encoded(),
            #"{"b":{"ok":true,"a":1}}"#
        )
    }

    func testValuesAreWrittenAsJSONOnOneLine() throws {
        XCTAssertEqual(JSONValue.null.encoded(), "null")
        XCTAssertEqual(JSONValue.bool(true).encoded(), "true")
        XCTAssertEqual(JSONValue.int(-3).encoded(), "-3")
        XCTAssertEqual(JSONValue.double(2).encoded(), "2.0")
        XCTAssertEqual(JSONValue.double(0.5).encoded(), "0.5")
        XCTAssertEqual(JSONValue.double(.nan).encoded(), "null")
        XCTAssertEqual(JSONValue.double(.infinity).encoded(), "null")
        XCTAssertEqual(JSONValue.array([.int(1), .string("a"), .array([])]).encoded(), #"[1,"a",[]]"#)

        let text = "a\"b\\c\nd\te\rf\u{01}g\u{1F}h é đ 😀 \u{2028} </script>"
        let written = JSONValue.string(text).encoded()
        XCTAssertEqual(
            written, "\"a\\\"b\\\\c\\nd\\te\\rf\\u0001g\\u001fh é đ 😀 \u{2028} </script>\""
        )
        XCTAssertFalse(written.contains("\n"))
        XCTAssertFalse(written.contains("\r"))
        let back = try JSONSerialization.jsonObject(with: Data(written.utf8), options: [.fragmentsAllowed])
        XCTAssertEqual(back as? String, text)
    }

    func testWhatIsWrittenReadsBackTheSame() {
        let value = JSONValue.object([
            "id": .string("7"), "ok": .bool(true), "n": .int(42), "f": .double(0.25),
            "whole": .double(3), "none": .null, "list": .array([.bool(false), .string("é\n")]),
            "deep": .object(["k": .array([.object([:])])]),
        ])
        XCTAssertEqual(parsed(value.encoded()), value)
    }

    // MARK: the contract's numbers and words

    func testLimitsAreTheContracts() {
        XCTAssertEqual(Limits.maxIDCharacters, 64)
        XCTAssertEqual(Limits.maxLineBytes, 64 * 1024)
        XCTAssertEqual(Limits.maxSocketPathBytes, 103)
        XCTAssertEqual(Limits.maxPx, 320...2000)
        XCTAssertEqual(Limits.defaultMaxPx, 1456)
        XCTAssertEqual(Limits.maxNodes, 50...400)
        XCTAssertEqual(Limits.defaultMaxNodes, 400)
        XCTAssertEqual(Limits.scrollLines, -50...50)
        XCTAssertEqual(Limits.maxTextCharacters, 2000)
        XCTAssertEqual(Limits.maxFieldCharacters, 200)
        XCTAssertEqual(Limits.maxWindows, 100)
        XCTAssertEqual(Limits.maxFrameAge, 300)
        XCTAssertEqual(Limits.focusWait, 2)
        XCTAssertEqual(HelperInfo.protocolVersion, 1)
        XCTAssertNotNil(HelperInfo.version.range(of: #"^\d+\.\d+\.\d+$"#, options: .regularExpression))
    }

    func testErrorCodesAreTheContractsWords() {
        XCTAssertEqual(Set(ErrorCode.allCases.map(\.rawValue)), [
            "bad_request", "unknown_command", "locked", "display_asleep", "permission_missing:screen",
            "permission_missing:accessibility", "frame_mismatch", "app_not_running", "app_mismatch",
            "ref_unknown", "secure_input", "blocked_keys", "capture_failed", "internal",
        ])
        XCTAssertEqual(ErrorCode.allCases.count, 14)
    }

    func testCommandsAreTheContractsWords() {
        for name in ["state", "request_permissions", "apps", "windows", "screenshot", "ax", "act"] {
            XCTAssertNotNil(Command(rawValue: name), name)
        }
        for name in ["State", "ACT", "", "permissions", "request-permissions", "click", "quit"] {
            XCTAssertNil(Command(rawValue: name), "<\(name)>")
        }
    }

    func testReasonTheHelperCannotListenReadsAsASentence() {
        XCTAssertEqual(
            SocketError.pathTooLong(bytes: 120).description,
            "The socket path is 120 bytes; a Unix socket path on macOS holds at most 103."
        )
        XCTAssertEqual(SocketError.unsafeFolder("The folder is open.").description, "The folder is open.")
        XCTAssertEqual(SocketError.inUse("A helper answers.").description, "A helper answers.")
        XCTAssertEqual(SocketError.failed("It failed.").description, "It failed.")
    }
}
