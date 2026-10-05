"""Which messages carry what a turn is told of the agent's memory (`agent/turn_notes.py`),
and what happens to it on the way.

Every message that opens a turn carries it: the one a turn begins with, a steer, a batch
that waited in line. The loop's own notes and a turn carried on without a new message carry
none. A fork keeps what its copied messages were told, a conversation begun before messages
carried this still reads its memory, and a builder that fails costs the notes, not the
message."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path

from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.prompt import turn_messages
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store import Store
from my_agent_crew.store.artifact_models import USER
from tests.canvas_helpers import SWIM, seen_canvas
from tests.conftest import collect
from tests.queue_helpers import until
from tests.test_server_api import parse_sse
from tests.turn_notes_helpers import (
    ADDED,
    EARLY,
    NOTHING_NEW,
    RUN,
    WHOLE,
    asked,
    before,
    framed,
    kept,
    told,
    write_note,
)

SLOW = ToolCall("c1", "slow", {})
GUARDED = ToolCall("g1", "guarded", {})
GROWN = f"{EARLY}\n{RUN}\n"


async def test_a_steer_carries_what_changed_since_the_turn_began(rigs):
    rig = rigs([completion(tool_calls=[SLOW]), completion("đã thêm X")])
    title = write_note(rig.deps, EARLY)
    first = asyncio.create_task(collect(rig.inbound.stream(rig.conv.id, "làm việc chậm")))
    await asyncio.wait_for(rig.slow.started.wait(), 2)
    write_note(rig.deps, GROWN)
    await collect(rig.inbound.stream(rig.conv.id, "/steer thêm X"))
    rig.slow.release.set()
    await asyncio.wait_for(first, 2)

    began, steered = (list(request.messages) for request in rig.provider.requests)
    assert steered[: len(began)] == began
    assert began[1].content == before("làm việc chậm", told(WHOLE, title, EARLY))
    assert steered[-1].content == before("thêm X", told(ADDED, title, RUN))
    assert rig.history()[-2] == ("user", "thêm X")  # stored as the person wrote it


async def test_what_waited_in_line_is_delivered_with_what_changed_meanwhile(rigs):
    rig = rigs([completion(tool_calls=[SLOW]), completion("xong"), completion("đã đọc")])
    title = write_note(rig.deps, EARLY)
    first = asyncio.create_task(collect(rig.inbound.stream(rig.conv.id, "việc 1")))
    await asyncio.wait_for(rig.slow.started.wait(), 2)
    await collect(rig.inbound.stream(rig.conv.id, "tin 2"))
    await collect(rig.inbound.stream(rig.conv.id, "tin 3"))
    write_note(rig.deps, GROWN)
    rig.slow.release.set()
    await asyncio.wait_for(first, 2)
    await until(lambda: rig.statuses() == ["done", "done"])

    answered = list(rig.provider.requests[-1].messages)
    assert answered[-1].content == before("tin 2\n\ntin 3", told(ADDED, title, RUN))
    assert rig.history()[-2:] == [("user", "tin 2\n\ntin 3"), ("assistant", "đã đọc")]


async def test_a_turn_carried_on_after_a_decision_reads_what_it_read_and_nothing_new(served):
    """No message opens it, so nothing is told: the note saved while the person decided
    reaches the conversation with its next message."""
    app = served([completion(tool_calls=[GUARDED]), completion("đã ghi"), completion("ok")])
    deps, conv = app.runtime.default, app.conv
    title = write_note(deps, EARLY)
    await app.client.post(app.messages, json={"text": "làm đi"})
    approval = deps.store.approvals.pending(conv.id)
    write_note(deps, GROWN)
    decided = await app.client.post(f"{app.detail}/approvals/{approval.id}", json={"approve": True})
    assert parse_sse(decided.text)[-1]["type"] == "done"
    await app.client.post(app.messages, json={"text": "tiếp"})

    asking, carried_on, next_turn = (list(request.messages) for request in app.provider.requests)
    assert carried_on[: len(asking)] == asking
    assert not any("chạy 5 km" in message.content for message in carried_on)
    assert next_turn[-1].content == before("tiếp", told(ADDED, title, RUN))
    told_by = [bool(notes) for notes in kept(deps, conv.id)]
    roles = [stored.message.role for stored in deps.store.history(conv.id)]
    assert [role for role, has in zip(roles, told_by, strict=True) if has] == ["user", "user"]
    # The screen is given the message as written, and nothing of what the model read first.
    shown = (await app.client.get(app.detail)).json()["messages"][0]
    assert shown["content"] == "làm đi" and "turn_notes" not in shown


async def test_the_block_stands_in_front_of_the_canvas_note_and_the_message(deps_factory):
    deps = deps_factory(script=[completion("ok")])
    conv = deps.store.create()
    art = seen_canvas(deps.store, conv)
    deps.store.artifacts.write(art, SWIM, USER, "")
    title = write_note(deps, EARLY)
    await collect(run_turn(deps, conv.id, "tiếp nhé"))

    [[_, opening]] = asked(deps)
    canvas_note = deps.store.history(conv.id)[0].context
    assert canvas_note and opening.content == (
        f"{framed(told(WHOLE, title, EARLY))}\n\n{canvas_note}\n\ntiếp nhé"
    )


async def test_a_fork_keeps_what_its_messages_were_told_and_hears_only_what_changed(
    deps_factory,
):
    deps = deps_factory(script=[completion("a"), completion("b"), completion("c")])
    earlier = deps.store.create(agent_id="default", channel="")
    deps.store.update(earlier.id, summary="Đã bàn về giấc ngủ.")
    conv = deps.store.create(agent_id="default", channel="")
    title = write_note(deps, EARLY)
    await collect(run_turn(deps, conv.id, "một"))
    await collect(run_turn(deps, conv.id, "hai"))
    second_message = deps.store.history(conv.id)[2]

    fork, draft = deps.store.fork(conv.id, second_message.id, autonomous=False)
    write_note(deps, GROWN)
    await collect(run_turn(deps, fork.id, "hai khác"))

    source, _, forked = asked(deps)
    assert draft == "hai" and forked[: len(source)] == source
    assert forked[-1].content == before("hai khác", told(ADDED, title, RUN))
    # The summary its first message read stands: a fork has none of its own to compare it
    # with, and is not told that one is gone.
    said = "\n".join(message.content for message in forked)
    assert said.count("Đã bàn về giấc ngủ.") == 1 and "nay đã trống" not in said


async def test_a_conversation_begun_before_messages_carried_this_still_reads_its_memory(
    deps_factory,
):
    """Until its next message is stored with all of it, the memory as it is now is read in
    front of its first message, which is where it used to end the system prompt for."""
    deps = deps_factory(script=[completion("ok")])
    conv = deps.store.create()
    title = write_note(deps, EARLY)
    for role, text in (("user", "chào"), ("assistant", "chào bạn"), ("user", "tiếp")):
        deps.store.append(conv.id, Message(role=role, content=text))

    sent = turn_messages(deps, deps.store.get(conv.id), deps.store.history(conv.id))
    whole = told(WHOLE, title, EARLY)
    assert [m.content for m in sent[1:]] == [before("chào", whole), "chào bạn", "tiếp"]

    await collect(run_turn(deps, conv.id, "nữa"))
    [carried] = asked(deps)
    assert [m.content for m in carried[1:]] == ["chào", "chào bạn", "tiếp", before("nữa", whole)]


def test_an_older_database_gains_the_column_and_its_messages_were_told_nothing(tmp_path: Path):
    path = tmp_path / "agent.sqlite3"
    first = Store(path)
    conv = first.create()
    first.append(conv.id, Message(role="user", content="chào"))
    first.close()
    old = sqlite3.connect(path)
    old.execute("ALTER TABLE messages DROP COLUMN turn_notes")
    old.commit()
    old.close()

    store = Store(path)

    assert [stored.turn_notes for stored in store.history(conv.id)] == [""]
    store.append(conv.id, Message(role="user", content="tiếp"), turn_notes=lambda: NOTHING_NEW)
    assert store.messages.turn_notes(conv.id) == [NOTHING_NEW]
    assert [stored.turn_notes for stored in store.history(conv.id)] == ["", NOTHING_NEW]
    store.close()


def test_notes_that_cannot_be_built_cost_the_notes_and_not_the_message(store: Store, caplog):
    conv = store.create()

    def broken() -> str:
        raise OSError("không đọc được thư mục ghi chú")

    with caplog.at_level(logging.ERROR):
        stored = store.append(conv.id, Message(role="user", content="chào"), turn_notes=broken)

    assert (stored.message.content, stored.turn_notes) == ("chào", "")
    assert [m.message.content for m in store.history(conv.id)] == ["chào"]
    assert f"turn notes for conversation {conv.id} failed" in caplog.text


async def test_notes_that_are_not_what_was_stored_are_read_as_nothing(deps_factory):
    """A row someone edited by hand must not stop the conversation from being read."""
    deps = deps_factory(script=[completion("ok")])
    conv = deps.store.create()
    title = write_note(deps, EARLY)
    for raw in ("không phải JSON", '{"sections": [{"mode": "lạ"}, 7]}', '{"other": 1}', "[]"):
        deps.store.append(conv.id, Message(role="user", content="cũ"), turn_notes=lambda r=raw: r)
    await collect(run_turn(deps, conv.id, "chào"))

    [sent] = asked(deps)
    whole = before("chào", told(WHOLE, title, EARLY))
    assert [m.content for m in sent[1:]] == ["cũ", "cũ", "cũ", "cũ", whole]
