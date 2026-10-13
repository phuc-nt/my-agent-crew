// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "MyAgentCrewDesktop",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "MyAgentCrewDesktop", targets: ["MyAgentCrewDesktop"]),
    ],
    targets: [
        // Everything that can be tested without touching the real machine.
        .target(name: "DesktopHelperCore"),
        // The real machine behind the `System` protocol, and `main`.
        .executableTarget(name: "MyAgentCrewDesktop", dependencies: ["DesktopHelperCore"]),
        .testTarget(name: "DesktopHelperCoreTests", dependencies: ["DesktopHelperCore"]),
    ]
)
