import CryptoKit
import Foundation

/// `<first 16 hex of the SHA-256 of the pixels>-<width>x<height>-<display id>`.
enum FrameID {
    struct Parts: Equatable {
        let hash: String
        let width: Int
        let height: Int
        let display: UInt32
    }

    static func make(pixels: Data, width: Int, height: Int, display: UInt32) -> String {
        let hash = SHA256.hash(data: pixels).prefix(8).map { String(format: "%02x", $0) }.joined()
        return "\(hash)-\(width)x\(height)-\(display)"
    }

    static func parse(_ text: String) -> Parts? {
        let pieces = text.split(separator: "-", omittingEmptySubsequences: false)
        guard pieces.count == 3 else { return nil }
        let size = pieces[1].split(separator: "x", omittingEmptySubsequences: false)
        let hex = "0123456789abcdef"
        guard pieces[0].count == 16, pieces[0].allSatisfy({ hex.contains($0) }),
              size.count == 2, let width = digits(size[0]), let height = digits(size[1]),
              width > 0, height > 0, let number = digits(pieces[2]),
              let display = UInt32(exactly: number)
        else { return nil }
        return Parts(hash: String(pieces[0]), width: width, height: height, display: display)
    }

    private static func digits(_ text: Substring) -> Int? {
        guard !text.isEmpty, text.count <= 10, text.allSatisfy({ "0123456789".contains($0) }) else {
            return nil
        }
        return Int(text)
    }
}

/// A picture the helper handed out, kept so `act` can read pixel coordinates against it.
struct Frame: Equatable {
    let id: String
    let display: UInt32
    let takenAt: TimeInterval
    let width: Int
    let height: Int
    /// The display's place and size in global points when the picture was taken.
    let displayBounds: ScreenRect

    /// The global point under a pixel of the picture; `nil` when the pixel is outside it.
    func point(x: Double, y: Double) -> ScreenPoint? {
        guard x >= 0, y >= 0, x < Double(width), y < Double(height) else { return nil }
        return ScreenPoint(
            x: displayBounds.x + x * displayBounds.width / Double(width),
            y: displayBounds.y + y * displayBounds.height / Double(height)
        )
    }
}

/// The last frame of each display and nothing older.
struct FrameStore {
    private var latest: [UInt32: Frame] = [:]

    mutating func remember(_ frame: Frame) {
        latest[frame.display] = frame
    }

    /// The frame `id` names when it is the last one of its display and still fresh.
    func frame(_ id: String, now: TimeInterval) throws -> Frame {
        guard let parts = FrameID.parse(id) else {
            throw Refusal(.frameMismatch, "That is not a frame id the helper gave out.")
        }
        guard let frame = latest[parts.display], frame.id == id else {
            throw Refusal(
                .frameMismatch,
                "That is not the last frame captured of display \(parts.display); take a new screenshot."
            )
        }
        guard now - frame.takenAt <= Limits.maxFrameAge else {
            throw Refusal(.frameMismatch, "That frame is over 300 seconds old; take a new screenshot.")
        }
        return frame
    }
}

struct PictureSize: Equatable {
    let width: Int
    let height: Int

    /// The display's own pixels, scaled down (never up) until the longer side fits `maxPx`.
    static func fit(display: DisplayInfo, maxPx: Int) -> PictureSize {
        let width = pixels(display.bounds.width * display.scale)
        let height = pixels(display.bounds.height * display.scale)
        let longer = max(width, height)
        guard longer > Double(maxPx) else {
            return PictureSize(width: Int(width), height: Int(height))
        }
        let factor = Double(maxPx) / longer
        return PictureSize(
            width: max(1, Int((width * factor).rounded())),
            height: max(1, Int((height * factor).rounded()))
        )
    }

    private static func pixels(_ value: Double) -> Double {
        guard value.isFinite, value >= 1 else { return 1 }
        return min(value.rounded(), 100_000)
    }
}
