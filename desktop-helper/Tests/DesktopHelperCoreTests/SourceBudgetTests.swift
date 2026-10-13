import Foundation
import XCTest

/// Two rules about the sources themselves: no file grows past what one reading holds, and the
/// library the tests run never names the machine.
final class SourceBudgetTests: XCTestCase {
    private static let lineBudget = 200

    private struct Source {
        let name: String
        let text: String

        /// Lines as `wc -l` counts them, plus the last one when no newline ends it.
        var lines: Int {
            let newlines = text.utf8.filter { $0 == 0x0A }.count
            return text.isEmpty || text.hasSuffix("\n") ? newlines : newlines + 1
        }
    }

    /// Every Swift file of a target, by its path from `Sources/`.
    private func sources(of target: String? = nil) throws -> [Source] {
        let package = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        var root = package.appendingPathComponent("Sources", isDirectory: true)
        if let target { root.appendPathComponent(target, isDirectory: true) }
        let found = try XCTUnwrap(
            FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil),
            "no folder at \(root.path)"
        )
        var result: [Source] = []
        for case let file as URL in found where file.pathExtension == "swift" {
            let name = String(file.standardizedFileURL.path.dropFirst(root.standardizedFileURL.path.count + 1))
            result.append(Source(name: name, text: try String(contentsOf: file, encoding: .utf8)))
        }
        return result.sorted { $0.name < $1.name }
    }

    func testNoSourceFileIsOver200Lines() throws {
        let all = try sources()
        XCTAssertGreaterThanOrEqual(all.count, 30, "the walk found the sources: \(all.map(\.name))")
        XCTAssertTrue(all.contains { $0.name == "DesktopHelperCore/Dispatcher.swift" })
        XCTAssertTrue(all.contains { $0.name == "MyAgentCrewDesktop/main.swift" })
        for source in all {
            XCTAssertLessThanOrEqual(
                source.lines, Self.lineBudget, "\(source.name) has \(source.lines) lines; split it by concern"
            )
            XCTAssertGreaterThan(source.lines, 0, "\(source.name) is empty")
        }
    }

    func testLinesAreCountedAsWcCountsThemPlusAnUnendedLastLine() {
        XCTAssertEqual(Source(name: "", text: "").lines, 0)
        XCTAssertEqual(Source(name: "", text: "a\n").lines, 1)
        XCTAssertEqual(Source(name: "", text: "a").lines, 1)
        XCTAssertEqual(Source(name: "", text: "a\nb\n").lines, 2)
        XCTAssertEqual(Source(name: "", text: "a\nb").lines, 2)
        XCTAssertEqual(Source(name: "", text: "a\n\n\n").lines, 3)
        XCTAssertEqual(Source(name: "", text: String(repeating: "x\n", count: 201)).lines, 201)
    }

    /// Everything the tests reach goes through the `System` protocol, so a library that named one of
    /// these could show a dialog or move the pointer of the machine the tests run on.
    func testCoreLibraryNamesNothingOfTheRealMachine() throws {
        let forbidden = [
            "CGRequestScreenCaptureAccess", "CGPreflightScreenCaptureAccess", "AXIsProcessTrusted",
            "ScreenCaptureKit", "SCShareableContent", "SCScreenshotManager", "SCStream",
            "CGWindowList", "CGDisplayCreateImage", "CGEvent", "AXUIElement", "AXObserver",
            "NSWorkspace", "NSRunningApplication", "NSApplication", "NSScreen", "IsSecureEventInput",
            "CGSession", "CGDisplay", "CGMainDisplayID", "IOPM", "TISCopy", "UCKeyTranslate",
            "NSAppleScript", "osascript", "Process()",
            "import AppKit", "import ApplicationServices", "import Carbon", "import Cocoa",
            "import IOKit", "import ScreenCaptureKit",
        ]
        let core = try sources(of: "DesktopHelperCore")
        XCTAssertGreaterThanOrEqual(core.count, 20, "the walk found the library: \(core.map(\.name))")
        for source in core {
            for word in forbidden where source.text.contains(word) {
                XCTFail("\(source.name) names \(word); only the executable's `System` may")
            }
        }
    }

    func testCoreLibraryImportsOnlyWhatDrawsNoDialog() throws {
        let allowed: Set<String> = ["Foundation", "CryptoKit", "CoreGraphics", "ImageIO"]
        for source in try sources(of: "DesktopHelperCore") {
            for line in source.text.split(separator: "\n") where line.hasPrefix("import ") {
                let module = String(line.dropFirst("import ".count)).trimmingCharacters(in: .whitespaces)
                XCTAssertTrue(allowed.contains(module), "\(source.name) imports \(module)")
            }
        }
    }

    func testTheRealMachineIsNamedOnlyInTheExecutable() throws {
        let executable = try sources(of: "MyAgentCrewDesktop")
        XCTAssertGreaterThanOrEqual(executable.count, 10)
        let text = executable.map(\.text).joined(separator: "\n")
        for word in ["CGEvent", "AXUIElement", "SCScreenshotManager", "CGRequestScreenCaptureAccess"] {
            XCTAssertTrue(text.contains(word), "the executable is where \(word) lives")
        }
    }
}
