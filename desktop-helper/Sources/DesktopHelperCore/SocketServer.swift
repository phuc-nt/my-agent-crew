import Foundation

/// Listens on a Unix socket and answers request lines, one request at a time across every
/// connection. Safe to start and stop from any thread: what changes is behind `lock`, and the
/// dispatcher is touched only on `requests`.
public final class SocketServer: @unchecked Sendable {
    private let path: String
    private let owner: uid_t
    /// The only user whose connections are answered. A test changes it to stand in for a stranger.
    var allowedPeer: uid_t
    private let dispatcher: Dispatcher
    /// The one serial queue of the contract: a second connection's request waits here.
    private let requests = DispatchQueue(label: "my-agent-crew.desktop.requests")
    private let accepting = DispatchQueue(label: "my-agent-crew.desktop.accept")
    private let lock = NSLock()
    private var source: DispatchSourceRead?
    private var connections: Set<Int32> = []

    /// `owner` must own the socket's folder, and only its connections are answered.
    public init(path: String, system: System, owner: uid_t = geteuid()) {
        self.path = path
        self.owner = owner
        self.allowedPeer = owner
        self.dispatcher = Dispatcher(system: system)
    }

    public func start() throws {
        let listener = try SocketSetup.makeListener(at: path, owner: owner)
        // Non-blocking, so a peer that goes away between the event and `accept` cannot hang it.
        _ = fcntl(listener, F_SETFL, fcntl(listener, F_GETFL) | O_NONBLOCK)
        let source = DispatchSource.makeReadSource(fileDescriptor: listener, queue: accepting)
        source.setEventHandler { [weak self] in self?.acceptPending(on: listener) }
        source.setCancelHandler { close(listener) }
        lock.lock()
        self.source = source
        lock.unlock()
        source.resume()
    }

    /// Stops listening, removes the socket file and ends every open connection.
    public func stop() {
        lock.lock()
        defer { lock.unlock() }
        guard let source else { return }
        self.source = nil
        source.cancel()
        unlink(path)
        // Under the lock, a descriptor in the set is still this connection's: it is closed only
        // after it was taken out.
        for connection in connections { shutdown(connection, SHUT_RDWR) }
    }

    private func acceptPending(on listener: Int32) {
        while true {
            let connection = accept(listener, nil, nil)
            if connection < 0 {
                if errno == EINTR { continue }
                return
            }
            guard peerIsOwner(connection), keep(connection) else {
                close(connection)
                continue
            }
            let thread = Thread { self.serve(connection) }
            thread.name = "my-agent-crew.desktop.connection"
            thread.start()
        }
    }

    /// Any other user's connection is closed without an answer.
    private func peerIsOwner(_ connection: Int32) -> Bool {
        var user: uid_t = 0
        var group: gid_t = 0
        return getpeereid(connection, &user, &group) == 0 && user == allowedPeer
    }

    private func keep(_ connection: Int32) -> Bool {
        // An accepted socket inherits the listener's non-blocking flag; the reads here block.
        _ = fcntl(connection, F_SETFL, fcntl(connection, F_GETFL) & ~O_NONBLOCK)
        var on: Int32 = 1
        // A peer that hung up must be a failed write, not a signal that ends the helper. macOS
        // refuses the option on a socket whose peer is already gone, and nobody is left to answer
        // there: such a connection is closed with its requests unread.
        let size = socklen_t(MemoryLayout<Int32>.size)
        guard setsockopt(connection, SOL_SOCKET, SO_NOSIGPIPE, &on, size) == 0 else { return false }
        lock.lock()
        defer { lock.unlock() }
        guard source != nil else { return false }
        connections.insert(connection)
        return true
    }

    private func release(_ connection: Int32) {
        lock.lock()
        connections.remove(connection)
        close(connection)
        lock.unlock()
    }

    private func serve(_ connection: Int32) {
        defer { release(connection) }
        var reader = LineReader()
        let size = 16 * 1024
        var buffer = [UInt8](repeating: 0, count: size)
        while true {
            let count = read(connection, &buffer, size)
            if count < 0 && errno == EINTR { continue }
            guard count > 0 else { return }
            for event in reader.feed(buffer[0..<count]) {
                switch event {
                case .line(let line):
                    let answer = requests.sync { dispatcher.respond(to: line) }
                    guard send(answer, to: connection) else { return }
                case .overflow:
                    _ = send(Dispatcher.oversizeLineAnswer, to: connection)
                    return
                }
            }
        }
    }

    private func send(_ answer: String, to connection: Int32) -> Bool {
        var bytes = Array(answer.utf8)
        bytes.append(0x0A)
        var sent = 0
        while sent < bytes.count {
            let count = bytes[sent...].withUnsafeBytes { write(connection, $0.baseAddress, $0.count) }
            if count < 0 && errno == EINTR { continue }
            guard count > 0 else { return false }
            sent += count
        }
        return true
    }
}
