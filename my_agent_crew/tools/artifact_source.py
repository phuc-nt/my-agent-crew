"""Reading a workspace file that is to become a canvas, for the import tool and for the web's
re-import alike. The file is opened once and measured on the open descriptor, so nothing can
change between the measuring and the reading; only a regular file is read, and never more than
one byte past its kind's cap, so a pipe, a device or a file still growing cannot hold a thread
or fill memory. Text must be real UTF-8: a byte swapped for a replacement mark would go back out
through an export as a damaged file nobody was told about."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from my_agent_crew.artifacts.filenames import LANGUAGE_BY_EXTENSION
from my_agent_crew.artifacts.kinds import BINARY_KINDS, KINDS, NotAnImage, cap_bytes, prepare
from my_agent_crew.texts import WORKSPACE_ESCAPE, WORKSPACE_IS_DIR, WORKSPACE_NOT_FOUND
from my_agent_crew.texts_canvas import (
    IMPORT_NOT_FILE,
    IMPORT_NOT_IMAGE,
    IMPORT_NOT_TEXT,
    IMPORT_TOO_LARGE,
    IMPORT_UNKNOWN_SUFFIX,
)
from my_agent_crew.tools.artifact_file_texts import IMPORT_NOT_READABLE
from my_agent_crew.tools.registry import ToolError
from my_agent_crew.tools.workspace import resolve_inside

# Looked up before the languages, so a page comes in as a page that runs; whoever wants its
# source as text says `kind: code`.
_KIND_BY_SUFFIX = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".htm": "html",
    ".svg": "svg",
    ".mmd": "mermaid",
    ".mermaid": "mermaid",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".webp": "image",
}
_LANGUAGE_BY_SUFFIX = {**LANGUAGE_BY_EXTENSION, ".yml": "yaml", ".txt": ""}


class SourceError(ToolError):
    """A file that cannot become a canvas. A tool lets it reach the model like any `ToolError`;
    a route answers with `status`."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class _OverCap(Exception):
    """The file holds more than one version of its kind may."""


@dataclass(frozen=True)
class SourceFile:
    """A file as a canvas will keep it: `content` for a text kind, `data` for a picture, its
    size in bytes and the sha256 of exactly that. `path` is where it was found."""

    path: Path
    content: str | None
    data: bytes | None
    size: int
    digest: str


def infer_kind(path: str) -> tuple[str, str]:
    """The kind and language the last suffix of `path` stands for, whatever its case."""
    suffix = Path(path).suffix.lower()
    if suffix in _KIND_BY_SUFFIX:
        return _KIND_BY_SUFFIX[suffix], ""
    if suffix in _LANGUAGE_BY_SUFFIX:
        return "code", _LANGUAGE_BY_SUFFIX[suffix]
    raise SourceError(422, IMPORT_UNKNOWN_SUFFIX.format(path=path, kinds=", ".join(KINDS)))


def code_language(path: str) -> str:
    """The language a file imported as code takes from its suffix, "" when it names none."""
    return _LANGUAGE_BY_SUFFIX.get(Path(path).suffix.lower(), "")


def read_source(root: Path, relative: str, kind: str) -> SourceFile:
    """The file at `relative` under the workspace `root`, checked as a version of `kind`.
    It blocks on the disk, so call it in a thread. Every refusal names the path as it was sent."""
    cap = cap_bytes(kind)
    try:
        path = resolve_inside(root, relative)
    except (ToolError, RuntimeError):  # RuntimeError: "~name" for a user this machine lacks
        raise SourceError(403, WORKSPACE_ESCAPE) from None
    try:
        raw = _read_regular(path, cap)
    except (FileNotFoundError, NotADirectoryError):
        raise SourceError(404, WORKSPACE_NOT_FOUND.format(path=relative)) from None
    except IsADirectoryError:
        raise SourceError(422, WORKSPACE_IS_DIR.format(path=relative)) from None
    except PermissionError:  # a file like any other, closed to this process
        raise SourceError(422, IMPORT_NOT_READABLE.format(path=relative)) from None
    except OSError:
        raise SourceError(422, IMPORT_NOT_FILE.format(path=relative)) from None
    except _OverCap:
        refusal = IMPORT_TOO_LARGE.format(path=relative, kind=kind, cap=cap)
        raise SourceError(413, refusal) from None
    content, data = None, raw
    if kind not in BINARY_KINDS:
        content, data = _text(raw), None
        if content is None:
            raise SourceError(422, IMPORT_NOT_TEXT.format(path=relative, kind=kind))
    try:
        content, size = prepare(kind, content, data)
    except NotAnImage:
        raise SourceError(422, IMPORT_NOT_IMAGE.format(path=relative)) from None
    kept = raw if content is None else content.encode("utf-8")
    return SourceFile(path, content, data, size, hashlib.sha256(kept).hexdigest())


def _read_regular(path: Path, cap: int) -> bytes:
    """At most `cap` bytes of a regular file, through one descriptor. The open does not wait,
    so a pipe with no writer returns at once and is then refused for what it is."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if stat.S_ISDIR(info.st_mode):
            raise IsADirectoryError(path.name)
        if not stat.S_ISREG(info.st_mode):
            raise OSError("not a regular file")
        if info.st_size > cap:
            raise _OverCap
        chunks: list[bytes] = []
        left = cap + 1
        while left > 0:
            chunk = os.read(fd, left)
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
    finally:
        os.close(fd)
    if left == 0:
        raise _OverCap
    return b"".join(chunks)


def _text(raw: bytes) -> str | None:
    """`raw` as UTF-8 text without its byte-order mark; None when it is not text."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    return None if "\x00" in text else text
