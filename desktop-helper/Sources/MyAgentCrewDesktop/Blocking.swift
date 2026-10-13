import DesktopHelperCore
import Foundation

enum Blocking {
    private final class Box<Value>: @unchecked Sendable {
        var result: Result<Value, Error>?
    }

    /// Runs asynchronous work to its end on behalf of a thread that may wait: the request queue,
    /// never the main thread. A system that does not answer in time is a failed capture.
    static func wait<Value>(seconds: Double, _ work: @escaping () async throws -> Value) throws -> Value {
        let box = Box<Value>()
        let done = DispatchSemaphore(value: 0)
        let task = Task.detached {
            do {
                box.result = .success(try await work())
            } catch {
                box.result = .failure(error)
            }
            done.signal()
        }
        // The box is read only after the signal, so the task is done writing it.
        guard done.wait(timeout: .now() + seconds) == .success, let result = box.result else {
            task.cancel()
            throw SystemError.captureFailed("The system did not answer within \(Int(seconds)) seconds.")
        }
        return try result.get()
    }
}
