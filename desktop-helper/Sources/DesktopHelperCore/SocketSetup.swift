import Foundation

/// Why the helper cannot listen on a path. Each is a reason to exit with the message.
public enum SocketError: Error, Equatable, CustomStringConvertible {
    case pathTooLong(bytes: Int)
    case unsafeFolder(String)
    case inUse(String)
    case failed(String)

    public var description: String {
        switch self {
        case .pathTooLong(let bytes):
            return "The socket path is \(bytes) bytes; a Unix socket path on macOS holds at most "
                + "\(Limits.maxSocketPathBytes)."
        case .unsafeFolder(let message), .inUse(let message), .failed(let message):
            return message
        }
    }
}

enum SocketSetup {
    /// A listening socket at `path`, mode 0600, in a folder only `owner` can enter.
    static func makeListener(at path: String, owner: uid_t) throws -> Int32 {
        let bytes = path.utf8.count
        guard bytes > 0 else { throw SocketError.failed("The socket path is empty.") }
        guard bytes <= Limits.maxSocketPathBytes else { throw SocketError.pathTooLong(bytes: bytes) }
        try prepareFolder(for: path, owner: owner)
        try removeStaleSocket(at: path)
        return try bindAndListen(at: path)
    }

    private static func prepareFolder(for path: String, owner: uid_t) throws {
        let parent = (path as NSString).deletingLastPathComponent
        let folder = parent.isEmpty ? "." : parent
        var info = stat()
        if stat(folder, &info) != 0 {
            guard errno == ENOENT else { throw failure("The folder \(folder) cannot be read") }
            do {
                try FileManager.default.createDirectory(
                    atPath: folder, withIntermediateDirectories: true,
                    attributes: [.posixPermissions: 0o700]
                )
            } catch {
                throw SocketError.failed("The folder \(folder) cannot be made: \(error.localizedDescription)")
            }
            // The process's umask may have taken bits away; the folder is 0700 whatever it was.
            guard chmod(folder, 0o700) == 0, stat(folder, &info) == 0 else {
                throw failure("The folder \(folder) cannot be set up")
            }
        }
        guard info.st_mode & S_IFMT == S_IFDIR else {
            throw SocketError.unsafeFolder("\(folder) is not a folder.")
        }
        guard info.st_uid == owner else {
            throw SocketError.unsafeFolder("The folder \(folder) is not owned by the current user.")
        }
        guard info.st_mode & 0o077 == 0 else {
            throw SocketError.unsafeFolder("The folder \(folder) is open to group or others; make it 0700.")
        }
    }

    /// A socket file is removed only when nothing answers on it.
    private static func removeStaleSocket(at path: String) throws {
        var info = stat()
        guard lstat(path, &info) == 0 else {
            if errno == ENOENT { return }
            throw failure("\(path) cannot be read")
        }
        guard info.st_mode & S_IFMT == S_IFSOCK else {
            throw SocketError.inUse("\(path) is there and is not a socket; it is left alone.")
        }
        let probe = socket(AF_UNIX, SOCK_STREAM, 0)
        guard probe >= 0 else { throw failure("A socket cannot be made") }
        defer { close(probe) }
        if withAddress(path, { connect(probe, $0, $1) }) == 0 {
            throw SocketError.inUse("A helper already answers on \(path): one helper a socket.")
        }
        guard unlink(path) == 0 else { throw failure("The stale socket \(path) cannot be removed") }
    }

    private static func bindAndListen(at path: String) throws -> Int32 {
        let listener = socket(AF_UNIX, SOCK_STREAM, 0)
        guard listener >= 0 else { throw failure("A socket cannot be made") }
        let previous = umask(0o077)
        let bound = withAddress(path) { bind(listener, $0, $1) }
        let bindError = errno
        umask(previous)
        guard bound == 0 else {
            close(listener)
            errno = bindError
            throw failure("The socket cannot be bound at \(path)")
        }
        // As many connections may wait to be accepted as macOS allows: a full queue refuses the
        // next one at once, and the server would read that as no helper at all.
        guard chmod(path, 0o600) == 0, listen(listener, SOMAXCONN) == 0 else {
            let reason = failure("The socket at \(path) cannot be set up")
            close(listener)
            unlink(path)
            throw reason
        }
        return listener
    }

    private static func failure(_ what: String) -> SocketError {
        .failed("\(what): \(String(cString: strerror(errno))).")
    }

    static func withAddress<Value>(
        _ path: String, _ body: (UnsafePointer<sockaddr>, socklen_t) -> Value
    ) -> Value {
        var address = sockaddr_un()
        address.sun_family = sa_family_t(AF_UNIX)
        address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
        // The caller checked the length, so a NUL always follows the path.
        withUnsafeMutableBytes(of: &address.sun_path) { $0.copyBytes(from: path.utf8.prefix(103)) }
        return withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                body($0, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
    }
}
