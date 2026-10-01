"""What a canvas may hold. The kind decides whether a version is text (`content`) or bytes
(`data`) and how large one version may grow. The store checks every write against this
table, so a tool, a route and an import are all held to the same limits."""

from __future__ import annotations

KB, MB = 1024, 1024 * 1024

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
    with the payload's size in bytes. Every line break in text becomes LF: a browser's
    textarea only ever sends LF, so text kept with CRLF would read as wholly rewritten the
    first time a person saved it from the web."""
    check_payload(kind, content, data)
    if content is not None:
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        size = len(content.encode("utf-8"))
    else:
        size = len(data or b"")
    check_size(kind, size)
    return content, size
