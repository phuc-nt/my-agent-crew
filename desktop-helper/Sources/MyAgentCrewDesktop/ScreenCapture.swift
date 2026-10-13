import CoreGraphics
import DesktopHelperCore
import Foundation
import ScreenCaptureKit

enum ScreenCapture {
    /// The whole display as exactly `width` by `height` pixels.
    static func capture(display: UInt32, width: Int, height: Int) throws -> RawImage {
        // Asked here whatever the caller asked: without the grant, ScreenCaptureKit is what
        // shows the system's dialog.
        guard CGPreflightScreenCaptureAccess() else { throw SystemError.screenRecordingMissing }
        guard width > 0, height > 0 else {
            throw SystemError.captureFailed("The picture asked for has no size.")
        }
        let picture: CGImage
        do {
            picture = try Blocking.wait(seconds: 8) {
                try await image(of: display, width: width, height: height)
            }
        } catch let error as SystemError {
            throw error
        } catch {
            throw SystemError.captureFailed(error.localizedDescription)
        }
        return try pixels(of: picture, width: width, height: height)
    }

    private static func image(of display: UInt32, width: Int, height: Int) async throws -> CGImage {
        let content = try await SCShareableContent.current
        guard let target = content.displays.first(where: { $0.displayID == display }) else {
            throw SystemError.captureFailed("The system does not offer display \(display) for capture.")
        }
        let configuration = SCStreamConfiguration()
        configuration.width = width
        configuration.height = height
        configuration.showsCursor = true
        return try await SCScreenshotManager.captureImage(
            contentFilter: SCContentFilter(display: target, excludingWindows: []),
            configuration: configuration
        )
    }

    /// Drawn into memory of a known layout, so the same screen always gives the same bytes:
    /// red, green, blue and an unused byte, rows from the top.
    private static func pixels(of picture: CGImage, width: Int, height: Int) throws -> RawImage {
        var bytes = Data(count: width * height * 4)
        let drawn = bytes.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(
                data: buffer.baseAddress, width: width, height: height, bitsPerComponent: 8,
                bytesPerRow: width * 4,
                space: CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
            ) else { return false }
            context.interpolationQuality = .high
            context.draw(picture, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        guard drawn else {
            throw SystemError.captureFailed("The captured picture could not be read as pixels.")
        }
        return RawImage(width: width, height: height, rgba: bytes)
    }
}
