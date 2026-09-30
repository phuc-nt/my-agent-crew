from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import load_settings
from my_agent_crew.llm.types import Message
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime_build import build_runtime

FAKE_KEY = "sk-khong-duoc-lo-ra-12345"


def user(text: str) -> Message:
    return Message(role="user", content=text)


@pytest.fixture
def crew(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    env = {
        "MY_AGENT_HOME": str(home),
        "MY_AGENT_ROUTES": "fake:echo",
        "OPENROUTER_API_KEY": FAKE_KEY,
        "TELEGRAM_BOT_TOKEN": FAKE_KEY,
    }
    runtime = build_runtime(load_settings(env=env), env=env)
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, runtime


def test_a_hit_comes_back_200_not_the_conversation_not_found_404(crew) -> None:
    # Proves the route sits outside `/conversations/{conv_id}`'s path-parameter match:
    # that route would otherwise catch a literal `/conversations/search` first and answer
    # 404 "conversation not found" instead of ever reaching this one.
    client, runtime = crew
    conv = runtime.store.create(agent_id="default")
    runtime.store.append(conv.id, user("Tôi muốn đọc sách"))

    reply = client.get("/api/messages/search", params={"q": "doc"})

    assert reply.status_code == 200
    hits = reply.json()["hits"]
    assert len(hits) == 1
    assert hits[0]["conversation_id"] == conv.id
    assert hits[0]["snippet"] == "Tôi muốn đọc sách"
    assert hits[0]["agent_id"] == "default"


def test_agent_id_narrows_the_search_to_that_agent_only(crew) -> None:
    client, runtime = crew
    conv_default = runtime.store.create(agent_id="default")
    conv_coach = runtime.store.create(agent_id="coach")
    runtime.store.append(conv_default.id, user("nội dung agent mặc định"))
    runtime.store.append(conv_coach.id, user("nội dung agent coach"))

    reply = client.get("/api/messages/search", params={"q": "nội dung agent", "agent_id": "coach"})

    hits = reply.json()["hits"]
    assert [h["agent_id"] for h in hits] == ["coach"]


def test_an_unknown_agent_id_returns_no_hits_not_an_error(crew) -> None:
    client, runtime = crew
    conv = runtime.store.create(agent_id="default")
    runtime.store.append(conv.id, user("một câu bất kỳ"))

    reply = client.get("/api/messages/search", params={"q": "một câu", "agent_id": "khong-ton-tai"})

    assert reply.status_code == 200
    assert reply.json() == {"hits": []}


def test_an_empty_query_returns_no_hits_not_an_error(crew) -> None:
    client, _ = crew

    reply = client.get("/api/messages/search", params={"q": ""})

    assert reply.status_code == 200
    assert reply.json() == {"hits": []}


def test_limit_below_one_is_422(crew) -> None:
    client, _ = crew

    reply = client.get("/api/messages/search", params={"q": "abc", "limit": 0})

    assert reply.status_code == 422


def test_limit_above_fifty_is_422(crew) -> None:
    client, _ = crew

    reply = client.get("/api/messages/search", params={"q": "abc", "limit": 51})

    assert reply.status_code == 422


def test_default_search_covers_every_agent_since_the_caller_is_the_owner(crew) -> None:
    client, runtime = crew
    conv_default = runtime.store.create(agent_id="default")
    conv_coach = runtime.store.create(agent_id="coach")
    runtime.store.append(conv_default.id, user("chủ đề chung của hai agent"))
    runtime.store.append(conv_coach.id, user("chủ đề chung của hai agent"))

    reply = client.get("/api/messages/search", params={"q": "chủ đề chung"})

    hits = reply.json()["hits"]
    assert {h["agent_id"] for h in hits} == {"default", "coach"}
