import Foundation

/// A point in global screen points; the origin is the top left corner of the main display.
public struct ScreenPoint: Equatable {
    public var x: Double
    public var y: Double

    public init(x: Double, y: Double) {
        self.x = x
        self.y = y
    }
}

/// A rectangle in global screen points.
public struct ScreenRect: Equatable {
    public var x: Double
    public var y: Double
    public var width: Double
    public var height: Double

    public init(x: Double, y: Double, width: Double, height: Double) {
        self.x = x
        self.y = y
        self.width = width
        self.height = height
    }

    public var center: ScreenPoint {
        ScreenPoint(x: x + width / 2, y: y + height / 2)
    }

    func overlap(with other: ScreenRect) -> Double {
        let across = min(x + width, other.x + other.width) - max(x, other.x)
        let down = min(y + height, other.y + other.height) - max(y, other.y)
        return across > 0 && down > 0 ? across * down : 0
    }
}

public struct DisplayInfo: Equatable {
    public let id: UInt32
    /// Place and size in global points.
    public let bounds: ScreenRect
    /// Pixels per point of the display itself.
    public let scale: Double
    public let isMain: Bool

    public init(id: UInt32, bounds: ScreenRect, scale: Double, isMain: Bool) {
        self.id = id
        self.bounds = bounds
        self.scale = scale
        self.isMain = isMain
    }
}

public struct AppInfo: Equatable {
    public let name: String
    public let bundleID: String
    public let pid: Int32
    public let isHidden: Bool

    public init(name: String, bundleID: String, pid: Int32, isHidden: Bool = false) {
        self.name = name
        self.bundleID = bundleID
        self.pid = pid
        self.isHidden = isHidden
    }
}

public struct WindowInfo: Equatable {
    public let app: String
    public let pid: Int32
    public let title: String
    public let bounds: ScreenRect
    public let layer: Int

    public init(app: String, pid: Int32, title: String, bounds: ScreenRect, layer: Int) {
        self.app = app
        self.pid = pid
        self.title = title
        self.bounds = bounds
        self.layer = layer
    }
}

/// A picture as RGBA bytes, eight bits a channel, rows from the top.
public struct RawImage: Equatable {
    public let width: Int
    public let height: Int
    public let rgba: Data

    public init(width: Int, height: Int, rgba: Data) {
        self.width = width
        self.height = height
        self.rgba = rgba
    }
}

/// One accessibility element as the machine reports it, before the contract's shaping.
public struct RawNode: Equatable {
    public var depth: Int
    public var role: String
    public var subrole: String?
    public var title: String?
    public var description: String?
    public var value: String?
    public var focused: Bool?
    public var enabled: Bool?
    public var frame: ScreenRect?
    /// What the `System` wants back to reach this element again; it means nothing to the core.
    public var element: Int

    public init(
        depth: Int, role: String, subrole: String? = nil, title: String? = nil,
        description: String? = nil, value: String? = nil, focused: Bool? = nil,
        enabled: Bool? = nil, frame: ScreenRect? = nil, element: Int
    ) {
        self.depth = depth
        self.role = role
        self.subrole = subrole
        self.title = title
        self.description = description
        self.value = value
        self.focused = focused
        self.enabled = enabled
        self.frame = frame
        self.element = element
    }
}

public struct AXSnapshot: Equatable {
    /// The window's title; `nil` when the application has no window to read.
    public let window: String?
    /// Depth first.
    public let nodes: [RawNode]
    /// The walk stopped before the tree ended.
    public let truncated: Bool

    public init(window: String?, nodes: [RawNode], truncated: Bool) {
        self.window = window
        self.nodes = nodes
        self.truncated = truncated
    }
}

public enum MouseButton: Equatable {
    case left
    case right
}

/// The element on top at a point of the screen, the one a pointer event there would reach.
public struct PointHit: Equatable {
    /// The process that owns it.
    public let pid: Int32
    /// It is the element the question named, or inside it; `false` when the question named none.
    public let insideTarget: Bool

    public init(pid: Int32, insideTarget: Bool) {
        self.pid = pid
        self.insideTarget = insideTarget
    }
}

/// What the machine can answer instead of doing what was asked.
public enum SystemError: Error, Equatable {
    case screenRecordingMissing
    case accessibilityMissing
    case captureFailed(String)
    /// The element no longer answers.
    case elementGone
    case secureField
    case appGone
    /// The machine cannot do this to that element.
    case unsupported(String)
    case failed(String)
}
