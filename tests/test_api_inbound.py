"""`POST /api/inbound`, the one door every platform uses: a message becomes a turn of
today's conversation on a channel, the reply comes back as one JSON message, and a test
can walk master → delegate → answer with nothing but HTTP."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import API, DELEGATE
from my_agent_crew.config import load_settings
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.server import build_runtime, create_app
from my_agent_crew.store.models import AWAITING_APPROVAL


@pytest.fixture
def crew(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo", "MY_AGENT_AUTONOMOUS": "1"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False)) as client:
        yield client, runtime


def test_a_message_opens_todays_conversation_on_the_channel_and_is_answered(crew):
    client, runtime = crew

    res = client.post("/api/inbound", json={"text": "xin chào"})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["agent_id"] == "default" and body["text"] == "(echo) xin chào"
    assert body["status"] == "done" and body["steps"] == 1
    conv = runtime.store.get(body["conversation_id"])
    assert conv.channel == API and conv.title == f"{API} · {datetime.now().date().isoformat()}"
    # The next message of the day lands in the same conversation; a person's chat window
    # is one thread, whatever platform it is on.
    again = client.post("/api/inbound", json={"text": "còn đó không"}).json()
    assert again["conversation_id"] == conv.id
    history = client.get(f"/api/conversations/{conv.id}").json()["messages"]
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]
    [run] = [r for r in runtime.hub.recent() if r.id == runtime.hub.recent()[0].id]
    assert run.source == API and run.conversation_id == conv.id


def test_a_new_day_opens_another_conversation_on_the_same_channel(crew):
    client, runtime = crew
    first = client.post("/api/inbound", json={"text": "hôm nay"}).json()["conversation_id"]
    tomorrow = datetime.now() + timedelta(days=1)
    replaced: list[str] = []
    runtime.inbound.on_replaced = lambda deps, conv_id: replaced.append(conv_id)

    conv = runtime.inbound.conversation_for("default", API, clock=lambda: tomorrow)

    assert conv.id != first and conv.channel == API
    assert runtime.store.latest_for_channel("default", API).id == conv.id
    # The closed one is handed over for a recap, as a Telegram day's is.
    assert replaced == [first]


def test_channels_and_explicit_conversations_are_kept_apart(crew):
    client, _ = crew
    web = client.post("/api/conversations", json={"title": "riêng"}).json()
    slack = client.post("/api/inbound", json={"text": "a", "channel": "slack:team"}).json()
    api = client.post("/api/inbound", json={"text": "b"}).json()
    into_web = client.post(
        "/api/inbound", json={"text": "c", "conversation_id": web["id"], "source": "chat"}
    ).json()

    assert len({slack["conversation_id"], api["conversation_id"], web["id"]}) == 3
    assert into_web["conversation_id"] == web["id"] and into_web["text"] == "(echo) c"


def test_unknown_agents_and_conversations_are_refused(crew):
    client, _ = crew
    missing = client.post("/api/inbound", json={"text": "a", "agent_id": "ghost"})
    assert missing.status_code == 404 and "ghost" in missing.json()["detail"]
    gone = client.post("/api/inbound", json={"text": "a", "conversation_id": "nope"})
    assert gone.status_code == 404


def test_a_conversation_waiting_on_an_approval_refuses_new_messages(crew):
    client, runtime = crew
    conv_id = client.post("/api/inbound", json={"text": "a"}).json()["conversation_id"]
    runtime.store.update(conv_id, status=AWAITING_APPROVAL)

    res = client.post("/api/inbound", json={"text": "b"})

    assert res.status_code == 409


def test_the_master_delegates_and_the_childs_answer_comes_back_over_http(crew):
    """The whole product in two requests: install a specialist, then ask the master for
    something it hands over. No browser, no bot."""
    client, runtime = crew
    assert client.post("/api/agents/install", json={"template": "researcher"}).status_code == 201
    prompt = '/tool delegate {"agent": "researcher", "task": "tìm ba nguồn về sqlite"}'

    res = client.post("/api/inbound", json={"text": prompt})

    body = res.json()
    assert res.status_code == 200 and body["status"] == "done"
    assert body["agent_id"] == "default" and body["steps"] == 2
    [child] = runtime.store.list("researcher")
    assert "sqlite" in child.title
    assert "Kết quả công cụ delegate" in body["text"]
    sources = {r.source.split(":")[0] for r in runtime.hub.recent()}
    assert sources == {API, DELEGATE}


def test_how_a_turn_ended_is_reported_with_the_text(deps_factory):
    """Platforms without a stream still learn why the reply stopped short."""
    # Two blanks, because the loop retries the first one rather than calling a silent
    # turn finished.
    deps = deps_factory(script=[ProviderError("model down"), completion("   "), completion("   ")])
    with TestClient(create_app(deps, schedule=False)) as client:
        failed = client.post("/api/inbound", json={"text": "a"}).json()
        assert failed["status"] == "error"
        assert failed["text"].startswith(texts.REPLY_ERROR.format(message=""))
        silent = client.post("/api/inbound", json={"text": "b"}).json()
        assert silent["status"] == "error"
        assert texts.BLANK_COMPLETION.format(provider="scripted", model="m") in silent["text"]
