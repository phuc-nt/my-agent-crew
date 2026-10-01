"""What a canvas may hold. The kind decides whether a version is text (`content`) or bytes
(`data`) and how large one version may grow. The store checks every write against this
table, so a tool, a route and an import are all held to the same limits."""

from __future__ import annotations

import re
import unicodedata

KB, MB = 1024, 1024 * 1024
TITLE_MAX = 200
LANGUAGE_MAX = 40
# A code canvas's language: a short name such as "python", "c++", "c#" or "objective-c".
_LANGUAGE = re.compile(r"[a-z0-9+#._-]*")
# Every version of every canvas together. Old versions are never pruned, so this is what
# stops a writer stuck in a loop long before the disk fills and every other write fails.
STORAGE_CAP = 1024 * MB
# Format characters a title may keep: the joiners that hold an emoji sequence or a word in
# some scripts together. Every other one is invisible at best, and a bidi override reorders
# whatever follows it.
_JOINERS = frozenset("\u200c\u200d")

# Largest version per kind, in bytes of UTF-8 text or of raw data. Prose and code stay
# small enough to diff and to quote back to a model; a page or a picture is allowed more.
_CAPS = {
    "markdown": 512 * KB,
    "code": 512 * KB,
    "html": 4 * MB,
    "svg": 2 * MB,
    "mermaid": 512 * KB,
    "image": 2 * MB,
}
KINDS = tuple(_CAPS)
BINARY_KINDS = frozenset({"image"})
TEXT_KINDS = frozenset(KINDS) - BINARY_KINDS


class UnknownKind(ValueError):
    """Not one of KINDS."""


class ArtifactTooLarge(ValueError):
    """One version is larger than its kind allows."""

    def __init__(self, kind: str, size: int, cap: int):
        super().__init__(f"{kind} version of {size} bytes is over the {cap}-byte cap")
        self.kind, self.size, self.cap = kind, size, cap


class PayloadMismatch(ValueError):
    """Text sent for a binary kind, bytes for a text kind, or neither."""


class InvalidTitle(ValueError):
    """Nothing left once cleaned, or longer than TITLE_MAX."""


class InvalidLanguage(ValueError):
    """Not a short name of letters, digits and "+#._-", or longer than LANGUAGE_MAX."""


class StorageFull(ValueError):
    """The write would take every canvas together past its author's ceiling."""

    def __init__(self, used: int, cap: int):
        super().__init__(f"canvases already hold {used} of {cap} bytes")
        self.used, self.cap = used, cap


def check_kind(kind: str) -> str:
    if kind not in _CAPS:
        raise UnknownKind(f"unknown canvas kind {kind!r}")
    return kind


def cap_bytes(kind: str) -> int:
    return _CAPS[check_kind(kind)]


def check_size(kind: str, size: int) -> None:
    cap = cap_bytes(kind)
    if size > cap:
        raise ArtifactTooLarge(kind, size, cap)


def check_payload(kind: str, content: str | None, data: bytes | None) -> None:
    """A text kind carries `content` and no `data`; a binary kind the other way round."""
    if check_kind(kind) in BINARY_KINDS:
        if data is None or content is not None:
            raise PayloadMismatch(f"{kind} takes data, not content")
    elif content is None or data is not None:
        raise PayloadMismatch(f"{kind} takes content, not data")


def prepare(kind: str, content: str | None, data: bytes | None) -> tuple[str | None, int]:
    """Checks one version's payload for its kind and returns the text as it will be stored,
    with the payload's size in bytes. CR and CRLF become LF: a browser's textarea only ever
    sends LF, so text kept with CRLF would read as wholly rewritten the first time a person
    saved it from the web. A canvas's lines are then what splitting on LF alone gives, on the
    server and in the browser alike: the vertical tab, form feed, file, group and record
    separators, NEL and the Unicode line and paragraph separators, which `str.splitlines`
    would also break on, are kept as they are, inside a line."""
    check_payload(kind, content, data)
    if content is not None:
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        size = len(content.encode("utf-8"))
    else:
        size = len(data or b"")
    check_size(kind, size)
    return content, size


def clean_title(title: str) -> str:
    """One line of visible text. Line breaks and other spaces become single spaces, and
    control and format characters are dropped, so a title quoted to a model or shown in a
    list cannot end the line it sits on, hide text, or reorder what follows."""
    kept = (" " if ch.isspace() else ch for ch in title)
    visible = "".join(
        ch for ch in kept if ch in _JOINERS or unicodedata.category(ch) not in ("Cc", "Cf")
    )
    text = " ".join(unicodedata.normalize("NFC", visible).split())
    if not text:
        raise InvalidTitle("a canvas needs a title")
    if len(text) > TITLE_MAX:
        raise InvalidTitle(f"a title of {len(text)} characters is over {TITLE_MAX}")
    return text


def clean_language(language: str) -> str:
    """Lower-cased, without surrounding spaces. It is listed and quoted to a model beside the
    title, so it is kept to characters that cannot end the line or hide text."""
    name = language.strip().lower()
    if len(name) > LANGUAGE_MAX or not _LANGUAGE.fullmatch(name):
        raise InvalidLanguage(f"a canvas language is a short name like 'python', not {language!r}")
    return name
