"""The canvas note a person's message is stored with: what changed in its conversation's
canvases since the agent last heard, and, for a message from the web chat, the canvas open
there and the passage selected in it. The model reads the note in front of the message.

Building a note only reads. It runs under the store's lock inside the message's transaction
and hands back the marks that record what it told; they run once the message is written, so
the note and its marks land together or not at all. A message sent while the person is still
typing in a canvas may miss the last autosave, so the web saves before it sends."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING

from my_agent_crew.artifacts.diff import diff_text, middle_lines
from my_agent_crew.artifacts.kinds import TEXT_KINDS
from my_agent_crew.store.artifact_authors import authors_line
from my_agent_crew.store.artifact_models import USER, ArtifactSummary, Focus, Link, VersionGone
from my_agent_crew.store.canvas_quote import focus_section, shown, title_of
from my_agent_crew.texts_canvas import (
    CANVAS_NOTE_BUMP,
    CANVAS_NOTE_CLOSE,
    CANVAS_NOTE_EDITED,
    CANVAS_NOTE_LARGE,
    CANVAS_NOTE_MORE,
    CANVAS_NOTE_NEW,
    CANVAS_NOTE_OPEN,
    CANVAS_NOTE_READ,
)

if TYPE_CHECKING:
    from my_agent_crew.store.db import Store

log = logging.getLogger(__name__)

# The web chat's turn source, where the open canvas lives; a test keeps it the agent's own.
WEB_CHAT = "chat"
# A person's change is diffed only while its changed middle is at most this many lines.
MIDDLE_LINES = 600
MAX_DIFFS = 3  # canvases one note diffs; the rest get a line each
NOTE_CHARS = 8000  # the whole note, its frame and overflow line included
DIFF_CHARS = 3000  # one canvas's diff

# What a note marks as told, run in the message's transaction once the message is in.
Mark = Callable[[], object]
# One way to tell of a canvas: its text in the note, "" for none, and what it marks.
Section = tuple[str, list[Mark]]


@dataclass(frozen=True)
class Note:
    text: str = ""
    marks: tuple[Mark, ...] = ()


def build_note(store: Store, conversation_id: str, source: str) -> Note:
    """The note for a person's message to `conversation_id` from `source`: the open canvas
    first when the message came from the web chat, then every linked canvas that moved past
    what the conversation saw or was told of, the most recently changed first."""
    links = store.artifact_links.links_for(conversation_id)
    focus = store.artifact_links.focus(conversation_id) if source == WEB_CHAT else None
    changed = _changed(store, links, focus)
    if not changed and focus is None:
        return Note()
    draft = _Draft(len(changed))
    if focus is not None:
        _add_focus(store, draft, focus)
    diffs = 0
    for summary, link in changed:
        diffs += _add_canvas(store, draft, summary, link, may_diff=diffs < MAX_DIFFS)
    return draft.note()


def _changed(
    store: Store, links: list[Link], focus: Focus | None
) -> list[tuple[ArtifactSummary, Link]]:
    pairs = [(store.artifacts.get(link.artifact_id), link) for link in links]
    changed = [pair for pair in pairs if pair[0].head_version > _base(pair[1])]
    changed.sort(key=lambda pair: pair[0].updated_at, reverse=True)
    opened = focus.artifact_id if focus is not None else None
    changed.sort(key=lambda pair: pair[0].id != opened)
    return changed


@dataclass
class _Draft:
    """The note so far: its lines and marks, the room left under NOTE_CHARS with the frame
    and an overflow line kept free, and how many canvases did not fit."""

    changed: int
    lines: list[str] = field(default_factory=list)
    marks: list[Mark] = field(default_factory=list)
    left_out: int = 0
    room: int = 0

    def __post_init__(self) -> None:
        frame = len(CANVAS_NOTE_OPEN) + len(CANVAS_NOTE_CLOSE) + 1
        more = len(CANVAS_NOTE_MORE.format(n=self.changed)) + 1
        self.room = NOTE_CHARS - frame - more

    def place(self, sections: list[Section]) -> int | None:
        """Places the first section that fits and takes its marks: which one, or None when
        none fits and nothing is marked."""
        for at, (text, marks) in enumerate(sections):
            if text and len(text) + 1 > self.room:
                continue
            if text:
                self.lines.append(text)
                self.room -= len(text) + 1
            self.marks.extend(marks)
            return at
        return None

    def note(self) -> Note:
        more = [CANVAS_NOTE_MORE.format(n=self.left_out)] if self.left_out else []
        body = self.lines + more
        text = "\n".join([CANVAS_NOTE_OPEN, *body, CANVAS_NOTE_CLOSE]) if body else ""
        return Note(text, tuple(self.marks))


def _base(link: Link) -> int:
    """The version a note tells changes from: the newest one seen or told of."""
    return max(link.seen_version, link.noted_version)


def _add_focus(store: Store, draft: _Draft, focus: Focus) -> None:
    try:
        section = focus_section(store, focus)
    except Exception:
        log.exception("canvas note: cannot read the open canvas %s", focus.artifact_id)
        return
    if section is not None:
        draft.place([section])


def _add_canvas(
    store: Store, draft: _Draft, summary: ArtifactSummary, link: Link, may_diff: bool
) -> bool:
    """Tells of one changed canvas in the fullest form that fits, or counts it as left out;
    True when that form was a diff."""
    art, head = summary.id, summary.head_version
    told = partial(store.artifact_links.mark_noted, link.conversation_id, art, head, commit=False)
    title, base = title_of(summary.title), _base(link)
    if base == 0:
        sections, diffed = [(CANVAS_NOTE_NEW.format(title=title, id=art, head=head), [told])], False
    else:
        try:
            sections, diffed = _sections(store, summary, link, base, told, may_diff)
        except Exception:
            log.exception("canvas note: cannot tell what changed in %s", art)
            bump = CANVAS_NOTE_BUMP.format(title=title, id=art, head=head)
            sections, diffed = [(f"{bump} {CANVAS_NOTE_READ}", [told])], False
    at = draft.place(sections)
    if at is None:
        draft.left_out += 1
    return diffed and at == 0


def _sections(
    store: Store, summary: ArtifactSummary, link: Link, base: int, told: Mark, may_diff: bool
) -> tuple[list[Section], bool]:
    """The forms a changed canvas can take, fullest first, and whether the first is a diff.
    Only a text canvas whose new versions are all a person's own writing is diffed, from the
    version last seen or told of, so the agent hears each change once."""
    art, head, seen = summary.id, summary.head_version, link.seen_version
    title = title_of(summary.title)
    versions = store.artifacts.versions(art)
    bump = CANVAS_NOTE_BUMP.format(title=title, id=art, head=head)
    authors = authors_line(versions, seen, head)
    one_line: Section = (" ".join(filter(None, (bump, authors, CANVAS_NOTE_READ))), [told])
    news = [version for version in versions if base < version.version <= head]
    persons = all(version.author == USER and not version.note for version in news)
    if summary.kind not in TEXT_KINDS or not persons or not may_diff:
        return [one_line], False
    try:
        before = shown(store.artifacts.version(art, base).content or "")
    except VersionGone:
        return [one_line], False
    after = shown(store.artifacts.head(art).content or "")
    if middle_lines(before, after) > MIDDLE_LINES:
        large = CANVAS_NOTE_LARGE.format(title=title, id=art, base=base, head=head)
        return [(f"{large} {CANVAS_NOTE_READ}", [told]), one_line], False
    diff = diff_text(before, after, DIFF_CHARS)
    # The newest version is seen whole only when the diff starts from a version seen whole
    # and shows every change in full.
    advance = base == seen and diff.whole
    links = store.artifact_links
    seen_all = partial(links.advance_seen, link.conversation_id, art, seen, head, commit=False)
    marks = [told, seen_all] if advance else [told]
    if not diff.text:
        return [("", marks)], False
    edited = CANVAS_NOTE_EDITED.format(title=title, id=art, base=base, head=head)
    read = "" if advance else f"\n{CANVAS_NOTE_READ}"
    return [(f"{edited}\n{diff.text}{read}", marks), one_line], True
