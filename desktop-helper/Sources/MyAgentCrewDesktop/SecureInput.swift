import Darwin

/// Whether a password is being typed somewhere. Carbon exports `IsSecureEventInputEnabled`, but
/// no header of the SDK declares it any more, so it is found by name when the helper starts.
struct SecureInputProbe {
    private typealias Probe = @convention(c) () -> UInt8

    private let probe: Probe?

    init() {
        let carbon = "/System/Library/Frameworks/Carbon.framework/Carbon"
        if let library = dlopen(carbon, RTLD_LAZY),
           let symbol = dlsym(library, "IsSecureEventInputEnabled") {
            probe = unsafeBitCast(symbol, to: Probe.self)
        } else {
            probe = nil
        }
    }

    var isResolved: Bool { probe != nil }

    /// A helper that cannot tell says a password is being typed, so it never types into one.
    var isOn: Bool {
        guard let probe else { return true }
        return probe() != 0
    }
}
