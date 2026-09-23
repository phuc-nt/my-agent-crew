"""HTTP surface for agents, activity, stats and jobs on a two-agent runtime."""

import json
import time
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import load_settings
from my_agent_crew.server import build_runtime, create_app
from tests.test_server_api import parse_sse

MANIFEST = """
name: Coach
routes: [fake:echo]
autonomous: true
schedules:
  - id: brief
    name: Bản tin
    cron: '0 7 * * *'
    prompt: '/tool shell_run {"command": "echo brief"}'
  - id: sync
    every: 1h
    command: echo synced
"""


@pytest.fixture
def two_agents(tmp_path: Path):
    coach = tmp_path / "agents" / "coach"
    coach.mkdir(parents=True)
    (coach / "agent.yaml").write_text(MANIFEST)
    env = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, runtime


def test_agents_endpoint_lists_profiles_with_tools_and_skills(two_agents):
    client, _ = two_agents
    agents = client.get("/api/agents").json()
    assert [a["id"] for a in agents] == ["default", "coach"]
    assert "shell_run" in agents[1]["tools"] and agents[1]["autonomous"] is True
    one = client.get("/api/agents/coach").json()
    assert one["name"] == "Coach" and one["tools"][0]["name"]
    assert client.get("/api/agents/nope").status_code == 404
    assert client.get("/api/settings").json()["agents"][1]["id"] == "coach"


def test_conversations_belong_to_an_agent(two_agents):
    client, runtime = two_agents
    created = client.post("/api/conversations", json={"agent_id": "coach"}).json()
    assert created["agent_id"] == "coach" and created["autonomous"] is True
    assert client.post("/api/conversations", json={"agent_id": "ghost"}).status_code == 404
    default = client.post("/api/conversations", json={}).json()
    assert default["agent_id"] == "default"
    assert [c["id"] for c in client.get("/api/conversations?agent_id=coach").json()] == [
        created["id"]
    ]
    assert len(client.get("/api/conversations").json()) == 2
    with client.stream(
        "POST",
        f"/api/conversations/{created['id']}/messages",
        json={"text": '/tool shell_run {"command": "pwd"}'},
    ) as r:
        events = parse_sse("".join(r.iter_text()))
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["output"].strip() == str(runtime.deps_for("coach").agent.workspace)


def test_runs_are_recorded_per_turn_and_summarised_in_stats(two_agents):
    client, _ = two_agents
    conv = client.post("/api/conversations", json={"agent_id": "coach"}).json()
    with client.stream(
        "POST", f"/api/conversations/{conv['id']}/messages", json={"text": "xin chào"}
    ) as r:
        r.read()
    runs = client.get("/api/activity/runs").json()
    assert len(runs) == 1 and runs[0]["agent_id"] == "coach" and runs[0]["status"] == "done"
    assert runs[0]["conversation_id"] == conv["id"] and runs[0]["source"] == "chat"
    assert client.get(f"/api/activity/runs/{runs[0]['id']}").json()["steps"]
    assert client.get("/api/activity/runs/none").status_code == 404
    assert client.get("/api/activity/runs?agent_id=default").json() == []
    stats = client.get("/api/stats").json()
    assert stats["runs"] == 1 and stats["by_agent"] == {"coach": 0.0}
    assert stats["model_calls"] >= 1 and "fake:echo" in stats["by_model"]
    # Runs are stamped in UTC; the day is the person's (here the machine's, no timezone set).
    started = datetime.fromisoformat(runs[0]["started_at"]).astimezone()
    assert list(stats["by_day"]) == [started.date().isoformat()]


def test_a_conversation_sees_its_own_runs_and_not_another_conversations(two_agents):
    client, _ = two_agents
    mine = client.post("/api/conversations", json={"agent_id": "coach"}).json()
    theirs = client.post("/api/conversations", json={"agent_id": "coach"}).json()
    for conv in (mine, theirs):
        with client.stream(
            "POST", f"/api/conversations/{conv['id']}/messages", json={"text": "xin chào"}
        ) as r:
            r.read()

    runs = client.get(f"/api/activity/runs?conversation_id={mine['id']}").json()

    assert [r["conversation_id"] for r in runs] == [mine["id"]]


def test_a_quiet_conversations_runs_are_not_crowded_out_by_a_busier_one(two_agents):
    """The limit must count the conversation's own runs, or a chat that ran once looks
    like it never ran at all once other chats fill the page."""
    client, _ = two_agents
    quiet = client.post("/api/conversations", json={"agent_id": "coach"}).json()
    busy = client.post("/api/conversations", json={"agent_id": "coach"}).json()
    for conv in (quiet, busy, busy, busy):
        with client.stream(
            "POST", f"/api/conversations/{conv['id']}/messages", json={"text": "xin chào"}
        ) as r:
            r.read()

    runs = client.get(f"/api/activity/runs?conversation_id={quiet['id']}&limit=2").json()

    assert [r["conversation_id"] for r in runs] == [quiet["id"]]


def test_what_a_conversation_delegated_counts_as_its_own_activity(two_agents):
    """The work runs on the child's run; without it the parent looks idle while a
    delegate is busy on its behalf."""
    client, runtime = two_agents
    parent = client.post("/api/conversations", json={"agent_id": "default"}).json()
    with client.stream(
        "POST",
        f"/api/conversations/{parent['id']}/messages",
        json={"text": '/tool delegate {"agent_id": "coach", "task": "xin chào"}'},
    ) as r:
        r.read()
    children = runtime.store.delegated_children(parent["id"], "delegate")
    assert children, "the delegate tool did not open a child conversation"

    runs = client.get(f"/api/activity/runs?conversation_id={parent['id']}").json()

    assert {r["conversation_id"] for r in runs} == {parent["id"], children[0].id}


async def test_activity_stream_sends_snapshot_then_run_events(tmp_path: Path):
    # The test client buffers whole responses, so the endless SSE body is read directly.
    from my_agent_crew.activity import tracked
    from my_agent_crew.agent.loop import run_turn
    from my_agent_crew.server.routes_activity import stream

    env = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    conv = runtime.store.create()
    body = (await stream(runtime)).body_iterator
    first = await body.__anext__()
    assert first["event"] == "snapshot" and json.loads(first["data"]) == {
        "type": "snapshot",
        "runs": [],
    }
    deps = runtime.deps_for("default")
    turn = tracked(runtime.hub, run_turn(deps, conv.id, "hi"), "default", "chat", "t", conv.id)
    async for _ in turn:
        pass
    second = await body.__anext__()
    assert second["event"] == "run"
    assert json.loads(second["data"])["run"]["conversation_id"] == conv.id
    runtime.hub.close()
    remaining = [chunk["event"] async for chunk in body]
    assert remaining[-1] == "run" and "event" in remaining


def test_jobs_are_listed_and_can_run_now(two_agents):
    client, runtime = two_agents
    jobs = client.get("/api/jobs").json()
    assert [j["id"] for j in jobs] == ["coach/brief", "coach/sync"]
    assert jobs[0]["next_run"] and jobs[0]["last_run"] is None and jobs[1]["every"] == "1h"
    assert client.post("/api/jobs/coach/nope/run").status_code == 404
    assert client.post("/api/jobs/coach/sync/run").status_code == 202
    assert client.post("/api/jobs/coach/brief/run").json() == {
        "job_id": "coach/brief",
        "status": "started",
    }
    deadline = time.monotonic() + 10
    while True:
        runs = client.get("/api/activity/runs").json()
        if len(runs) == 2 and all(r["status"] == "done" for r in runs):
            break
        assert time.monotonic() < deadline, runs
        time.sleep(0.05)
    assert {r["source"] for r in runs} == {"job:coach/sync", "job:coach/brief"}
    assert runtime.store.list("coach")[0].title.startswith("[lịch] Bản tin")
    assert client.get("/api/jobs").json()[1]["last_run"]["source"] == "job:coach/sync"


def test_a_job_can_be_paused_over_http_and_lists_its_own_runs(two_agents):
    client, runtime = two_agents
    far = datetime(2030, 1, 1, tzinfo=runtime.settings.zone)  # the scheduler's clock is aware
    assert client.patch("/api/jobs/coach/nope/state", json={"enabled": False}).status_code == 404
    paused = client.patch("/api/jobs/coach/sync/state", json={"enabled": False}).json()
    assert paused["id"] == "coach/sync" and paused["enabled"] is False and paused["paused"]
    assert [j.id for j in runtime.scheduler.due(far)] == ["coach/brief"]
    assert client.get("/api/jobs").json()[0]["paused"] is False

    assert client.get("/api/jobs/coach/sync/runs").json() == []
    assert client.post("/api/jobs/coach/sync/run").status_code == 202  # run-now ignores the pause
    deadline = time.monotonic() + 10
    while (
        not (runs := client.get("/api/jobs/coach/sync/runs").json()) or runs[0]["status"] != "done"
    ):
        assert time.monotonic() < deadline
        time.sleep(0.05)
    assert [r["source"] for r in runs] == ["job:coach/sync"]
    assert client.get("/api/jobs/coach/brief/runs").json() == []

    back = client.patch("/api/jobs/coach/sync/state", json={"enabled": True}).json()
    assert back["enabled"] is True and back["paused"] is False
    assert [j.id for j in runtime.scheduler.due(far)] == ["coach/brief", "coach/sync"]


def test_stats_carry_the_message_ledger_with_tokens(two_agents):
    client, _ = two_agents
    conv = client.post("/api/conversations", json={"agent_id": "coach"}).json()
    with client.stream(
        "POST", f"/api/conversations/{conv['id']}/messages", json={"text": "xin chào"}
    ) as r:
        r.read()
    stats = client.get("/api/stats").json()
    assert len(stats["days"]) == 7 and stats["days"][-1]["calls"] == 1
    assert stats["days"][-1]["prompt_tokens"] > 0 and stats["days"][-1]["completion_tokens"] > 0
    assert stats["days"][0]["calls"] == 0
    (model,) = stats["models"]
    assert model["model"] == "fake:echo" and model["calls"] == 1


def test_agent_files_are_served_only_from_the_workspace(two_agents):
    client, runtime = two_agents
    workspace = runtime.deps_for("coach").agent.workspace
    (workspace / "charts").mkdir()
    (workspace / "charts" / "sleep.png").write_bytes(b"\x89PNG fake")
    r = client.get("/api/agents/coach/files", params={"path": "charts/sleep.png"})
    assert r.status_code == 200 and r.content == b"\x89PNG fake"
    absolute = str(workspace / "charts" / "sleep.png")
    assert client.get("/api/agents/coach/files", params={"path": absolute}).status_code == 200
    linked = workspace.parent / "linked-charts"
    linked.mkdir()
    (linked / "hr.png").write_bytes(b"linked")
    (workspace / "data").symlink_to(linked)
    r = client.get("/api/agents/coach/files", params={"path": "data/hr.png"})
    assert r.status_code == 200 and r.content == b"linked"
    assert (
        client.get("/api/agents/coach/files", params={"path": "../agent.yaml"}).status_code == 403
    )
    assert client.get("/api/agents/coach/files", params={"path": "/etc/hosts"}).status_code == 403
    assert client.get("/api/agents/coach/files", params={"path": "missing.png"}).status_code == 404
