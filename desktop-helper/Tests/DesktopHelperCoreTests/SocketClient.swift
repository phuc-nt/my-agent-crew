import Foundation
@testable import DesktopHelperCore

/// What the Python server will be to the helper: a connection that writes request lines and reads
/// answer lines.
final class SocketClient {
    enum Reply: Equatable {
        case line(String)
        /// The helper ended the connection.
        case closed
        /// Nothing came within the time allowed.
        case timedOut
        case failed(Int32)
    }

    private var descriptor: Int32
    private var pending = Data()

    /// `nil` when nothing listens on `path`.
    init?(path: String) {
        let descriptor = socket(AF_UNIX, SOCK_STREAM, 0)
        guard descriptor >= 0 else { return nil }
        var on: Int32 = 1
        // A helper that hung up is a failed write for the test to see, not a signal that ends it.
        setsockopt(descriptor, SOL_SOCKET, SO_NOSIGPIPE, &on, socklen_t(MemoryLayout<Int32>.size))
        guard SocketSetup.withAddress(path, { connect(descriptor, $0, $1) }) == 0 else {
            close(descriptor)
            return nil
        }
        self.descriptor = descriptor
    }

    deinit {
        hangUp()
    }

    func hangUp() {
        guard descriptor >= 0 else { return }
        close(descriptor)
        descriptor = -1
    }

    /// Whether every byte was taken.
    @discardableResult
    func send(_ text: String) -> Bool {
        send(Array(text.utf8))
    }

    @discardableResult
    func send(_ bytes: [UInt8]) -> Bool {
        var sent = 0
        while sent < bytes.count {
            let count = bytes[sent...].withUnsafeBytes { write(descriptor, $0.baseAddress, $0.count) }
            if count < 0 && errno == EINTR { continue }
            guard count > 0 else { return false }
            sent += count
        }
        return true
    }

    /// The next answer line without its newline. `timeout` is how long one read may wait.
    func readLine(timeout: TimeInterval = 10) -> Reply {
        var wait = timeval(
            tv_sec: Int(timeout), tv_usec: Int32((timeout - timeout.rounded(.down)) * 1_000_000)
        )
        setsockopt(descriptor, SOL_SOCKET, SO_RCVTIMEO, &wait, socklen_t(MemoryLayout<timeval>.size))
        let size = 64 * 1024
        var buffer = [UInt8](repeating: 0, count: size)
        while true {
            if let newline = pending.firstIndex(of: 0x0A) {
                let line = Data(pending[pending.startIndex..<newline])
                pending = Data(pending[pending.index(after: newline)...])
                return .line(String(decoding: line, as: UTF8.self))
            }
            let count = read(descriptor, &buffer, size)
            if count > 0 {
                pending.append(contentsOf: buffer[0..<count])
                continue
            }
            if count == 0 { return .closed }
            switch errno {
            case EINTR: continue
            case EAGAIN: return .timedOut
            case ECONNRESET, EPIPE: return .closed
            default: return .failed(errno)
            }
        }
    }
}
