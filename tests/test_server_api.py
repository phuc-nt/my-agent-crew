"""HTTP surface: conversations CRUD, SSE chat, approvals, settings, health."""

import json

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import Route
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.server import create_app
from my_agent_crew.texts import CONVERSATION_TITLE_DEFAULT


@pytest.fixture
def client(deps_factory):
    deps = deps_factory(routes=(Route("fake", "echo"),))
    with TestClient(create_app(deps), base_url="http://127.0.0.1") as c:
        yield c


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        data = [line[5:].strip() for line in block.splitlines() if line.startswith("data:")]
        if data:
            events.append(json.loads("".join(data)))
    return events


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and "version" in body


def test_conversation_crud(client):
    created = client.post("/api/conversations", json={"title": "Thử"}).json()
    assert created["title"] == "Thử" and created["cost_cap_usd"] == 0.5
    assert client.get("/api/conversations").json()[0]["id"] == created["id"]
    patched = client.patch(
        f"/api/conversations/{created['id']}", json={"autonomous": True, "skills": ["k"]}
    ).json()
    assert patched["autonomous"] is True and patched["skills"] == ["k"]
    full = client.get(f"/api/conversations/{created['id']}").json()
    assert full["messages"] == [] and full["pending_approval"] is None
    assert client.delete(f"/api/conversations/{created['id']}").status_code == 204
    assert client.get(f"/api/conversations/{created['id']}").status_code == 404


def test_validation_rejects_negative_cap_and_empty_text(client):
    assert client.post("/api/conversations", json={"cost_cap_usd": -1}).status_code == 422
    conv = client.post("/api/conversations", json={}).json()
    r = client.post(f"/api/conversations/{conv['id']}/messages", json={"text": ""})
    assert r.status_code == 422


def test_chat_streams_events_and_persists(client):
    conv = client.post("/api/conversations", json={}).json()
    with client.stream(
        "POST", f"/api/conversations/{conv['id']}/messages", json={"text": "xin chào"}
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = parse_sse("".join(r.iter_text()))
    kinds = [e["type"] for e in events]
    assert kinds[0] == "text_delta" and kinds[-2:] == ["assistant_message", "done"]
    assert events[-2]["content"] == "(echo) xin chào"
    stored = client.get(f"/api/conversations/{conv['id']}").json()["messages"]
    assert [m["role"] for m in stored] == ["user", "assistant"]


def test_unknown_conversation_is_404(client):
    r = client.post("/api/conversations/nope/messages", json={"text": "hi"})
    assert r.status_code == 404


def test_approval_flow_over_http(client):
    conv = client.post("/api/conversations", json={}).json()
    text = '/tool workspace_write {"path": "x.txt", "content": "1"}'
    with client.stream(
        "POST", f"/api/conversations/{conv['id']}/messages", json={"text": text}
    ) as r:
        events = parse_sse("".join(r.iter_text()))
    assert events[-1]["type"] == "approval_required"
    approval_id = events[-1]["approval_id"]
    detail = client.get(f"/api/conversations/{conv['id']}").json()
    assert detail["pending_approval"]["id"] == approval_id
    assert detail["status"] == "awaiting_approval"
    busy = client.post(f"/api/conversations/{conv['id']}/messages", json={"text": "nữa"})
    assert busy.status_code == 409
    with client.stream(
        "POST",
        f"/api/conversations/{conv['id']}/approvals/{approval_id}",
        json={"approve": True},
    ) as r:
        resumed = parse_sse("".join(r.iter_text()))
    assert [e["type"] for e in resumed][:2] == ["tool_call", "tool_result"]
    assert resumed[-1]["type"] == "done"
    again = client.post(
        f"/api/conversations/{conv['id']}/approvals/{approval_id}", json={"approve": True}
    )
    assert again.status_code == 409


def test_always_allow_skips_the_next_pause_and_lands_in_history(client):
    conv = client.post("/api/conversations", json={}).json()
    text = '/tool workspace_write {"path": "x.txt", "content": "1"}'
    base = f"/api/conversations/{conv['id']}"

    def turn(text: str) -> list[dict]:
        with client.stream("POST", f"{base}/messages", json={"text": text}) as r:
            return parse_sse("".join(r.iter_text()))

    first = turn(text)
    assert first[-1]["type"] == "approval_required" and first[-1]["expires_at"]
    url = f"{base}/approvals/{first[-1]['approval_id']}"
    with client.stream("POST", url, json={"approve": True, "always": True}) as r:
        resumed = parse_sse("".join(r.iter_text()))
    assert resumed[-1]["type"] == "done"
    assert client.get(base).json()["auto_approve"] == ["workspace_write"]

    kinds = [e["type"] for e in turn(text)]
    assert "approval_required" not in kinds and "tool_result" in kinds and kinds[-1] == "done"

    history = client.get("/api/approvals").json()
    assert [(h["status"], h["agent_id"]) for h in history] == [("approved", conv["agent_id"])]
    assert history[0]["resolved_at"] and history[0]["conversation_id"] == conv["id"]

    assert client.patch(base, json={"auto_approve": []}).json()["auto_approve"] == []
    assert turn(text)[-1]["type"] == "approval_required"


def test_settings_never_echo_secrets(deps_factory):
    deps = deps_factory(routes=(Route("fake", "echo"),), openrouter_api_key="sk-secret")
    with TestClient(create_app(deps), base_url="http://127.0.0.1") as c:
        body = c.get("/api/settings").json()
    assert body["keys"]["openrouter"] is True
    assert "sk-secret" not in json.dumps(body)
    assert {t["name"] for t in body["tools"]} >= {"workspace_read", "memory_save"}
    assert body["skills"][0]["name"] == "cite-sources"


def test_error_event_when_every_route_fails(deps_factory):
    from my_agent_crew.llm.provider import ProviderError

    deps = deps_factory(script=[ProviderError("down")])
    with TestClient(create_app(deps), base_url="http://127.0.0.1") as c:
        conv = c.post("/api/conversations", json={}).json()
        with c.stream(
            "POST", f"/api/conversations/{conv['id']}/messages", json={"text": "hi"}
        ) as r:
            events = parse_sse("".join(r.iter_text()))
    assert events[-1]["type"] == "error" and "down" in events[-1]["message"]


def test_scripted_tool_round_trip_over_http(deps_factory):
    deps = deps_factory(
        script=[completion(tool_calls=(ToolCall("c1", "workspace_list", {}),)), completion("ok")]
    )
    with TestClient(create_app(deps), base_url="http://127.0.0.1") as c:
        conv = c.post("/api/conversations", json={}).json()
        with c.stream(
            "POST", f"/api/conversations/{conv['id']}/messages", json={"text": "ls"}
        ) as r:
            events = parse_sse("".join(r.iter_text()))
    kinds = [e["type"] for e in events if e["type"] != "text_delta"]
    assert kinds == ["assistant_message", "tool_call", "tool_result", "assistant_message", "done"]


def test_a_new_conversation_recaps_the_web_one_it_replaces(client):
    first = client.post("/api/conversations", json={}).json()
    with client.stream(
        "POST", f"/api/conversations/{first['id']}/messages", json={"text": "nhắc tôi chạy bộ"}
    ) as r:
        r.read()

    client.post("/api/conversations", json={}).json()

    assert client.get(f"/api/conversations/{first['id']}").json()["summary"] != ""


def test_resummarizing_rewrites_the_recap_and_404s_for_an_unknown_conversation(client):
    conv = client.post("/api/conversations", json={}).json()
    with client.stream(
        "POST", f"/api/conversations/{conv['id']}/messages", json={"text": "xin chào"}
    ) as r:
        r.read()

    r = client.post(f"/api/conversations/{conv['id']}/summary")

    assert r.status_code == 202
    body = r.json()
    assert body["id"] == conv["id"] and body["summary"] != ""
    assert client.get(f"/api/conversations/{conv['id']}").json()["summary"] == body["summary"]
    assert client.post("/api/conversations/nope/summary").status_code == 404


def test_a_new_conversation_is_named_from_the_first_thing_the_person_says(client):
    conv = client.post("/api/conversations", json={}).json()
    assert conv["title"] == CONVERSATION_TITLE_DEFAULT

    with client.stream(
        "POST",
        f"/api/conversations/{conv['id']}/messages",
        json={"text": "Giúp tôi lập kế hoạch ôn thi. Còn ba tháng nữa."},
    ) as r:
        r.read()

    assert client.get(f"/api/conversations/{conv['id']}").json()["title"] == (
        "Giúp tôi lập kế hoạch ôn thi"
    )


def test_a_conversation_the_person_named_keeps_that_name_when_they_write(client):
    conv = client.post("/api/conversations", json={"title": "Sổ tay của tôi"}).json()

    with client.stream(
        "POST", f"/api/conversations/{conv['id']}/messages", json={"text": "xin chào"}
    ) as r:
        r.read()

    assert client.get(f"/api/conversations/{conv['id']}").json()["title"] == "Sổ tay của tôi"
