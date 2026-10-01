"""A person's message lands in one transaction with its canvas note and with what the note
marks as told: when any step fails none of it lands, and the next message tells it again. A
note that cannot be built never costs the person their message. A message handed over from
the queue hears the open canvas only when it came from the web chat."""

from __future__ import annotations

import logging
import sqlite3
from functools import partial

import pytest

from my_agent_crew.agent.turn_context import CHAT, TELEGRAM, set_turn_conversation, set_turn_source
from my_agent_crew.llm.types import Message
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.canvas_note import Note
from my_agent_crew.store.db import Store
from my_agent_crew.store.messages import MessageStore
from my_agent_crew.store.models import Conversation
from my_agent_crew.store.queue import FOLLOW_UP, STEER
from my_agent_crew.store.stamps import now_iso
from my_agent_crew.texts_canvas import CANVAS_NOTE_PICK, PICK_LINES
from tests.canvas_helpers import PLAN, SWIM, created, edited, framed, noted, say, seen, turn

PICK = {"version": 2, "text": "bơi 1 km", "line_start": 3, "line_end": 3}


class _Conn:
    """The store's connection with one kind of statement, or the commit, made to fail."""

    def __init__(
        self, real: sqlite3.Connection, blocks: str | None = None, commit_fails: bool = False
    ):
        self._real = real
        self._blocks = blocks
        self._commit_fails = commit_fails

    def execute(self, sql: str, *args):
        if self._blocks is not None and sql.strip().startswith(self._blocks):
            raise sqlite3.OperationalError("hỏng")
        return self._real.execute(sql, *args)

    def commit(self) -> None:
        if self._commit_fails:
            raise sqlite3.OperationalError("hỏng")
        self._real.commit()

    def __getattr__(self, name: str):
        return getattr(self._real, name)


@pytest.fixture(autouse=True)
def fresh_turn():
    set_turn_source(CHAT)
    set_turn_conversation("")
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


async def _edited_and_picked(store: Store) -> tuple[Conversation, str]:
    """A canvas the agent made and the person then edited, open on the web with a passage
    selected: the next message's note carries a mark of every kind."""
    conv = turn(store)
    art = await created(store, PLAN)
    store.artifacts.write(art, SWIM, USER, "")
    store.artifact_links.set_focus(conv.id, art, PICK)
    return conv, art


def _full_note(art: str) -> str:
    where = PICK_LINES.format(span="3", version=2)
    pick = CANVAS_NOTE_PICK.format(title="Kế hoạch", id=art, where=where)
    return framed(pick, "> bơi 1 km", *edited("Kế hoạch", art))


def _untold(store: Store, conv: Conversation, art: str) -> None:
    """Nothing of the note landed: no message, nothing marked as told."""
    assert store.history(conv.id) == []
    assert (seen(store, conv, art), noted(store, conv, art)) == (1, 0)
    focus = store.artifact_links.focus(conv.id)
    assert (focus.selection, focus.noted) == (PICK, False)


def _waiting(store: Store, conv: Conversation) -> list[str]:
    return [item.text for item in store.queue.peek_all(conv.id)]


async def test_the_message_its_note_and_what_the_note_marks_land_together(store: Store):
    conv, art = await _edited_and_picked(store)
    context = say(store, conv)
    assert context == _full_note(art)
    assert store.history(conv.id)[-1].context == context
    assert (seen(store, conv, art), noted(store, conv, art)) == (2, 2)
    focus = store.artifact_links.focus(conv.id)
    assert (focus.selection, focus.noted) == (None, True)
    assert store._conn.in_transaction is False


@pytest.mark.parametrize(
    ("owner", "blocks", "commit_fails"),
    [
        ("messages", "INSERT INTO messages", False),
        # The open canvas's mark is written first, so this one fails after a write.
        ("artifact_links", "UPDATE conversation_artifacts", False),
        ("messages", "UPDATE conversations", False),
        ("messages", None, True),
    ],
)
async def test_a_message_that_fails_to_land_takes_its_note_and_marks_with_it(
    store: Store, monkeypatch: pytest.MonkeyPatch, owner: str, blocks: str | None, commit_fails
):
    conv, art = await _edited_and_picked(store)
    part = getattr(store, owner)
    with monkeypatch.context() as patch:
        patch.setattr(part, "_conn", _Conn(part._conn, blocks, commit_fails))
        with pytest.raises(sqlite3.OperationalError):
            say(store, conv)
    store.create()  # a later commit must carry none of it
    _untold(store, conv, art)
    assert say(store, conv) == _full_note(art)


def test_a_message_for_an_unknown_conversation_lands_no_mark(store: Store):
    conv = store.create()
    art = store.artifacts.create("Kế hoạch", "markdown", "coach", "agent:coach", "", PLAN).id
    store.artifact_links.mark_seen(conv.id, art, 1)
    mark = partial(store.artifact_links.mark_noted, conv.id, art, 5, commit=False)
    messages = MessageStore(store._conn, store._lock, lambda _conv, _source: Note("x", (mark,)))
    message = Message(role="user", content="tiếp nhé")
    with pytest.raises(KeyError):
        messages.append("không-có", message, now_iso(), note_source=CHAT)
    store.create()
    assert noted(store, conv, art) == 0


async def test_a_note_that_fails_to_build_costs_the_person_nothing(
    store: Store, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """The message is stored without a note and nothing is marked, so the next message
    tells what this one could not."""
    conv, art = await _edited_and_picked(store)

    def broken(conversation_id: str):
        raise sqlite3.OperationalError("hỏng")

    with monkeypatch.context() as patch, caplog.at_level(logging.ERROR):
        patch.setattr(store.artifact_links, "links_for", broken)
        assert say(store, conv) == ""
    assert [stored.message.content for stored in store.history(conv.id)] == ["tiếp nhé"]
    assert [r.levelno for r in caplog.records if r.name == "my_agent_crew.store.messages"] == [
        logging.ERROR
    ]
    assert (seen(store, conv, art), noted(store, conv, art)) == (1, 0)
    assert say(store, conv) == _full_note(art)


async def test_a_handover_that_fails_keeps_the_queue_and_leaves_the_note_untold(
    store: Store, monkeypatch: pytest.MonkeyPatch
):
    conv, art = await _edited_and_picked(store)
    store.queue.add(conv.id, FOLLOW_UP, "tiếp nhé", CHAT)
    ids = [item.id for item in store.queue.peek_all(conv.id)]
    monkeypatch.setattr(store.messages, "_conn", _Conn(store._conn, commit_fails=True))
    with pytest.raises(sqlite3.OperationalError):
        store.queue.deliver(conv.id, ids)
    store.create()
    assert _waiting(store, conv) == ["tiếp nhé"]
    _untold(store, conv, art)


def _hand_over(store: Store, conv: Conversation, kind: str) -> None:
    if kind == STEER:
        store.queue.take_steers(conv.id)
    else:
        store.queue.deliver(conv.id, [item.id for item in store.queue.peek_all(conv.id)])


@pytest.mark.parametrize("kind", [FOLLOW_UP, STEER])
async def test_a_message_handed_over_from_telegram_hears_the_change_but_not_the_open_canvas(
    store: Store, kind: str
):
    """The canvas open on the web, and the passage selected there, wait for the web chat's
    next message."""
    conv, art = await _edited_and_picked(store)
    store.queue.add(conv.id, kind, "tiếp nhé", TELEGRAM)
    _hand_over(store, conv, kind)
    assert _waiting(store, conv) == []
    assert store.history(conv.id)[-1].context == framed(*edited("Kế hoạch", art))
    focus = store.artifact_links.focus(conv.id)
    assert (focus.selection, focus.noted) == (PICK, False)


@pytest.mark.parametrize("kind", [FOLLOW_UP, STEER])
async def test_a_message_handed_over_from_the_web_chat_hears_the_open_canvas(
    store: Store, kind: str
):
    conv, art = await _edited_and_picked(store)
    store.queue.add(conv.id, kind, "tiếp nhé", CHAT)
    store.queue.add(conv.id, kind, "và thêm", TELEGRAM)
    _hand_over(store, conv, kind)
    [stored] = store.history(conv.id)
    assert stored.message.content == "tiếp nhé\n\nvà thêm"
    assert stored.context == _full_note(art)
    focus = store.artifact_links.focus(conv.id)
    assert (focus.selection, focus.noted) == (None, True)


async def test_only_a_persons_message_from_a_source_is_given_a_note(store: Store):
    """The loop's own notes to the model and the agent's replies carry no canvas note and
    mark nothing as told."""
    conv, art = await _edited_and_picked(store)
    guard_note = Message(role="user", content="ghi chú của vòng lặp")
    assert store.append(conv.id, guard_note).context == ""
    reply = Message(role="assistant", content="ok")
    assert store.append(conv.id, reply, note_source=CHAT).context == ""
    assert (seen(store, conv, art), noted(store, conv, art)) == (1, 0)
    focus = store.artifact_links.focus(conv.id)
    assert (focus.selection, focus.noted) == (PICK, False)
