"""Forking a conversation that has canvases: every copied message keeps the canvas note it was
stored with, and the fork links each canvas the source had linked by the fork point with
nothing seen, read or told, so the fork's agent reads a canvas again before it overwrites it.
The canvas open in the source stays open there only."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from my_agent_crew.llm.types import Message
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import ARTIFACT_REWRITE_UNSEEN, CANVAS_NOTE_NEW
from tests.canvas_helpers import (
    PLAN,
    SWIM,
    agents_canvas,
    call,
    edited,
    framed,
    lines_text,
    say,
    seen,
    seen_canvas,
    turn,
)
from tests.conftest import CanvasClock

FRESH = {"seen_version": 0, "read_version": 0, "read_upto": 0, "noted_version": 0}


def _cut(store: Store, conversation_id: str, text: str = "hai") -> int:
    """The id of a person's message to fork the conversation at."""
    return store.append(conversation_id, Message(role="user", content=text)).id


def test_each_copied_message_keeps_the_canvas_note_it_was_stored_with(store: Store):
    conv = store.create()
    art = seen_canvas(store, conv)
    store.artifacts.write(art, SWIM, USER, "")
    note = say(store, conv)
    store.append(conv.id, Message(role="assistant", content="Đã xem."))
    fork, draft = store.fork(conv.id, _cut(store, conv.id), autonomous=False)
    assert (note, draft) == (framed(*edited("Kế hoạch", art)), "hai")
    copied = [(m.message.content, m.context) for m in store.history(fork.id)]
    assert copied == [("tiếp nhé", note), ("Đã xem.", "")]


def test_the_fork_links_what_the_source_linked_with_nothing_seen_read_or_told(store: Store):
    """The fork's agent has read nothing yet; only when a canvas was linked and whether the
    conversation's children share it carry over, and the source keeps its own marks."""
    conv = store.create()
    art = seen_canvas(store, conv)
    store.artifact_links.mark_read(conv.id, art, 1, 0, 10, len(PLAN))
    store.artifacts.write(art, SWIM, USER, "")
    say(store, conv)
    shared = agents_canvas(store, "coach")
    store.artifact_links.link(conv.id, shared, shared=True)
    before = store.artifact_links.links_for(conv.id)
    marks = [
        (link.seen_version, link.read_version, link.read_upto, link.noted_version, link.shared)
        for link in before
    ]
    assert marks == [(2, 1, 10, 2, False), (0, 0, 0, 0, True)]
    fork, _ = store.fork(conv.id, _cut(store, conv.id), autonomous=False)
    copies = [replace(link, conversation_id=fork.id, **FRESH) for link in before]
    assert store.artifact_links.links_for(fork.id) == copies
    assert store.artifact_links.links_for(conv.id) == before


def test_a_canvas_linked_after_the_fork_point_is_left_out(store: Store, monkeypatch):
    """Stamps go to the second, so a canvas linked in the second of the message the fork
    starts at may have come just before it, and is kept."""
    clock = CanvasClock(datetime(2026, 10, 1, 3, 0, tzinfo=UTC))
    conv = store.create()
    with monkeypatch.context() as patch:
        for module in ("message_log", "artifact_links"):
            patch.setattr(f"my_agent_crew.store.{module}.now_iso", lambda: clock.now)
        early = seen_canvas(store, conv, "Trước")
        clock.tick(1)
        cut = _cut(store, conv.id)
        same_second = seen_canvas(store, conv, "Cùng giây")
        clock.tick(1)
        seen_canvas(store, conv, "Sau")
        fork, _ = store.fork(conv.id, cut, autonomous=False)
    linked = [link.artifact_id for link in store.artifact_links.links_for(fork.id)]
    assert linked == [early, same_second]
    assert len(store.artifact_links.links_for(conv.id)) == 3


def test_the_canvas_open_in_the_source_is_not_open_in_the_fork(store: Store):
    conv = store.create()
    art = seen_canvas(store, conv)
    selection = {"version": 1, "text": "bơi", "line_start": 3, "line_end": 3}
    store.artifact_links.set_focus(conv.id, art, selection)
    fork, _ = store.fork(conv.id, _cut(store, conv.id), autonomous=False)
    assert store.artifact_links.focus(fork.id) is None
    focus = store.artifact_links.focus(conv.id)
    assert (focus.artifact_id, focus.selection) == (art, selection)


def test_the_first_note_in_the_fork_tells_of_each_linked_canvas_as_new(store: Store):
    """The source has seen the canvas and hears nothing; the fork has not, and is told."""
    conv = store.create()
    art = seen_canvas(store, conv)
    fork, _ = store.fork(conv.id, _cut(store, conv.id), autonomous=False)
    assert say(store, fork) == framed(CANVAS_NOTE_NEW.format(title="Kế hoạch", id=art, head=1))
    assert say(store, conv) == ""


async def test_a_fork_that_reads_only_the_last_page_cannot_overwrite_the_canvas(store: Store):
    """The source read every line but the last. Its cursor stays with it, so the fork's read
    of the last line does not add up to a read of the whole, while the source's does."""
    conv = turn(store)
    art = agents_canvas(store, "coach", lines_text(5))
    assert (await call(store, "artifact_read", {"id": art, "lines": 4})).ok
    fork, _ = store.fork(conv.id, _cut(store, conv.id), autonomous=False)
    turn(store, fork)
    assert (await call(store, "artifact_read", {"id": art, "from_line": 5})).ok
    rewrite = await call(store, "artifact_rewrite", {"id": art, "content": "mới"})
    assert rewrite.output == TOOL_FAILED.format(error=ARTIFACT_REWRITE_UNSEEN.format(id=art))
    turn(store, conv)
    assert (await call(store, "artifact_read", {"id": art, "from_line": 5})).ok
    assert (seen(store, fork, art), seen(store, conv, art)) == (0, 1)
