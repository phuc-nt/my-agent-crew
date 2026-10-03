"""Applying an agent's edit to a canvas. The match is exact, or else reads curly quotes and
odd spaces as plain ones; it must be unique unless every match is replaced, and the result
is sized before it is built. Cheap enough to run inside the store's lock: when nothing
matches, finding the closest passage is left to `text_nearest`, after the lock is let go."""

from __future__ import annotations

from my_agent_crew.artifacts.kinds import utf8_size
from my_agent_crew.texts_canvas import (
    ARTIFACT_CONTENT_UNSTORABLE,
    ARTIFACT_EDIT_AMBIGUOUS,
    ARTIFACT_EDIT_EMPTY_OLD,
    ARTIFACT_EDIT_NO_MATCH,
    ARTIFACT_EDIT_TOO_LARGE,
)
from my_agent_crew.tools.registry import ToolError

# Each maps one character to one, so offsets in the loose text hold in the original.
_LOOSE = str.maketrans(
    {
        "\N{NO-BREAK SPACE}": " ",
        "\N{NARROW NO-BREAK SPACE}": " ",
        "\N{FIGURE SPACE}": " ",
        "\N{LEFT SINGLE QUOTATION MARK}": "'",
        "\N{RIGHT SINGLE QUOTATION MARK}": "'",
        "\N{LEFT DOUBLE QUOTATION MARK}": '"',
        "\N{RIGHT DOUBLE QUOTATION MARK}": '"',
    }
)


class EditNotFound(ToolError):
    """`old` is nowhere in the canvas, not even read loosely."""


def normalize_for_match(text: str) -> str:
    return text.translate(_LOOSE)


def apply_edit(
    text: str, old: str, new: str, replace_all: bool = False, cap: int | None = None
) -> tuple[str, int]:
    """`text` with `old` replaced by `new`, and how many places changed. Cheap enough to run
    inside the store's lock: no search beyond plain `find`. A `new` with a lone surrogate is
    refused as `UnstorableText`. An `old` with one needs no check: no canvas holds one, so it
    matches nothing and is reported as not found."""
    if not old:
        raise ToolError(ARTIFACT_EDIT_EMPTY_OLD)
    new_size = utf8_size(new, ARTIFACT_CONTENT_UNSTORABLE)
    count = text.count(old)
    if count:
        size = len(text.encode()) + count * (new_size - len(old.encode()))
        _check(count, replace_all, size, cap)
        return text.replace(old, new), count
    loose, wanted, starts = normalize_for_match(text), normalize_for_match(old), []
    at = loose.find(wanted)
    while at != -1:
        starts.append(at)
        at = loose.find(wanted, at + len(old))
    if not starts:
        raise EditNotFound(ARTIFACT_EDIT_NO_MATCH)
    # A loose match replaces the canvas's own characters, which may take more bytes.
    matched = sum(len(text[start : start + len(old)].encode()) for start in starts)
    size = len(text.encode()) - matched + len(starts) * new_size
    _check(len(starts), replace_all, size, cap)
    pieces, end = [], 0
    for start in starts:
        pieces += [text[end:start], new]
        end = start + len(old)
    return "".join([*pieces, text[end:]]), len(starts)


def _check(count: int, replace_all: bool, size: int, cap: int | None) -> None:
    if count > 1 and not replace_all:
        raise ToolError(ARTIFACT_EDIT_AMBIGUOUS.format(count=count))
    if cap is not None and size > cap:
        raise ToolError(ARTIFACT_EDIT_TOO_LARGE.format(size=size, cap=cap))
