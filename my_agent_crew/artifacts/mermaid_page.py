"""The page a canvas of kind `mermaid` runs as: its source, drawn by Mermaid.

Mermaid is loaded from a CDN, pinned to one version and checked against a hash, so a file that
changed on the way is refused by the browser instead of run. The page then shows the source as
text with a line saying why, as it does when there is no network. Mermaid 11 is pinned and not
12, whose build is two megabytes larger; a new version is a commit of its own, with the hash
worked out again.

The source goes into the page escaped, as Mermaid reads it back: a canvas that holds
`</pre><script>...` is drawn as that text, never run. `securityLevel: "strict"` keeps Mermaid
itself from running anything a diagram's labels carry. A syntax error is not caught here: it
rejects `run()`, and the reporter sends it on like any other failure of the page.
"""

from __future__ import annotations

import html

from my_agent_crew.artifacts.render import REPORTER_TAG
from my_agent_crew.texts_canvas import RENDER_MERMAID_OFFLINE

MERMAID_VERSION = "11.17.2"
MERMAID_URL = f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VERSION}/dist/mermaid.min.js"
#: sha384 of the file at MERMAID_URL, behind `sha384-`, as
#: `curl -sL <url> | openssl dgst -sha384 -binary | openssl base64 -A` prints it. The CDN and
#: the npm tarball of the same version give the same bytes.
MERMAID_SRI = "sha384-EOXBFmc3gx5mb+vn0vPvvGqACToJD24hhacX5Yx+8NUUQrHIle/Qi5Bg9o3zKwW2"
MERMAID_TAG = (
    f'<script src="{MERMAID_URL}" integrity="{MERMAID_SRI}" crossorigin="anonymous"></script>'
)

# Models often wrap a diagram in a fence; the canvas keeps what was written.
_FENCE = "```"
_FENCE_OPENING = _FENCE + "mermaid"

STYLE = """\
:root { color-scheme: light dark; }
body { margin: 0; padding: 16px; background: #ffffff; color: #1f2328;
  font: 14px/1.5 system-ui, sans-serif; }
.offline { margin: 0 0 12px; padding: 8px 12px; border-radius: 6px;
  background: #fff8c5; color: #3d2e00; }
pre.mermaid { margin: 0; font: 13px/1.5 ui-monospace, monospace; }
pre.mermaid:not([data-processed]) { white-space: pre-wrap; }
@media (prefers-color-scheme: dark) {
  body { background: #0d1117; color: #e6edf3; }
  .offline { background: #3d2e00; color: #fff8c5; }
}
"""

#: Without `window.mermaid` the file did not load or did not match its hash: the source stays
#: as it is and the line above it says so.
RUNNER_JS = """\
(function () {
  if (!window.mermaid) {
    document.getElementById("offline").hidden = false;
    return;
  }
  var dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  window.mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    theme: dark ? "dark" : "default"
  });
  window.mermaid.run();
})();
"""


def _unfenced(source: str) -> str:
    """The diagram inside a fence that wraps the whole source, else the source as it is. Plain
    string work: a pattern that looked for the closing fence from every position took time
    with the square of a source of blanks, and this runs on the event loop."""
    opening, _, rest = source.strip().partition("\n")
    if opening.rstrip(" \t").lower() != _FENCE_OPENING or not rest.endswith(_FENCE):
        return source
    return rest[: -len(_FENCE)].rstrip(" \t").removesuffix("\n")


def mermaid_page(title: str, source: str) -> str:
    """The page for a canvas titled `title` that holds `source`."""
    return "\n".join(
        (
            "<!doctype html>",
            '<html lang="vi">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{html.escape(title)}</title>",
            f"<style>{STYLE}</style>",
            REPORTER_TAG,
            "</head>",
            "<body>",
            f'<p id="offline" class="offline" hidden>{html.escape(RENDER_MERMAID_OFFLINE)}</p>',
            f'<pre class="mermaid">{html.escape(_unfenced(source))}</pre>',
            MERMAID_TAG,
            f"<script>{RUNNER_JS}</script>",
            "</body>",
            "</html>",
            "",
        )
    )
