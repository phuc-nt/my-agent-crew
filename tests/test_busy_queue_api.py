"""The busy queue over HTTP: a message the web or a relay sends while its conversation is
busy is answered with its place in line, the conversation shows what waits, and `stop`
hands the waiting messages back and ends the turn the queue runs, never a turn that
someone else is reading. A server answers what waited through a restart as it starts,
unless it was started to start nothing on its own."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import pytest
from fastapi.testclient import TestClient

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import CHAT
from my_agent_crew.config import Route
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.server import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store import Conversation
from my_agent_crew.store.queue import FOLLOW_UP, QUEUE_LIMIT, STEER
from my_agent_crew.tools.ask_user import ASK_USER_TOOL_NAME
from tests.queue_helpers import GatedProvider, SlowTool, until
from tests.test_server_api import parse_sse

SLOW = ToolCall("c1", "slow", {})
GUARDED = ToolCall("g1", "guarded", {})
ASK = ToolCall("q1", ASK_USER_TOOL_NAME, {"question": "A hay B?", "options": ["A", "B"]})


@pytest.fixture
def api(deps_factory):
    """The app with its queue drain left idle, so what waits stays put for the test to see.
    A claim taken from the test's thread stands for a turn about to start: no loop runs
    there to let it lapse."""
    runtime = Runtime.single(deps_factory(routes=(Route("fake", "echo"),)))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, runtime


def new_conversation(client: TestClient, title: str = "Thử") -> str:
    return client.post("/api/conversations", json={"title": title}).json()["id"]


def test_a_message_sent_while_busy_is_answered_with_its_place_in_line(api):
    client, runtime = api
    conv_id = new_conversation(client)
    assert client.get(f"/api/conversations/{conv_id}").json()["queued"] == []
    runtime.hub.busy.claim(conv_id)
    sent = [
        client.post(f"/api/conversations/{conv_id}/messages", json={"text": text})
        for text in ("tin 2", "/steer rẽ trái")
    ]
    assert [response.status_code for response in sent] == [200, 200]
    [[follow_up], [steer]] = [parse_sse(response.text) for response in sent]
    assert follow_up == {
        "type": "queued",
        "item_id": follow_up["item_id"],
        "kind": FOLLOW_UP,
        "position": 1,
    }
    assert steer == {"type": "queued", "item_id": steer["item_id"], "kind": STEER, "position": 2}
    waiting = [
        {"id": follow_up["item_id"], "kind": FOLLOW_UP, "text": "tin 2"},
        {"id": steer["item_id"], "kind": STEER, "text": "rẽ trái"},
    ]
    for _ in range(2):  # showing the line leaves it as it was
        assert client.get(f"/api/conversations/{conv_id}").json()["queued"] == waiting


def test_a_bare_steer_and_a_message_past_the_limit_are_refused_with_the_reason(api):
    client, runtime = api
    conv_id = new_conversation(client)
    messages = f"/api/conversations/{conv_id}/messages"
    bare = client.post(messages, json={"text": "/steer"})
    assert (bare.status_code, bare.json()["detail"]) == (422, texts.STEER_NEEDS_TEXT)
    assert not runtime.hub.busy.busy(conv_id)
    runtime.hub.busy.claim(conv_id)
    for n in range(QUEUE_LIMIT):
        runtime.store.queue.add(conv_id, FOLLOW_UP, f"tin {n}", "chat")
    full = texts.QUEUE_FULL.format(limit=QUEUE_LIMIT)
    refused = [
        client.post(messages, json={"text": "tin thừa"}),
        client.post("/api/inbound", json={"text": "tin thừa", "conversation_id": conv_id}),
    ]
    assert [(r.status_code, r.json()["detail"]) for r in refused] == [(429, full)] * 2
    assert runtime.store.queue.count(conv_id) == QUEUE_LIMIT


def test_stop_hands_back_what_waited_and_empties_the_line(api):
    client, runtime = api
    conv_id = new_conversation(client)
    stop = f"/api/conversations/{conv_id}/stop"
    assert client.post(stop).json() == {"cleared": [], "cancelled": False}
    runtime.hub.busy.claim(conv_id)
    for text in ("một", "/steer hai"):
        client.post(f"/api/conversations/{conv_id}/messages", json={"text": text})
    stopped = client.post(stop).json()
    # The turn that holds the conversation is not one the queue started: not its to end.
    assert stopped["cancelled"] is False
    assert [(i["kind"], i["text"]) for i in stopped["cleared"]] == [
        (FOLLOW_UP, "một"),
        (STEER, "hai"),
    ]
    assert client.get(f"/api/conversations/{conv_id}").json()["queued"] == []
    assert client.post("/api/conversations/nope/stop").status_code == 404


def test_a_relay_hears_that_its_message_waits(api):
    client, runtime = api
    conv_id = new_conversation(client)
    runtime.hub.busy.claim(conv_id)
    replies = [
        client.post("/api/inbound", json={"text": text, "conversation_id": conv_id}).json()
        for text in ("tin 2", "/steer rẽ")
    ]
    assert [(r["status"], r["queued"], r["text"], r["steps"]) for r in replies] == [
        ("queued", True, texts.QUEUED_FOLLOW_UP, 0),
        ("queued", True, texts.QUEUED_STEER, 0),
    ]


def test_a_decision_while_an_earlier_one_holds_the_conversation_is_turned_away(deps_factory):
    guarded = SlowTool("guarded", requires_approval=True)
    guarded.release.set()
    provider = ScriptedProvider(
        [
            completion(tool_calls=[GUARDED]),
            completion(tool_calls=[ASK]),
            completion("đã chạy"),
            completion("chọn B"),
        ]
    )
    deps = deps_factory(providers={"scripted": provider}, extra_tools=[guarded.tool])
    runtime = Runtime.single(deps)
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        tool_conv, question_conv = new_conversation(client, "Gọi"), new_conversation(client, "Hỏi")
        pauses = {}
        for conv_id in (tool_conv, question_conv):
            sent = client.post(f"/api/conversations/{conv_id}/messages", json={"text": "làm đi"})
            *_, pause = parse_sse(sent.text)
            assert pause["type"] == "approval_required"
            pauses[conv_id] = f"/api/conversations/{conv_id}/approvals/{pause['approval_id']}"
        decide, answer = pauses[tool_conv], pauses[question_conv] + "/answer"
        for conv_id in (tool_conv, question_conv):
            runtime.hub.busy.claim(conv_id)  # the first click, its turn not read yet
        refused = [
            client.post(decide, json={"approve": True}),
            client.post(answer, json={"answer": "B"}),
        ]
        assert [(r.status_code, r.json()["detail"]) for r in refused] == [
            (409, "approval already resolved")
        ] * 2
        for conv_id in (tool_conv, question_conv):
            runtime.hub.busy.release(conv_id)
        assert parse_sse(client.post(decide, json={"approve": True}).text)[-1]["type"] == "done"
        assert parse_sse(client.post(answer, json={"answer": "B"}).text)[-1]["type"] == "done"
    assert guarded.runs == 1


def wait_for(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.02)


def left_in_line(deps_factory) -> tuple[Runtime, str]:
    """A runtime whose conversation holds a message that waited while the server was down."""
    runtime = Runtime.single(deps_factory(routes=(Route("fake", "echo"),)))
    conv = runtime.store.create("Thử", agent_id=runtime.default.agent.id)
    runtime.store.queue.add(conv.id, FOLLOW_UP, "tin đã chờ", CHAT)
    return runtime, conv.id


def history(client: TestClient, conv_id: str) -> list[tuple[str, str]]:
    messages = client.get(f"/api/conversations/{conv_id}").json()["messages"]
    return [(m["role"], m["content"]) for m in messages]


def test_a_server_answers_what_waited_through_a_restart_as_it_starts(deps_factory):
    runtime, conv_id = left_in_line(deps_factory)
    with TestClient(create_app(runtime), base_url="http://127.0.0.1") as client:
        wait_for(lambda: history(client, conv_id)[-1:] == [("assistant", "(echo) tin đã chờ")])
        assert client.get(f"/api/conversations/{conv_id}").json()["queued"] == []


def test_a_server_started_with_no_schedule_leaves_it_for_the_next_turn(deps_factory):
    runtime, conv_id = left_in_line(deps_factory)
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        sent = client.post(f"/api/conversations/{conv_id}/messages", json={"text": "tin mới"})
        assert parse_sse(sent.text)[-1]["type"] == "done"  # nothing held the conversation
        wait_for(lambda: client.get(f"/api/conversations/{conv_id}").json()["queued"] == [])
        wait_for(lambda: len(history(client, conv_id)) == 4)
        assert history(client, conv_id) == [
            ("user", "tin mới"),
            ("assistant", "(echo) tin mới"),
            ("user", "tin đã chờ"),
            ("assistant", "(echo) tin đã chờ"),
        ]


@dataclass
class Served:
    client: httpx.AsyncClient
    runtime: Runtime
    provider: GatedProvider
    slow: SlowTool
    conv: Conversation

    @property
    def messages(self) -> str:
        return f"/api/conversations/{self.conv.id}/messages"

    @property
    def stop(self) -> str:
        return f"/api/conversations/{self.conv.id}/stop"

    def statuses(self) -> list[str]:
        runs = self.runtime.hub.recent(conversation_ids=[self.conv.id])
        return sorted(run.status for run in runs)


@pytest.fixture
async def served(deps_factory):
    """The app on the test's own event loop, where the queue runs its turns, so `stop`
    reaches the same turns a live server's would."""
    made: list[Served] = []

    def build(script, held=()) -> Served:
        provider, slow = GatedProvider(script, held), SlowTool()
        deps = deps_factory(providers={"scripted": provider}, extra_tools=[slow.tool])
        runtime = Runtime.single(deps)
        transport = httpx.ASGITransport(app=create_app(runtime, schedule=False))
        client = httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1")
        conv = runtime.store.create("Việc thử", agent_id=deps.agent.id)
        made.append(Served(client, runtime, provider, slow, conv))
        return made[-1]

    yield build
    for app in made:
        await app.runtime.drain.stop()
        await app.client.aclose()


async def test_stop_ends_the_turn_the_queue_runs(served):
    app = served(
        [completion(tool_calls=[SLOW]), completion("xong 1"), completion("trả lời 2")], held=(2,)
    )
    first = asyncio.create_task(app.client.post(app.messages, json={"text": "việc 1"}))
    await asyncio.wait_for(app.slow.started.wait(), 2)
    [queued] = parse_sse((await app.client.post(app.messages, json={"text": "tin 2"})).text)
    assert queued["kind"] == FOLLOW_UP
    app.slow.release.set()
    assert parse_sse((await asyncio.wait_for(first, 2)).text)[-1]["type"] == "done"
    await asyncio.wait_for(app.provider.started(2).wait(), 2)  # the queue's turn is under way
    stopped = await app.client.post(app.stop)
    assert stopped.json() == {"cleared": [], "cancelled": True}
    await until(lambda: app.statuses() == ["done", "error"])
    assert not app.runtime.hub.busy.busy(app.conv.id)


async def test_stop_leaves_a_turn_the_web_is_reading(served):
    app = served([completion("một")], held=(0,))
    first = asyncio.create_task(app.client.post(app.messages, json={"text": "tin 1"}))
    await asyncio.wait_for(app.provider.started(0).wait(), 2)
    stopped = await app.client.post(app.stop)
    assert stopped.json() == {"cleared": [], "cancelled": False}
    app.provider.release(0)
    assert parse_sse((await asyncio.wait_for(first, 2)).text)[-1]["type"] == "done"
    assert app.statuses() == ["done"]
