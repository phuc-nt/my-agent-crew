"""How a canvas note quotes a canvas: titles and passages made safe to show inside the
note's frame, and the canvas open in the web chat with the passage selected in it, placed by
its lines only when those lines hold it."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from my_agent_crew.artifacts.diff import line_span
from my_agent_crew.artifacts.kinds import TEXT_KINDS
from my_agent_crew.store.artifact_models import ArtifactSummary, Focus, VersionGone
from my_agent_crew.texts_canvas import (
    CANVAS_NOTE_CLOSE,
    CANVAS_NOTE_FOCUS,
    CANVAS_NOTE_OPEN,
    CANVAS_NOTE_PICK,
    CANVAS_NOTE_STUB,
    LINE_CUT_TAIL,
    PICK_GONE,
    PICK_LINES,
    PICK_OLD,
    PICK_TEXT,
)

if TYPE_CHECKING:
    from my_agent_crew.store.canvas_note import Section
    from my_agent_crew.store.db import Store

# A title is quoted in at most this many characters, a selected passage in at most these.
TITLE_CHARS = 80
PICK_CHARS = 1500

# Every character `str.splitlines` breaks a line on besides LF. A stored canvas has no CR,
# but the rest stay inside its lines, where the model would see a break the note never made.
_BREAKS = "\r\x0b\x0c\x1c\x1d\x1e\x85  "
_ESCAPES = str.maketrans({c: c.encode("unicode_escape").decode("ascii") for c in _BREAKS})
# The note's own frame lines, as a canvas may quote them: in round brackets.
_MARKERS = [
    (marker, marker.replace("[", "(").replace("]", ")"))
    for marker in (CANVAS_NOTE_OPEN, CANVAS_NOTE_CLOSE, CANVAS_NOTE_STUB)
]


def shown(text: str) -> str:
    """`text` as a note may quote it: every line break but LF made visible, and none of the
    note's frame lines left whole inside it. Both sides of a diff go through this, so its
    line numbers still match the canvas."""
    text = text.translate(_ESCAPES)
    for marker, neutral in _MARKERS:
        text = text.replace(marker, neutral)
    return text


def title_of(title: str) -> str:
    """A canvas title as a note quotes it between « and »: cut to TITLE_CHARS, with no « or »
    of its own to end the quotes early."""
    title = shown(title)
    if len(title) > TITLE_CHARS:
        title = title[: TITLE_CHARS - 1] + "…"
    return title.replace("«", "‹").replace("»", "›")


def focus_section(store: Store, focus: Focus) -> Section | None:
    """What a note says of the open canvas: the selected passage quoted, or else the canvas
    named once per opening, with the mark that records it and drops a selection once it is
    quoted or cannot be trusted. None when there is nothing to say or mark."""
    summary = store.artifacts.get(focus.artifact_id)
    pick = pick_block(store, summary, focus.selection)
    clear = focus.selection is not None
    links, conv = store.artifact_links, focus.conversation_id
    mark = partial(links.note_focus, conv, clear_selection=clear, commit=False)
    if pick is not None:
        return pick, [mark]
    if not focus.noted:
        title, version = title_of(summary.title), summary.head_version
        return CANVAS_NOTE_FOCUS.format(title=title, id=summary.id, version=version), [mark]
    return ("", [mark]) if clear else None


def valid_pick(selection: Any, head: int) -> bool:
    """Whether a stored selection has the shape the web sends, naming a version that can
    exist. The web stores what the browser sent, so none of it is trusted yet."""
    if not isinstance(selection, dict):
        return False
    numbers = [selection.get(key) for key in ("version", "line_start", "line_end")]
    if not all(type(number) is int for number in numbers):
        return False
    text = selection.get("text")
    return 1 <= numbers[0] <= head and isinstance(text, str) and bool(text.strip())


def pick_block(store: Store, summary: ArtifactSummary, selection: Any) -> str | None:
    """The selected passage quoted under a line saying where it is, or None when it cannot
    be trusted: a canvas without text, a shape the web never sends, or text the version does
    not hold. A version a later save folded away is looked for in the newest one."""
    head = summary.head_version
    if summary.kind not in TEXT_KINDS or not valid_pick(selection, head):
        return None
    text, gone = selection["text"], False
    try:
        content = store.artifacts.version(summary.id, selection["version"]).content or ""
    except VersionGone:
        content, gone = store.artifacts.head(summary.id).content or "", True
    if text not in content:
        return None
    where = _where(content, selection, head, gone)
    title = title_of(summary.title)
    return (
        CANVAS_NOTE_PICK.format(title=title, id=summary.id, where=where)
        + "\n"
        + quoted(shown(text))
    )


def quoted(text: str) -> str:
    """`text` as lines opened by "> ", cut at PICK_CHARS with what was left out counted."""
    text = text.strip("\n")
    if len(text) > PICK_CHARS:
        text = text[:PICK_CHARS] + LINE_CUT_TAIL.format(n=len(text) - PICK_CHARS)
    return "\n".join(f"> {line}" for line in text.split("\n"))


def _where(content: str, selection: dict[str, Any], head: int, gone: bool) -> str:
    number = selection["version"]
    if gone:
        return PICK_GONE.format(head=head)
    if number < head:
        return PICK_OLD.format(version=number, head=head)
    start, end = selection["line_start"], selection["line_end"]
    if _at_lines(content, selection["text"], start, end):
        return PICK_LINES.format(span=line_span(start, end), version=number)
    return PICK_TEXT.format(version=number)


def _at_lines(content: str, text: str, start: int, end: int) -> bool:
    """Whether the passage begins on line `start` of `content` and ends on line `end`: the
    browser counted its lines right."""
    lines = content.split("\n")
    if not 1 <= start <= end <= len(lines):
        return False
    block = "\n".join(lines[start - 1 : end])
    passage = text.strip("\n")
    at = block.find(passage)
    return at != -1 and "\n" not in block[:at] and passage.count("\n") == end - start
