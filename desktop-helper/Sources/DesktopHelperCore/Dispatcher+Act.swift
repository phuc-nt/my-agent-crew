import Foundation

extension Dispatcher {
    /// The checks after the shape and the preconditions, which the caller made: blocked keys,
    /// the application, a web browser, secure input, the frame and the ref, then what is on top
    /// at the points. Only then the action.
    func act(_ action: ActRequest) throws -> [String: JSONValue] {
        if let combo = action.combo, BlockedKeys.blocks(combo) {
            throw Refusal(
                .blockedKeys, "Those keys lock the screen, log out or force quit, so they are never sent."
            )
        }
        if action.kind == .focusApp {
            try focus(action.app)
            return done(effect: "focused")
        }
        guard let front = system.frontmostApp(), AppMatch.matches(action.app, front) else {
            throw Refusal(.appMismatch, "The frontmost application is not the one named in `app`.")
        }
        try refuseBrowser(front)
        try refuseSecureInput(action, front: front)
        let step = try resolve(action, front: front)
        try checkPoints(of: step, front: front)
        try perform(step, app: action.app)
        return done(effect: action.kind == .setValue ? "set" : "posted")
    }

    /// A page in a web browser can reach the crew's own web page and the private network, which
    /// the crew's browser tools hold apart and this helper cannot; so it never acts in one.
    private func refuseBrowser(_ front: AppInfo) throws {
        guard Browsers.contains(bundleID: front.bundleID) else { return }
        throw Refusal(
            .browserApp, "The frontmost application is a web browser; the helper never acts in one."
        )
    }

    private func done(effect: String) -> [String: JSONValue] {
        ["effect": .string(effect), "frontmost": Shape.frontmost(system.frontmostApp())]
    }

    /// `ok` only once the application is the frontmost one. A browser is never brought forward;
    /// one in front is left for another application, which sends it nothing, so an agent is not
    /// stuck behind a browser the owner left in front.
    private func focus(_ wanted: String) throws {
        let front = system.frontmostApp()
        guard let target = AppMatch.find(wanted, among: system.runningApps(), front: front) else {
            throw Refusal(.appNotRunning, "No running application is named that.")
        }
        if Browsers.contains(bundleID: target.bundleID) {
            throw Refusal(
                .browserApp, "That application is a web browser; the helper never brings one forward."
            )
        }
        if front?.pid == target.pid { return }
        try system.activate(pid: target.pid)
        let deadline = system.now() + Limits.focusWait
        while system.frontmostApp()?.pid != target.pid {
            guard system.now() < deadline else {
                throw Refusal(.appMismatch, "The application did not come to the front within 2 seconds.")
            }
            system.pause(0.05)
        }
    }

    private func refuseSecureInput(_ action: ActRequest, front: AppInfo) throws {
        guard action.kind.writes else { return }
        if system.isSecureInputOn() {
            throw Refusal(.secureInput, "Secure Event Input is on: a password is being typed.")
        }
        if action.kind == .type && system.focusedElementIsSecure(pid: front.pid) {
            throw Refusal(
                .secureInput,
                "The focused element is a secure text field, or the application would not say what holds the focus."
            )
        }
        if action.kind == .setValue, let ref = action.ref, let outline = action.outline,
           refs.pid == front.pid, refs.target(for: ref, of: outline)?.secure == true {
            throw Refusal(.secureInput, "That element is a secure text field.")
        }
    }

    private func perform(_ step: ActStep, app: String) throws {
        switch step {
        case .click(let point, let button, let count, _):
            try system.postClick(at: point, button: button, count: count)
        case .drag(let start, let end):
            try system.postDrag(from: start, to: end)
        case .scroll(let point, let dx, let dy):
            try system.postScroll(at: point, dx: dx, dy: dy)
        case .type(let text):
            try typeText(text, into: app)
        case .key(let combo):
            try system.postKey(code: combo.code, modifiers: combo.modifiers)
        case .setValue(let element, let text):
            try system.setValue(element, text: text)
        }
    }

    /// A long text takes many events. Between them the application and Secure Event Input are
    /// looked at again, so the rest of a text never lands in another application or a password.
    private func typeText(_ text: String, into app: String) throws {
        var typed = 0
        for chunk in TextTools.typingChunks(text) {
            if typed > 0 {
                guard let front = system.frontmostApp(), AppMatch.matches(app, front) else {
                    throw Refusal(
                        .appMismatch, "The frontmost application changed after \(typed) characters were typed."
                    )
                }
                if Browsers.contains(bundleID: front.bundleID) {
                    throw Refusal(
                        .browserApp, "A web browser came to the front after \(typed) characters were typed."
                    )
                }
                if system.isSecureInputOn() {
                    throw Refusal(
                        .secureInput, "Secure Event Input came on after \(typed) characters were typed."
                    )
                }
            }
            try system.postText(chunk)
            typed += chunk.unicodeScalars.count
        }
    }
}
