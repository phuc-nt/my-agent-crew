import CoreGraphics
import Foundation
import ImageIO

enum PNGEncoder {
    private static let failure = Refusal(
        .captureFailed, "The captured pixels could not be written as a PNG picture."
    )

    /// The alpha channel is left out: a screen has none worth sending.
    static func encode(_ image: RawImage) throws -> Data {
        guard image.width > 0, image.height > 0,
              image.rgba.count == image.width * image.height * 4,
              let provider = CGDataProvider(data: image.rgba as CFData),
              let picture = CGImage(
                  width: image.width, height: image.height, bitsPerComponent: 8, bitsPerPixel: 32,
                  bytesPerRow: image.width * 4,
                  space: CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB(),
                  bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipLast.rawValue),
                  provider: provider, decode: nil, shouldInterpolate: false,
                  intent: .defaultIntent
              )
        else { throw failure }
        let output = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(
            output, "public.png" as CFString, 1, nil
        ) else { throw failure }
        CGImageDestinationAddImage(destination, picture, nil)
        guard CGImageDestinationFinalize(destination) else { throw failure }
        return output as Data
    }
}
