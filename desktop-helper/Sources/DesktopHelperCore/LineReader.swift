import Foundation

/// Cuts a byte stream into request lines and notices a line that grows past the limit, without
/// ever holding much more than one line.
struct LineReader {
    enum Event: Equatable {
        /// One line without its newline.
        case line(Data)
        /// A line went over the limit. Nothing more comes out of this reader.
        case overflow
    }

    private let limit: Int
    private var pending = Data()
    private var overflowed = false

    init(limit: Int = Limits.maxLineBytes) {
        self.limit = limit
    }

    mutating func feed<Bytes: Sequence>(_ bytes: Bytes) -> [Event] where Bytes.Element == UInt8 {
        guard !overflowed else { return [] }
        pending.append(contentsOf: bytes)
        var events: [Event] = []
        while let newline = pending.firstIndex(of: 0x0A) {
            let line = pending[pending.startIndex..<newline]
            guard line.count <= limit else { return events + [overflow()] }
            events.append(.line(Data(line)))
            pending = Data(pending[pending.index(after: newline)...])
        }
        // No newline yet: the line can only get longer.
        if pending.count > limit { events.append(overflow()) }
        return events
    }

    private mutating func overflow() -> Event {
        overflowed = true
        pending = Data()
        return .overflow
    }
}
