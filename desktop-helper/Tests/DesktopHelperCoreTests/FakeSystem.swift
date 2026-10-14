import Foundation
@testable import DesktopHelperCore

enum Fixture {
    /// The contract's example display: 1920 by 1080 points, two pixels a point.
    static let main = DisplayInfo(
        id: 1, bounds: ScreenRect(x: 0, y: 0, width: 1920, height: 1080), scale: 2, isMain: true
    )
    /// A second display to the right of the main one and a little higher.
    static let side = DisplayInfo(
        id: 2, bounds: ScreenRect(x: 1920, y: -200, width: 2560, height: 1440), scale: 1, isMain: false
    )
    static let textEdit = AppInfo(name: "TextEdit", bundleID: "com.apple.TextEdit", pid: 4242)
    static let notes = AppInfo(name: "Notes", bundleID: "com.apple.Notes", pid: 500)
    static let preview = AppInfo(name: "Preview", bundleID: "com.apple.Preview", pid: 300, isHidden: true)
    /// Another process's window, put over a point by a test.
    static let mail = AppInfo(name: "Mail", bundleID: "com.apple.mail", pid: 600)
    /// A web browser, which the helper never acts in; not running unless a test says so.
    static let safari = AppInfo(name: "Safari", bundleID: "com.apple.Safari", pid: 800)
}

/// Stands in for the machine: answers from what a test set and records every call it gets.
final class FakeSystem: System, @unchecked Sendable {
    enum Call: Equatable {
        case now
        case pause(TimeInterval)
        case isLocked
        case isDisplayAsleep
        case hasScreenRecording
        case hasAccessibility
        case isSecureInputOn
        case displays
        case frontmostApp
        case runningApps
        case requestPermissions
        case windows
        case capture(display: UInt32, width: Int, height: Int)
        case accessibilityTree(pid: Int32, maxNodes: Int)
        case elementFrame(Int)
        case focusedElementIsSecure(pid: Int32)
        case setValue(Int, String)
        case topElement(ScreenPoint, within: Int?)
        case postClick(ScreenPoint, MouseButton, Int)
        case postDrag(ScreenPoint, ScreenPoint)
        case postScroll(ScreenPoint, dx: Int, dy: Int)
        case postText(String)
        case postKey(code: UInt16, modifiers: KeyModifiers)
        case activate(pid: Int32)

        /// On a real machine this call would show, read or change something a permission guards.
        var touchesMachine: Bool {
            switch self {
            case .now, .pause, .isLocked, .isDisplayAsleep, .hasScreenRecording, .hasAccessibility,
                 .isSecureInputOn, .displays, .frontmostApp, .runningApps:
                return false
            default:
                return true
            }
        }

        /// The call posts an event, sets a value or brings an application forward.
        var acts: Bool {
            switch self {
            case .setValue, .postClick, .postDrag, .postScroll, .postText, .postKey, .activate:
                return true
            default:
                return false
            }
        }
    }

    private let lock = NSLock()
    private var recorded: [Call] = []
    /// Told of every call before it is answered; a test changes the machine from here.
    var onCall: ((Call) -> Void)?

    var clock: TimeInterval = 10_000
    var locked = false
    var asleep = false
    var screenRecording = true
    var accessibility = true
    var secureInput = false
    var displayList = [Fixture.main, Fixture.side]
    var front: AppInfo? = Fixture.textEdit
    var apps = [Fixture.textEdit, Fixture.preview, Fixture.notes]
    /// Whether the owner says yes to the dialogs `requestPermissions` stands for.
    var grantsOnRequest = false
    var windowList: [WindowInfo] = []
    var windowsError: Error?
    /// Every byte of a captured picture; another value is another screen.
    var pixel: UInt8 = 0x40
    var captured: RawImage?
    var captureError: SystemError?
    var snapshot = AXSnapshot(window: "Untitled", nodes: [], truncated: false)
    var treeError: SystemError?
    var elementFrames: [Int: ScreenRect] = [:]
    var frameError: SystemError?
    var focusedSecure = false
    var setValueError: SystemError?
    var postError: SystemError?
    var activateError: SystemError?

    /// An element on top at a point: the process that owns it and the fake element it is.
    struct Hit {
        let pid: Int32
        let element: Int
    }

    /// What lies over part of the screen; a `nil` hit is a place where no element is.
    struct Cover {
        let area: ScreenRect
        let hit: Hit?
    }

    /// The element of the frontmost application on top where nothing else is and no element
    /// was asked about: its window, which no tree of the tests holds.
    static let frontWindow = -1
    /// The first cover holding a point is what is on top there. Where none does, the element
    /// asked about is on top, else the frontmost application's window.
    var covers: [Cover] = []
    /// Each fake element's parent, for telling what is inside an element.
    var parents: [Int: Int] = [:]
    var hitError: SystemError?

    var calls: [Call] {
        lock.lock()
        defer { lock.unlock() }
        return recorded
    }

    var touches: [Call] { calls.filter(\.touchesMachine) }
    var actions: [Call] { calls.filter(\.acts) }

    func forgetCalls() {
        lock.lock()
        recorded = []
        lock.unlock()
    }

    private func record(_ call: Call) {
        lock.lock()
        recorded.append(call)
        lock.unlock()
        onCall?(call)
    }

    func now() -> TimeInterval {
        record(.now)
        return clock
    }

    func pause(_ seconds: TimeInterval) {
        record(.pause(seconds))
        clock += seconds
    }

    func isLocked() -> Bool {
        record(.isLocked)
        return locked
    }

    func isDisplayAsleep() -> Bool {
        record(.isDisplayAsleep)
        return asleep
    }

    func hasScreenRecording() -> Bool {
        record(.hasScreenRecording)
        return screenRecording
    }

    func hasAccessibility() -> Bool {
        record(.hasAccessibility)
        return accessibility
    }

    func isSecureInputOn() -> Bool {
        record(.isSecureInputOn)
        return secureInput
    }

    func displays() -> [DisplayInfo] {
        record(.displays)
        return displayList
    }

    func frontmostApp() -> AppInfo? {
        record(.frontmostApp)
        return front
    }

    func runningApps() -> [AppInfo] {
        record(.runningApps)
        return apps
    }

    func requestPermissions() {
        record(.requestPermissions)
        if grantsOnRequest {
            screenRecording = true
            accessibility = true
        }
    }

    func windows() throws -> [WindowInfo] {
        record(.windows)
        if let windowsError { throw windowsError }
        return windowList
    }

    func capture(display: UInt32, width: Int, height: Int) throws -> RawImage {
        record(.capture(display: display, width: width, height: height))
        if let captureError { throw captureError }
        if let captured { return captured }
        return RawImage(
            width: width, height: height, rgba: Data(repeating: pixel, count: width * height * 4)
        )
    }

    func accessibilityTree(pid: Int32, maxNodes: Int) throws -> AXSnapshot {
        record(.accessibilityTree(pid: pid, maxNodes: maxNodes))
        if let treeError { throw treeError }
        return snapshot
    }

    func elementFrame(_ element: Int) throws -> ScreenRect? {
        record(.elementFrame(element))
        if let frameError { throw frameError }
        return elementFrames[element]
    }

    func focusedElementIsSecure(pid: Int32) -> Bool {
        record(.focusedElementIsSecure(pid: pid))
        return focusedSecure
    }

    func setValue(_ element: Int, text: String) throws {
        record(.setValue(element, text))
        if let setValueError { throw setValueError }
    }

    func topElement(at point: ScreenPoint, within element: Int?) throws -> PointHit? {
        record(.topElement(point, within: element))
        if let hitError { throw hitError }
        let hit: Hit?
        if let cover = covers.first(where: { FakeSystem.area($0.area, holds: point) }) {
            hit = cover.hit
        } else {
            hit = front.map { Hit(pid: $0.pid, element: element ?? FakeSystem.frontWindow) }
        }
        guard let hit else { return nil }
        let inside = element.map { isSelfOrDescendant(hit.element, of: $0) } ?? false
        return PointHit(pid: hit.pid, insideTarget: inside)
    }

    private static func area(_ area: ScreenRect, holds point: ScreenPoint) -> Bool {
        area.x <= point.x && point.x < area.x + area.width
            && area.y <= point.y && point.y < area.y + area.height
    }

    /// Up the parents as the real machine walks them, as many steps at most.
    private func isSelfOrDescendant(_ element: Int, of target: Int) -> Bool {
        var current: Int? = element
        for _ in 0..<64 {
            guard let here = current else { return false }
            if here == target { return true }
            current = parents[here]
        }
        return false
    }

    func postClick(at point: ScreenPoint, button: MouseButton, count: Int) throws {
        record(.postClick(point, button, count))
        if let postError { throw postError }
    }

    func postDrag(from start: ScreenPoint, to end: ScreenPoint) throws {
        record(.postDrag(start, end))
        if let postError { throw postError }
    }

    func postScroll(at point: ScreenPoint, dx: Int, dy: Int) throws {
        record(.postScroll(point, dx: dx, dy: dy))
        if let postError { throw postError }
    }

    func postText(_ chunk: String) throws {
        record(.postText(chunk))
        if let postError { throw postError }
    }

    func postKey(code: UInt16, modifiers: KeyModifiers) throws {
        record(.postKey(code: code, modifiers: modifiers))
        if let postError { throw postError }
    }

    func activate(pid: Int32) throws {
        record(.activate(pid: pid))
        if let activateError { throw activateError }
    }
}
