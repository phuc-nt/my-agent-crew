"""What an agent's file declares, versus what the crew computed from it.

An editor round-trips a profile: it reads what GET reports and sends back what changed.
That only works while the two agree. Where the crew fills something in — the master that
reaches every agent because it names none, the consolidation job generated from a cron
key — reading the computed value and writing it back turns a rule into a fixed list.
These tests pin the seam, because each failure here is silent: the save succeeds and the
damage shows up later, when a new agent turns out to be unreachable or a job runs twice.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime_build import build_runtime


@pytest.fixture
def crew(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, runtime, home


def test_a_profile_can_be_sent_back_exactly_as_it_was_read(crew) -> None:
    """The round-trip an editor performs when the person changes one unrelated field."""
    client, _, _ = crew
    client.post(
        "/api/agents",
        json={
            "agent_id": "coder",
            "profile": {
                "name": "Thợ mã",
                "schedules": [{"id": "nightly", "cron": "0 2 * * *", "prompt": "dọn kho"}],
            },
        },
    )
    described = client.get("/api/agents/coder").json()

    reply = client.patch(
        "/api/agents/coder",
        json={"profile": {"schedules": described["declared"]["schedules"], "name": "Thợ mã 2"}},
    )

    assert reply.status_code == 200, reply.json()
    assert reply.json()["profile"]["name"] == "Thợ mã 2"


def test_the_masters_reachable_crew_is_not_what_its_file_declares(crew) -> None:
    client, _, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})

    described = client.get("/api/agents/default").json()

    # It reaches the coder by the rule "names nobody, so reaches everyone". Saving that
    # reachable list back would replace the rule with today's answer, and every agent
    # added afterwards would be invisible to it.
    assert described["delegates"] == ["coder"]
    assert described["declared"]["delegates"] == []


def test_a_patch_that_keeps_the_declared_delegates_still_reaches_a_later_agent(crew) -> None:
    client, _, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    declared = client.get("/api/agents/default").json()["declared"]

    client.patch("/api/agents/default", json={"profile": {"delegates": declared["delegates"]}})
    client.post("/api/agents", json={"agent_id": "writer", "profile": {}})

    assert client.get("/api/agents/default").json()["delegates"] == ["coder", "writer"]


def listed(client: TestClient, agent_id: str) -> dict:
    return next(row for row in client.get("/api/agents").json() if row["id"] == agent_id)


def test_the_tools_an_agent_holds_are_not_what_its_file_lists(crew) -> None:
    client, _, _ = crew
    client.post(
        "/api/agents", json={"agent_id": "reader", "profile": {"tools": ["workspace_read"]}}
    )

    open_handed, capped = listed(client, "default"), listed(client, "reader")

    # The master lists nothing and holds everything. Saving what it holds back would cap
    # it at today's toolbox, and name tools no list gives.
    assert open_handed["declared"]["tools"] == []
    assert {"workspace_read", "shell_run", "delegate", "tool_script"} <= set(open_handed["tools"])
    # The script tool follows what an agent may read, not its list: held, never declared.
    assert capped["declared"]["tools"] == ["workspace_read"]
    assert capped["tools"] == ["workspace_read", "tool_script"]
    assert client.get("/api/agents/reader").json()["declared"]["tools"] == ["workspace_read"]


def test_a_save_answers_with_the_tools_the_file_now_lists(crew) -> None:
    client, _, _ = crew
    client.post("/api/agents", json={"agent_id": "reader", "profile": {}})

    reply = client.patch("/api/agents/reader", json={"profile": {"tools": ["workspace_read"]}})

    # The editor rebuilds its form from this answer, so it has to carry the same list.
    assert reply.json()["profile"]["declared"]["tools"] == ["workspace_read"]
    assert listed(client, "reader")["declared"]["tools"] == ["workspace_read"]


def test_a_patch_that_keeps_the_declared_tools_leaves_the_agent_open_handed(crew) -> None:
    client, _, _ = crew
    before = listed(client, "default")

    client.patch("/api/agents/default", json={"profile": {"tools": before["declared"]["tools"]}})

    after = listed(client, "default")
    assert after["declared"]["tools"] == []
    assert after["tools"] == before["tools"]


def test_the_consolidation_job_is_reported_to_run_but_never_offered_to_edit(crew) -> None:
    client, _, _ = crew
    client.post(
        "/api/agents",
        json={"agent_id": "coder", "profile": {"memory_consolidate": "0 3 * * 2"}},
    )

    described = client.get("/api/agents/coder").json()

    # It is a real job, so the schedule list shows it; it is generated from a cron key
    # rather than written out, so an editor that saved it back would create a second one
    # on the same cron alongside the key that made it.
    assert [s["kind"] for s in described["schedules"]] == ["consolidate"]
    assert described["declared"]["schedules"] == []


def test_a_telegram_channel_without_a_token_name_is_refused(crew) -> None:
    client, _, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})

    reply = client.patch(
        "/api/agents/coder",
        json={"profile": {"telegram": {"token_env": "", "chat_id": 0}}},
    )

    # Accepting it stores a bot that can never start and says so nowhere: the channel
    # just stays silent. The form is the last place the person can still fix it.
    assert reply.status_code == 422
    assert "token_env" in reply.json()["detail"]
