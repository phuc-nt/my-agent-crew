import Foundation

/// Turns one request into one answer. Not thread safe: the server calls it from one serial queue.
public final class Dispatcher {
    let system: System
    var frames = FrameStore()
    var refs = RefStore()

    public init(system: System) {
        self.system = system
    }

    /// What a line over the limit is answered with, before the connection is closed.
    public static let oversizeLineAnswer = Answer.refused(id: "", RequestParser.oversize).encoded()

    /// One request line in, one answer line out, both without the newline.
    public func respond(to line: Data) -> String {
        switch RequestParser.parse(line) {
        case .rejected(let id, let refusal):
            return Answer.refused(id: id, refusal).encoded()
        case .request(let request):
            return answer(request).encoded()
        }
    }

    func answer(_ request: Request) -> JSONValue {
        do {
            return Answer.ok(id: request.id, try run(request))
        } catch let refusal as Refusal {
            return Answer.refused(id: request.id, refusal)
        } catch let error as SystemError {
            return Answer.refused(id: request.id, Refusal(error))
        } catch {
            let refusal = Refusal(.internalError, "The helper failed: \(error).")
            return Answer.refused(id: request.id, refusal)
        }
    }

    /// A request's shape is read before the machine is asked anything, and the preconditions
    /// before anything else of the machine is touched.
    private func run(_ request: Request) throws -> [String: JSONValue] {
        guard let command = Command(rawValue: request.command) else {
            let name = TextTools.cut(request.command, to: 64)
            throw Refusal(.unknownCommand, "There is no command named \(name).")
        }
        let arguments = request.arguments
        switch command {
        case .state:
            return state()
        case .requestPermissions:
            return try requestPermissions()
        case .apps:
            try checkPreconditions(for: command)
            return apps()
        case .windows:
            try checkPreconditions(for: command)
            return try windows()
        case .screenshot:
            let shot = try ScreenshotRequest(arguments)
            try checkPreconditions(for: command)
            return try screenshot(shot)
        case .ax:
            let query = try AXRequest(arguments)
            try checkPreconditions(for: command)
            return try ax(query)
        case .act:
            let action = try ActRequest(arguments)
            try checkPreconditions(for: command)
            return try act(action)
        }
    }

    /// In the contract's order; the first that fails is the answer.
    func checkPreconditions(for command: Command) throws {
        if system.isLocked() {
            throw Refusal(.locked, "The console is locked.")
        }
        if system.isDisplayAsleep() {
            throw Refusal(.displayAsleep, "The main display is asleep.")
        }
        if command.needsScreenRecording && !system.hasScreenRecording() {
            throw Refusal(SystemError.screenRecordingMissing)
        }
        if command.needsAccessibility && !system.hasAccessibility() {
            throw Refusal(SystemError.accessibilityMissing)
        }
    }
}
