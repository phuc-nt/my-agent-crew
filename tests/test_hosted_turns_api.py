"""Turns the server reads itself (`turn_host.py`, `server/routes_turn.py`): a message, a
decision and an answer sent from the web start a turn that runs to its end whoever is
still reading; a tab that opens late is handed the conversation as it stands with the
answer being written, then follows the turn; `stop` ends it for everyone. A turn another
reader owns (a bot, a job, a relay) can be watched the same way and stays its reader's."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections.abc import AsyncIterator
from typing import Any

import pytest

from my_agent_crew import texts
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.server import create_app
from my_agent_crew.server.routes_turn import sse_frames
from my_agent_crew.tools.ask_user import ASK_USER_TOOL_NAME
from tests.conftest import collect
from tests.queue_helpers import Served, settle_loop, until
from tests.test_server_api import parse_sse

SLOW = ToolCall("c1", "slow", {})
GUARDED = ToolCall("g1", "guarded", {})
ASK = ToolCall("q1", ASK_USER_TOOL_NAME, {"question": "A hay B?", "options": ["A", "B"]})
WORK = [completion(tool_calls=[SLOW]), completion("xong rồi")]


def watching(app: Served) -> AsyncIterator[dict[str, str]]:
    """What `GET …/turn` streams, read a message at a time: over HTTP the test client hands
    a stream back only once it has ended."""
    frames = app.runtime.hub.turns.join(app.conv.id)
    assert frames is not None
    return sse_frames(app.runtime.default, app.conv.id, frames)


async def read(stream: AsyncIterator[dict[str, str]], count: int) -> list[dict[str, Any]]:
    async with asyncio.timeout(2):
        return [parse_sse(_wire(await anext(stream)))[0] for _ in range(count)]


async def rest(stream: AsyncIterator[dict[str, str]]) -> list[dict[str, Any]]:
    async with asyncio.timeout(2):
        return [parse_sse(_wire(message))[0] async for message in stream]


def _wire(message: dict[str, str]) -> str:
    return f"event: {message['event']}\ndata: {message['data']}\n\n"


def kinds(events: list[dict[str, Any]]) -> list[str]:
    return [event["type"] for event in events]


def shown(detail: dict[str, Any]) -> list[tuple[str, str]]:
    return [(m["role"], m["content"]) for m in detail["messages"]]


def history(app: Served) -> list[tuple[str, str]]:
    stored = app.runtime.store.history(app.conv.id)
    return [(m.message.role, m.message.content) for m in stored]


async def test_a_conversation_with_no_turn_has_nothing_to_watch(served):
    app = served([completion("xin chào")])
    assert (await app.client.get(app.turn)).status_code == 204
    assert (await app.client.get("/api/conversations/nope/turn")).status_code == 404
    sent = await app.client.post(app.messages, json={"text": "chào"})
    assert kinds(parse_sse(sent.text))[-1] == "done"
    assert (await app.client.get(app.turn)).status_code == 204  # over: nothing to watch


async def test_the_sender_reads_its_turn_as_before(served):
    app = served([completion("xin chào")])
    events = parse_sse((await app.client.post(app.messages, json={"text": "chào"})).text)
    assert "watching" not in kinds(events)  # there from the first event: nothing to rebuild
    assert kinds(events)[-2:] == ["assistant_message", "done"]
    assert "".join(e["text"] for e in events if e["type"] == "text_delta") == "xin chào"


async def test_a_tab_that_opens_late_gets_the_turn_as_it_stands_then_follows_it(served):
    app = served(WORK, paused=(1,))
    sender = asyncio.create_task(app.client.post(app.messages, json={"text": "làm đi"}))
    await asyncio.wait_for(app.slow.started.wait(), 2)
    during_the_tool = watching(app)
    [first] = await read(during_the_tool, 1)
    assert (first["type"], first["running"]) == ("watching", True)
    # The call is stored and has no result yet: the tab draws it as running.
    assert shown(first["detail"]) == [("user", "làm đi"), ("assistant", "")]
    assert first["detail"]["messages"][-1]["tool_calls"][0]["id"] == SLOW.id
    app.slow.release.set()
    await asyncio.wait_for(app.provider.written(1).wait(), 2)
    while_writing = watching(app)
    [second, replayed] = await read(while_writing, 2)
    assert second["type"] == "watching"
    assert shown(second["detail"])[-1] == ("tool", "xong")
    assert replayed == {"type": "text_delta", "text": "xong rồi"}  # all of it, as one piece
    app.provider.finish(1)
    assert kinds(await rest(while_writing)) == ["assistant_message", "done"]
    followed = await rest(during_the_tool)
    assert kinds(followed)[:1] == ["tool_result"]
    assert kinds(followed)[-2:] == ["assistant_message", "done"]
    assert "watching" not in kinds(followed)  # it kept up: never told to start over
    assert kinds(parse_sse((await asyncio.wait_for(sender, 2)).text))[-1] == "done"


async def test_what_a_late_tab_is_handed_and_what_follows_make_the_turn_exactly_once(served):
    app = served(WORK)
    sender = asyncio.create_task(app.client.post(app.messages, json={"text": "làm đi"}))
    await asyncio.wait_for(app.slow.started.wait(), 2)
    late = asyncio.create_task(app.client.get(app.turn))
    await settle_loop()
    app.slow.release.set()
    await asyncio.wait_for(sender, 2)
    first, *followed = parse_sse((await asyncio.wait_for(late, 2)).text)
    assert first["type"] == "watching" and kinds(followed)[-1] == "done"
    handed = [m["id"] for m in first["detail"]["messages"] if m["role"] == "assistant"]
    after = [e["message_id"] for e in followed if e["type"] == "assistant_message"]
    stored = app.runtime.store.history(app.conv.id)
    assert handed + after == [m.id for m in stored if m.message.role == "assistant"]
    results = [m for m in first["detail"]["messages"] if m["role"] == "tool"]
    assert len(results) + kinds(followed).count("tool_result") == 1


async def test_a_sender_that_leaves_does_not_end_its_turn(served):
    app = served(WORK)
    sender = asyncio.create_task(app.client.post(app.messages, json={"text": "làm đi"}))
    await asyncio.wait_for(app.slow.started.wait(), 2)
    sender.cancel()  # the tab was closed
    await asyncio.gather(sender, return_exceptions=True)
    await settle_loop()
    assert app.statuses() == ["running"]
    app.slow.release.set()
    await until(lambda: app.statuses() == ["done"])
    assert history(app)[-1] == ("assistant", "xong rồi")
    assert not app.runtime.hub.busy.busy(app.conv.id)


async def test_stop_ends_the_turn_for_everyone_watching_it(served):
    app = served(WORK)
    sender = asyncio.create_task(app.client.post(app.messages, json={"text": "làm đi"}))
    await asyncio.wait_for(app.slow.started.wait(), 2)
    other = watching(app)
    assert kinds(await read(other, 1)) == ["watching"]
    stopped = await app.client.post(app.stop)
    assert stopped.json() == {"cleared": [], "cancelled": True}
    assert await rest(other) == []  # nothing more to read, and no end that never came
    assert "done" not in kinds(parse_sse((await asyncio.wait_for(sender, 2)).text))
    await until(lambda: app.statuses() == ["error"])
    assert (await app.client.get(app.turn)).status_code == 204
    again = await app.client.post(app.stop)
    assert again.json() == {"cleared": [], "cancelled": False}


async def test_deleting_a_conversation_ends_the_turn_the_server_reads_for_it(served, caplog):
    """Once it is gone nothing on the web could stop its turn, so the delete does: the call
    under way is cut, and no model is asked what to make of it."""
    app = served(WORK)
    sender = asyncio.create_task(app.client.post(app.messages, json={"text": "làm đi"}))
    await asyncio.wait_for(app.slow.started.wait(), 2)
    other = watching(app)
    assert kinds(await read(other, 1)) == ["watching"]
    deleted = await app.client.delete(app.detail)
    assert deleted.status_code == 204
    assert await rest(other) == []
    assert "done" not in kinds(parse_sse((await asyncio.wait_for(sender, 2)).text))
    await until(lambda: app.statuses() == ["error"])
    [run] = app.runtime.hub.recent(conversation_ids=[app.conv.id])
    assert run.summary == "interrupted"
    assert not app.runtime.hub.busy.busy(app.conv.id)
    assert (app.slow.runs, app.provider.calls) == (1, 1)
    # A turn cut under a conversation that is gone ends quietly: it has nothing left to write.
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


async def test_deleting_a_conversation_cuts_the_model_call_under_way(served):
    app = served([completion("không ai đọc")], held=(0,))
    sender = asyncio.create_task(app.client.post(app.messages, json={"text": "hỏi"}))
    await asyncio.wait_for(app.provider.started(0).wait(), 2)
    assert (await app.client.delete(app.detail)).status_code == 204
    # The call is never let go: one that ran on would keep its sender here for good.
    assert "done" not in kinds(parse_sse((await asyncio.wait_for(sender, 2)).text))
    await until(lambda: app.statuses() == ["error"])
    assert not app.runtime.hub.busy.busy(app.conv.id)


async def test_a_delete_that_fails_leaves_the_turn_running(served, monkeypatch):
    app = served(WORK)
    sender = asyncio.create_task(app.client.post(app.messages, json={"text": "làm đi"}))
    await asyncio.wait_for(app.slow.started.wait(), 2)

    def locked(conv_id: str) -> None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(app.runtime.store, "delete", locked)
    with pytest.raises(sqlite3.OperationalError):
        await app.client.delete(app.detail)
    await settle_loop()
    assert app.statuses() == ["running"]
    app.slow.release.set()
    assert kinds(parse_sse((await asyncio.wait_for(sender, 2)).text))[-1] == "done"
    assert history(app)[-1] == ("assistant", "xong rồi")


async def test_a_message_that_waits_does_not_take_the_turn_from_those_watching_it(served):
    app = served([*WORK, completion("trả lời 2")])
    sender = asyncio.create_task(app.client.post(app.messages, json={"text": "việc 1"}))
    await asyncio.wait_for(app.slow.started.wait(), 2)
    other = watching(app)
    assert kinds(await read(other, 1)) == ["watching"]
    [queued] = parse_sse((await app.client.post(app.messages, json={"text": "tin 2"})).text)
    assert queued["type"] == "queued"
    app.slow.release.set()
    # Both still follow the first turn to its own end.
    assert kinds(parse_sse((await asyncio.wait_for(sender, 2)).text))[-1] == "done"
    assert kinds(await rest(other))[-2:] == ["assistant_message", "done"]
    await until(lambda: app.statuses() == ["done", "done"])
    assert history(app)[-2:] == [("user", "tin 2"), ("assistant", "trả lời 2")]


async def test_a_decision_starts_a_turn_the_server_reads_to_its_end(served):
    app = served([completion(tool_calls=[GUARDED]), *WORK])
    *_, pause = parse_sse((await app.client.post(app.messages, json={"text": "làm đi"})).text)
    assert pause["type"] == "approval_required"
    # Waiting for a person is not a turn under way.
    assert (await app.client.get(app.turn)).status_code == 204
    url = f"{app.detail}/approvals/{pause['approval_id']}"
    decided = asyncio.create_task(app.client.post(url, json={"approve": True}))
    await asyncio.wait_for(app.slow.started.wait(), 2)
    [first] = await read(watching(app), 1)
    assert (first["type"], first["detail"]["pending_approval"]) == ("watching", None)
    decided.cancel()  # the tab that said yes was closed
    await asyncio.gather(decided, return_exceptions=True)
    app.slow.release.set()
    await until(lambda: app.statuses() == ["done"])
    assert (app.guarded.runs, history(app)[-1]) == (1, ("assistant", "xong rồi"))


async def test_an_answer_starts_a_turn_the_server_reads_to_its_end(served):
    app = served([completion(tool_calls=[ASK]), *WORK])
    *_, pause = parse_sse((await app.client.post(app.messages, json={"text": "hỏi đi"})).text)
    assert (pause["type"], pause["kind"]) == ("approval_required", "question")
    url = f"{app.detail}/approvals/{pause['approval_id']}/answer"
    answered = asyncio.create_task(app.client.post(url, json={"answer": "B"}))
    await asyncio.wait_for(app.slow.started.wait(), 2)
    answered.cancel()
    await asyncio.gather(answered, return_exceptions=True)
    stopped = await app.client.post(app.stop)  # and it is the server's to end, like any other
    assert stopped.json() == {"cleared": [], "cancelled": True}
    await until(lambda: app.statuses() == ["error"])


async def test_a_turn_another_reader_owns_can_be_watched_and_is_not_the_webs_to_end(served):
    app = served(WORK)
    reader = asyncio.create_task(collect(app.runtime.inbound.stream(app.conv.id, "làm đi")))
    await asyncio.wait_for(app.slow.started.wait(), 2)
    other = watching(app)
    assert kinds(await read(other, 1)) == ["watching"]
    stopped = await app.client.post(app.stop)
    assert stopped.json() == {"cleared": [], "cancelled": False}
    app.slow.release.set()
    assert type(await asyncio.wait_for(reader, 2)).__name__ == "list"
    assert kinds(await rest(other))[-2:] == ["assistant_message", "done"]
    assert app.statuses() == ["done"]


async def test_a_turn_that_breaks_inside_the_server_says_so_to_the_tab(served, monkeypatch, caplog):
    app = served([])

    async def broken(messages, tools, model, reasoning=""):
        raise RuntimeError("hỏng trong server")
        yield  # an async generator, as a provider's stream is

    monkeypatch.setattr(app.provider, "stream", broken)
    events = parse_sse((await app.client.post(app.messages, json={"text": "làm đi"})).text)
    assert events[-1] == {"type": "error", "message": texts.TURN_BROKE}
    await until(lambda: app.statuses() == ["error"])
    assert "failed while the server was reading it" in caplog.text
    assert "hỏng trong server" in caplog.text  # the cause is in the log, not on the page
    assert not app.runtime.hub.busy.busy(app.conv.id)


async def test_a_server_that_shuts_down_ends_the_turns_it_reads(served):
    app = served(WORK)
    web = create_app(app.runtime, schedule=False)
    async with web.router.lifespan_context(web):
        frames = app.runtime.inbound.stream_hosted(app.conv.id, "làm đi")
        await asyncio.wait_for(app.slow.started.wait(), 2)
        assert app.statuses() == ["running"]
    assert app.statuses() == ["error"]
    async with asyncio.timeout(2):
        assert all(type(frame).__name__ != "DoneEvent" for frame in [f async for f in frames])
