import Foundation

/// What the arguments ask for. Only `--socket <path>` and `--version` mean anything; whatever
/// else is written is carried in `ignored` so `main` can say so, and changes nothing.
public enum CommandLineOptions: Equatable {
    case version
    case serve(socketPath: String, ignored: [String])
    case usage(String)

    public static func parse(_ arguments: [String], home: String) -> CommandLineOptions {
        if arguments.contains("--version") { return .version }
        var path = HelperInfo.defaultSocketPath(home: home)
        var ignored: [String] = []
        var index = 0
        while index < arguments.count {
            let argument = arguments[index]
            index += 1
            guard argument == "--socket" else {
                ignored.append(argument)
                continue
            }
            guard index < arguments.count, !arguments[index].isEmpty else {
                return .usage("--socket needs a path: MyAgentCrewDesktop --socket <path>")
            }
            path = arguments[index]
            index += 1
        }
        return .serve(socketPath: path, ignored: ignored)
    }
}
