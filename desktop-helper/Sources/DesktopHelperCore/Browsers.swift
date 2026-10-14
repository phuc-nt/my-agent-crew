import Foundation

/// The applications that are web browsers, by bundle id. Acting in one is refused whatever the
/// agent's list says: a page there reaches the crew's own web page and the private network,
/// which the crew's browser tools hold apart and this helper cannot.
enum Browsers {
    /// An id listed here, or one that goes on from it after a dot: a beta, or a site saved as
    /// an app of its own (`com.google.Chrome.app.…`, `com.apple.Safari.WebApp.…`).
    static let bundleIDs: [String] = [
        "com.apple.Safari",
        "com.apple.SafariTechnologyPreview",
        "com.google.Chrome",
        "com.google.chrome.for.testing",
        "org.chromium.Chromium",
        "org.mozilla.firefox",
        "org.mozilla.firefoxdeveloperedition",
        "org.mozilla.nightly",
        "org.torproject.torbrowser",
        "com.microsoft.edgemac",
        "com.brave.Browser",
        "company.thebrowser.Browser",
        "company.thebrowser.dia",
        "com.operasoftware",
        "com.vivaldi.Vivaldi",
        "com.kagi.kagimacOS",
        "com.duckduckgo.macos.browser",
        "app.zen-browser.zen",
        "ru.yandex.desktop.yandex-browser",
    ]

    /// Bundle ids are compared as LaunchServices does, without regard to case.
    static func contains(bundleID: String) -> Bool {
        let id = bundleID.lowercased()
        return bundleIDs.contains { listed in
            let browser = listed.lowercased()
            return id == browser || id.hasPrefix(browser + ".")
        }
    }
}
