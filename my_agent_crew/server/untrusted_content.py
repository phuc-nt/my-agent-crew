"""Headers for what an agent wrote: the files in its workspace and the canvases it fills. An
agent can be steered by what it reads, so its output must never open as a page of the app,
where a script could call every `/api/...` route: its origin would be the app's, and the local
guard lets those through.

Two independent layers keep it out. Anything but a raster image, a PDF or plain text downloads
as bytes instead of opening. And everything but a PDF opens sandboxed, in an opaque origin whose
requests carry `Origin: null`, which the local guard refuses.

The table is pinned here rather than taken from `mimetypes`, which differs between machines
(`.ts` is `video/mp2t` on a Mac) and would hand `.xht`, `.rss` or `.svg` to the browser as
documents that run scripts.

A canvas takes the same two layers (`canvas_shown`): a page is plain text when it is read, a
drawing an image that downloads when it is opened, a picture its own bytes. Only the render
route runs a canvas as a page, in a sandbox of its own that allows scripts and has no way out
(`artifacts/render.py`); nothing here ever does.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple
from urllib.parse import quote

from fastapi.responses import FileResponse, Response

from my_agent_crew.artifacts.kinds import sniff_image
from my_agent_crew.memory.search import normalize

#: Never `allow-scripts` or `allow-same-origin`. Inline styles stay, so an image or a text
#: file opened in a tab still looks like one.
SANDBOX = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
TEXT = "text/plain; charset=utf-8"


class Shown(NamedTuple):
    media_type: str
    inline: bool
    sandbox: bool


#: By lowercase extension. An `<img>` ignores the disposition and CSP of the image itself, so
#: an SVG still shows in a thread while opening it downloads it.
SHOWN: dict[str, Shown] = {
    ".png": Shown("image/png", True, True),
    ".jpg": Shown("image/jpeg", True, True),
    ".jpeg": Shown("image/jpeg", True, True),
    ".gif": Shown("image/gif", True, True),
    ".webp": Shown("image/webp", True, True),
    ".avif": Shown("image/avif", True, True),
    ".svg": Shown("image/svg+xml", False, True),
    # Chrome's viewer does not run inside a sandboxed document. A PDF's own scripts run in
    # PDFium's sandbox, away from the app's pages and origin.
    ".pdf": Shown("application/pdf", True, False),
    ".txt": Shown(TEXT, True, True),
    ".log": Shown(TEXT, True, True),
}
BYTES = Shown("application/octet-stream", False, True)

_UNSAFE = re.compile(r"[^a-z0-9._-]+")


def untrusted_file(path: Path) -> FileResponse:
    """A workspace file the way the browser may have it, under its own name."""
    shown = SHOWN.get(path.suffix.lower(), BYTES)
    headers = untrusted_headers(shown, path.name, "file")
    return FileResponse(path, media_type=shown.media_type, headers=headers)


def canvas_shown(kind: str, data: bytes | None, *, download: bool) -> Shown:
    """How a canvas of `kind` goes out. Text is plain text whatever it holds, so a page an
    agent wrote never runs as one of the app's. A drawing is an image: an `<img>` draws it
    without running its script, and opened as a document it downloads. A picture is its own
    bytes under the type they give, and bytes of no type we know, which no write lets in, are
    plain bytes. `download` saves any of them under their name instead of showing them."""
    if kind == "image":
        shown = SHOWN.get(sniff_image(data) or "", BYTES)
    elif kind == "svg" and not download:
        shown = SHOWN[".svg"]
    else:
        shown = Shown(TEXT, True, True)
    return shown._replace(inline=shown.inline and not download)


def untrusted_text(text: str, shown: Shown, name: str) -> Response:
    """A canvas's text, under the type and the disposition `shown` gives it."""
    headers = untrusted_headers(shown, name, "canvas")
    return Response(text, media_type=shown.media_type, headers=headers)


def untrusted_bytes(data: bytes, shown: Shown, name: str) -> Response:
    """A picture's own bytes, under the type and the disposition `shown` gives them."""
    headers = untrusted_headers(shown, name, "canvas")
    return Response(data, media_type=shown.media_type, headers=headers)


def untrusted_headers(shown: Shown, name: str, fallback: str) -> dict[str, str]:
    headers = {
        "Content-Disposition": disposition(name, fallback, inline=shown.inline),
        "X-Content-Type-Options": "nosniff",
        "Cross-Origin-Resource-Policy": "same-origin",
    }
    if shown.sandbox:
        headers["Content-Security-Policy"] = SANDBOX
    return headers


def disposition(name: str, fallback: str, *, inline: bool = False) -> str:
    """`filename*` carries the whole name, in any script. `filename` is a plain fallback for a
    client that reads only that: the stem and the extension folded apart, with `fallback` for
    a stem that folds to nothing (`メモ.html` → `file.html`). Built by hand, so every byte of
    the value encodes as latin-1, as a header must."""
    stem, dot, extension = name.rpartition(".")
    if not dot:
        stem, extension = name, ""
    plain = _fold(stem) or fallback
    if folded := _fold(extension):
        plain = f"{plain}.{folded}"
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename=\"{plain}\"; filename*=UTF-8''{quote(name, safe='')}"


def _fold(part: str) -> str:
    return _UNSAFE.sub("-", normalize(part)).strip("-.")
