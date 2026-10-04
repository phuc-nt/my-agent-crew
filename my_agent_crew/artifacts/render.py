"""The page a canvas of kind `html` runs as, and the policy it runs under.

An html canvas is a page an agent wrote, and it runs: scripts, styles, libraries from a CDN. The
policy is what keeps that from reaching the app. `sandbox` without `allow-same-origin` gives the
page an opaque origin, so it cannot call the app's API or read its storage, and `connect-src`,
`form-action` and `img-src` leave it no way to send anything out. `allow-scripts` is never
combined with `allow-same-origin`: together they let a page remove its own sandbox.

The reporter below is the first script of every such page, so it runs before anything the page
wrote. It does two things. It tells whoever frames the page what went wrong: a script error, a
file that did not load, a request the policy blocked, a rejected promise. And it hands the app
one end of a message channel in the first message of the load, then says over the end it kept
each time a person presses a pointer inside the page or lets it go again. That press is what the
app takes as leave for the page to hold the keyboard. The frame only sends: the app listens to
the window and to the port it was handed, and never posts anything into the frame.
"""

from __future__ import annotations

import re

#: Where a page may load scripts, styles and fonts from. Pinned by version in the page itself.
CDN_HOSTS = ("https://cdnjs.cloudflare.com", "https://cdn.jsdelivr.net", "https://unpkg.com")
FONT_STYLES = "https://fonts.googleapis.com"
FONT_FILES = "https://fonts.gstatic.com"

#: ES5, one function, no globals. A page can fail to load the very script that would report it,
#: so this goes in before every script of the page. At most MAX_MESSAGES go out per load, so a
#: page that fails in a loop cannot flood the panel. A rejection that is no `Error` is told by
#: its `message`, else as JSON: Mermaid rejects a diagram it cannot parse with a plain object
#: `{str, message, hash}`, which `String()` turns into "[object Object]".
#:
#: The hello goes out as the script runs, ahead of any report and outside their count, with one
#: end of a channel in its transfer list. The other end is kept as `tell`, a local already bound
#: to its port, so a press is told without looking up a name the page could have replaced since.
#: Only a press is told, and only one the browser marks as a person's (`isTrusted`, which no
#: script can set): a page can make the browser fire `focus`, `pointermove`, `wheel` and `scroll`
#: on its own. A press is told when it begins and again when it ends, at the pointer coming up
#: and at the click: a person holds a button longer than the app waits on a press, and a page may
#: take the keyboard only at the click. A click no pointer made (`detail` 0: Enter or the space
#: bar on a button) is not told, since a page that took the keyboard gets the keys a person
#: meant for the app. A browser without `MessageChannel` tells of no press and still reports.
REPORTER_JS = """\
(function () {
  var MAX_MESSAGES = 20;
  var MAX_CHARS = 2000;
  var sent = 0;
  var tell = null;
  try {
    var channel = new MessageChannel();
    tell = channel.port1.postMessage.bind(channel.port1);
    parent.postMessage({type: "canvas-hello"}, "*", [channel.port2]);
  } catch (ignored) {}
  function pressed(event) {
    if (tell && event.isTrusted === true && (event.type !== "click" || event.detail > 0)) {
      tell({type: "press"});
    }
  }
  window.addEventListener("pointerdown", pressed, true);
  window.addEventListener("mousedown", pressed, true);
  window.addEventListener("pointerup", pressed, true);
  window.addEventListener("mouseup", pressed, true);
  window.addEventListener("click", pressed, true);
  function text(value) {
    return typeof value === "string" ? value : "";
  }
  function number(value) {
    return typeof value === "number" ? value : 0;
  }
  function reason(value) {
    try {
      var shown = String(value);
      if (shown !== "[object Object]") {
        return shown;
      }
      return typeof value.message === "string" ? value.message : JSON.stringify(value);
    } catch (ignored) {
      return "unhandled rejection";
    }
  }
  function report(what, source, line, column) {
    try {
      if (sent >= MAX_MESSAGES) {
        return;
      }
      var message = String(what).slice(0, MAX_CHARS);
      sent += 1;
      parent.postMessage({
        type: "canvas-error",
        message: message,
        source: text(source),
        line: number(line),
        column: number(column)
      }, "*");
    } catch (ignored) {}
  }
  window.addEventListener("error", function (event) {
    try {
      var target = event.target;
      if (target && target.nodeType === 1) {
        var url = text(target.currentSrc) || text(target.src) || text(target.href);
        report("failed to load " + (url || target.tagName.toLowerCase()), url, 0, 0);
      } else {
        report(event.message, event.filename, event.lineno, event.colno);
      }
    } catch (ignored) {}
  }, true);
  window.addEventListener("unhandledrejection", function (event) {
    report(reason(event.reason), "", 0, 0);
  });
  window.addEventListener("securitypolicyviolation", function (event) {
    report(
      (event.effectiveDirective || event.violatedDirective) + " blocked " + event.blockedURI,
      event.sourceFile, event.lineNumber, event.columnNumber
    );
  });
})();
"""
REPORTER_TAG = f"<script>{REPORTER_JS}</script>"

#: A doctype that begins the page, as the HTML parser allows: after a byte order mark, blank
#: space and comments, and nothing else. The loop is possessive (`*+`): a comment ends at its
#: first `-->`, so nothing it took is ever given back. Without that, a run of `<!---->` that
#: ends in no doctype is tried in every way of grouping it, twice as long for each comment, and
#: a page that does it freezes the server.
_DOCTYPE = re.compile(
    r"\A(?:\ufeff|[ \t\n\f\r]|<!--.*?-->)*+<!doctype[^>]*>", re.IGNORECASE | re.DOTALL
)
DOCTYPE_WINDOW = 2048


def _directive(name: str, *sources: str) -> str:
    return " ".join((name, *sources))


def render_csp() -> str:
    """The `Content-Security-Policy` of the render route, on one line."""
    return "; ".join(
        (
            "sandbox allow-scripts",
            "default-src 'none'",
            _directive("script-src", "'unsafe-inline'", "'unsafe-eval'", *CDN_HOSTS),
            _directive("style-src", "'unsafe-inline'", *CDN_HOSTS, FONT_STYLES),
            _directive("font-src", "data:", FONT_FILES, *CDN_HOSTS),
            "img-src data: blob:",
            "media-src data: blob:",
            "connect-src 'none'",
            "form-action 'none'",
            "base-uri 'none'",
            "frame-ancestors 'self'",
            "webrtc 'block'",
        )
    )


def html_page(content: str) -> str:
    """The canvas's own page with the reporter added and nothing else changed.

    The reporter goes right after a doctype that begins the page, because a script ahead of it
    would put the page in quirks mode. Without one the page is in quirks mode already, and the
    reporter goes at the very top. Only the start is looked at, so a page of megabytes costs
    nothing to find its doctype in.
    """
    found = _DOCTYPE.match(content[:DOCTYPE_WINDOW])
    at = found.end() if found else 0
    return content[:at] + REPORTER_TAG + content[at:]
