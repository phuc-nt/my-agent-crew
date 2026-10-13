import CoreGraphics
import DesktopHelperCore

enum Displays {
    /// The displays the system draws on, sized in points.
    static func active() -> [DisplayInfo] {
        var count: UInt32 = 0
        guard CGGetActiveDisplayList(0, nil, &count) == .success, count > 0 else { return [] }
        var ids = [CGDirectDisplayID](repeating: 0, count: Int(count))
        guard CGGetActiveDisplayList(count, &ids, &count) == .success else { return [] }
        let main = CGMainDisplayID()
        return ids.prefix(Int(count)).map { id in
            let bounds = CGDisplayBounds(id)
            return DisplayInfo(
                id: id,
                bounds: ScreenRect(
                    x: bounds.origin.x, y: bounds.origin.y, width: bounds.width, height: bounds.height
                ),
                scale: scale(of: id),
                isMain: id == main
            )
        }
    }

    /// Pixels per point of the mode the display is in.
    private static func scale(of id: CGDirectDisplayID) -> Double {
        guard let mode = CGDisplayCopyDisplayMode(id), mode.width > 0, mode.pixelWidth > 0 else {
            return 1
        }
        return Double(mode.pixelWidth) / Double(mode.width)
    }
}
