import Foundation

public enum HelperInfo {
    public static let version = "0.1.0"
    public static let protocolVersion = 1

    public static func defaultSocketPath(home: String) -> String {
        home + "/.my-agent-crew/desktop/sock"
    }
}

/// The error codes of the wire contract; the raw values are what goes on the wire.
public enum ErrorCode: String, CaseIterable {
    case badRequest = "bad_request"
    case unknownCommand = "unknown_command"
    case locked = "locked"
    case displayAsleep = "display_asleep"
    case permissionMissingScreen = "permission_missing:screen"
    case permissionMissingAccessibility = "permission_missing:accessibility"
    case frameMismatch = "frame_mismatch"
    case appNotRunning = "app_not_running"
    case appMismatch = "app_mismatch"
    case refUnknown = "ref_unknown"
    case pointCovered = "point_covered"
    case browserApp = "browser_app"
    case secureInput = "secure_input"
    case blockedKeys = "blocked_keys"
    case captureFailed = "capture_failed"
    case internalError = "internal"
}

public enum Limits {
    /// Characters are counted as Unicode scalars, which is what the Python client's `len` counts.
    public static let maxIDCharacters = 64
    public static let maxLineBytes = 64 * 1024
    /// `sockaddr_un.sun_path` holds 104 bytes, the last one a NUL.
    public static let maxSocketPathBytes = 103
    public static let maxPx = 320...2000
    public static let defaultMaxPx = 1456
    public static let maxNodes = 50...400
    public static let defaultMaxNodes = 400
    public static let scrollLines = -50...50
    public static let maxTextCharacters = 2000
    public static let maxFieldCharacters = 200
    public static let maxWindows = 100
    public static let maxFrameAge: TimeInterval = 300
    public static let focusWait: TimeInterval = 2
    public static let typingChunkUnits = 20
}

/// A request the helper answers with an error code instead of doing it.
public struct Refusal: Error, Equatable {
    public let code: ErrorCode
    public let detail: String

    public init(_ code: ErrorCode, _ detail: String) {
        self.code = code
        self.detail = detail
    }

    static func badRequest(_ detail: String) -> Refusal {
        Refusal(.badRequest, detail)
    }

    /// What the machine said, as the contract's code for it.
    init(_ error: SystemError) {
        switch error {
        case .screenRecordingMissing:
            self.init(.permissionMissingScreen, "Screen Recording is not granted to the helper.")
        case .accessibilityMissing:
            self.init(.permissionMissingAccessibility, "Accessibility is not granted to the helper.")
        case .captureFailed(let message):
            self.init(.captureFailed, message)
        case .elementGone:
            self.init(.refUnknown, "That element no longer answers; read the tree again.")
        case .secureField:
            self.init(.secureInput, "That element is a secure text field.")
        case .appGone:
            self.init(.appNotRunning, "That application is no longer running.")
        case .unsupported(let message):
            self.init(.badRequest, message)
        case .failed(let message):
            self.init(.internalError, message)
        }
    }
}

public enum Command: String, CaseIterable {
    case state
    case requestPermissions = "request_permissions"
    case apps
    case windows
    case screenshot
    case ax
    case act

    /// `state` and `request_permissions` answer whatever the machine's condition.
    public var hasPreconditions: Bool { self != .state && self != .requestPermissions }
    public var needsScreenRecording: Bool { self == .windows || self == .screenshot }
    public var needsAccessibility: Bool { self == .ax || self == .act }
}

extension Comparable {
    func clamped(to range: ClosedRange<Self>) -> Self {
        min(max(self, range.lowerBound), range.upperBound)
    }
}
