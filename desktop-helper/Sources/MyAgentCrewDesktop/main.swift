import AppKit
import DesktopHelperCore

/// Words for whoever reads the helper's stderr. Nothing written here goes to a socket.
func note(_ message: String) {
    FileHandle.standardError.write(Data("MyAgentCrewDesktop: \(message)\n".utf8))
}

/// SIGTERM and SIGINT end the helper with its socket file removed.
func stopOnSignal(_ server: SocketServer) -> [DispatchSourceSignal] {
    [SIGTERM, SIGINT].map { number in
        // Left at its default, the signal would end the process before the handler ran.
        signal(number, SIG_IGN)
        let source = DispatchSource.makeSignalSource(signal: number, queue: .main)
        source.setEventHandler {
            server.stop()
            exit(0)
        }
        source.resume()
        return source
    }
}

let arguments = Array(CommandLine.arguments.dropFirst())
switch CommandLineOptions.parse(arguments, home: NSHomeDirectory()) {
case .version:
    print(HelperInfo.version)
case .usage(let message):
    note(message)
    exit(64)
case .serve(let socketPath, let ignored):
    for argument in ignored {
        note("the argument \(argument) changes nothing and is ignored.")
    }
    // A peer that hung up is a failed write, never a signal that ends the helper.
    signal(SIGPIPE, SIG_IGN)
    let system = RealSystem()
    if !system.canReadSecureInput {
        note("Secure Event Input cannot be read on this system; it is reported as on.")
    }
    let server = SocketServer(path: socketPath, system: system)
    do {
        try server.start()
    } catch {
        note("\(error)")
        exit(1)
    }
    let signals = stopOnSignal(server)
    // The main thread only keeps the application alive and its view of the running
    // applications fresh; every request is answered on the server's own queue.
    let application = NSApplication.shared
    application.setActivationPolicy(.accessory)
    application.run()
    withExtendedLifetime(signals) {}
}
