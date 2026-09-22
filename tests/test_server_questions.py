"""The HTTP side of a question: it pauses like an approval and resumes like one, but it
is closed on its own route and the two routes refuse each other's rows."""

import json

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import Route
from my_agent_crew.server import create_app

ASK = '/tool ask_user {"question": "Dời hạn sang thứ sáu?", "options": ["có", "không"]}'
WRITE = '/tool workspace_write {"path": "x.txt", "content": "1"}'


@pytest.fixture
def client(deps_factory):
    deps = deps_factory(routes=(Route("fake", "echo"),))
    with TestClient(create_app(deps)) as c:
        yield c


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        data = [line[5:].strip() for line in block.splitlines() if line.startswith("data:")]
        if data:
            events.append(json.loads("".join(data)))
    return events


def turn(client, base: str, text: str) -> list[dict]:
    with client.stream("POST", f"{base}/messages", json={"text": text}) as r:
        return parse_sse("".join(r.iter_text()))


def test_a_question_pauses_and_the_answer_resumes_the_turn(client):
    conv = client.post("/api/conversations", json={}).json()
    base = f"/api/conversations/{conv['id']}"

    paused = turn(client, base, ASK)[-1]
    assert paused["type"] == "approval_required"
    assert paused["kind"] == "question" and paused["options"] == ["có", "không"]

    detail = client.get(base).json()
    assert detail["pending_approval"]["kind"] == "question"
    assert detail["status"] == "awaiting_approval"

    url = f"{base}/approvals/{paused['approval_id']}/answer"
    with client.stream("POST", url, json={"answer": "có, dời sang thứ sáu"}) as r:
        resumed = parse_sse("".join(r.iter_text()))
    assert [e["type"] for e in resumed][:2] == ["tool_call", "tool_result"]
    assert "dời sang thứ sáu" in resumed[1]["output"]
    assert resumed[-1]["type"] == "done"

    history = client.get("/api/approvals").json()
    assert history[0]["status"] == "answered"
    assert history[0]["answer"] == "có, dời sang thứ sáu"


def test_answering_twice_is_refused(client):
    conv = client.post("/api/conversations", json={}).json()
    base = f"/api/conversations/{conv['id']}"
    paused = turn(client, base, ASK)[-1]
    url = f"{base}/approvals/{paused['approval_id']}/answer"
    with client.stream("POST", url, json={"answer": "có"}) as r:
        r.read()
    assert client.post(url, json={"answer": "không"}).status_code == 409


def test_an_empty_answer_is_rejected_rather_than_sent_on(client):
    """An empty answer is the one reply that teaches the agent nothing, and it would
    close the question for good. Better to leave it open."""
    conv = client.post("/api/conversations", json={}).json()
    base = f"/api/conversations/{conv['id']}"
    paused = turn(client, base, ASK)[-1]
    url = f"{base}/approvals/{paused['approval_id']}/answer"
    assert client.post(url, json={"answer": "   "}).status_code == 422
    assert client.get(base).json()["pending_approval"]["id"] == paused["approval_id"]


def test_the_two_routes_refuse_each_others_rows(client):
    conv = client.post("/api/conversations", json={}).json()
    base = f"/api/conversations/{conv['id']}"

    question = turn(client, base, ASK)[-1]["approval_id"]
    decide = client.post(f"{base}/approvals/{question}", json={"approve": True})
    assert decide.status_code == 409

    # Close the question so the conversation is free, then try the mirror case.
    with client.stream("POST", f"{base}/approvals/{question}/answer", json={"answer": "có"}) as r:
        r.read()

    tool = turn(client, base, WRITE)[-1]["approval_id"]
    answered = client.post(f"{base}/approvals/{tool}/answer", json={"answer": "ừ chạy đi"})
    assert answered.status_code == 409
