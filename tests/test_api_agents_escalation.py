"""Setting an agent's escalation route from the editor: saved the way a person writes it,
cleared with a null, and refused before it is written when it is no way out
(`server/routes_agents_edit.py`)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew import texts
from my_agent_crew.config import load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime_build import build_runtime

BIG = {"provider": "fake", "model": "big"}


@pytest.fixture
def crew(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, runtime, home


def manifest(home: Path, agent_id: str = "coder") -> str:
    return (home / "agents" / agent_id / "agent.yaml").read_text(encoding="utf-8")


def test_the_editor_sets_and_clears_an_agents_escalation_route(crew) -> None:
    client, runtime, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    assert client.get("/api/agents/coder").json()["escalation_route"] is None
    assert runtime.deps_for("coder").escalation is None

    reply = client.patch("/api/agents/coder", json={"profile": {"escalation_route": BIG}})

    assert reply.status_code == 200
    assert reply.json()["profile"]["escalation_route"] == BIG
    assert client.get("/api/agents/coder").json()["escalation_route"] == BIG
    assert "escalation_route: fake:big\n" in manifest(home)
    chain = runtime.deps_for("coder").escalation
    assert chain is not None and [(r.provider, r.model) for r in chain.routes] == [("fake", "big")]

    reply = client.patch("/api/agents/coder", json={"profile": {"escalation_route": None}})

    assert reply.status_code == 200 and reply.json()["profile"]["escalation_route"] is None
    assert "escalation_route" not in manifest(home)
    assert runtime.deps_for("coder").escalation is None


def test_a_new_agent_may_be_made_with_an_escalation_route(crew) -> None:
    client, runtime, home = crew

    reply = client.post(
        "/api/agents", json={"agent_id": "coder", "profile": {"escalation_route": "fake:big"}}
    )

    assert reply.status_code == 201 and reply.json()["profile"]["escalation_route"] == BIG
    assert runtime.deps_for("coder").escalation is not None


@pytest.mark.parametrize(
    ("patch", "problem", "route"),
    [
        ({"escalation_route": {"provider": "fake", "model": "echo"}}, "SAME", "fake:echo"),
        ({"escalation_route": "openrouter:big"}, "UNUSABLE", "openrouter:big"),
    ],
    ids=["the route the agent is on", "a provider with no key"],
)
def test_an_escalation_route_that_is_no_way_out_is_refused_before_it_is_written(
    crew, patch, problem, route
) -> None:
    client, runtime, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})

    reply = client.patch("/api/agents/coder", json={"profile": patch})

    wanted = getattr(texts, f"ESCALATION_ROUTE_{problem}").format(route=route)
    assert reply.status_code == 422 and reply.json()["detail"] == wanted
    assert "escalation_route" not in manifest(home)
    assert runtime.deps_for("coder").escalation is None


def test_moving_the_agent_onto_its_own_escalation_route_is_refused(crew) -> None:
    client, runtime, home = crew
    client.post(
        "/api/agents", json={"agent_id": "coder", "profile": {"escalation_route": "fake:big"}}
    )

    reply = client.patch("/api/agents/coder", json={"profile": {"routes": ["fake:big"]}})

    assert reply.status_code == 422
    assert reply.json()["detail"] == texts.ESCALATION_ROUTE_SAME.format(route="fake:big")
    assert "routes" not in manifest(home)
    assert [r.model for r in runtime.deps_for("coder").chain.routes] == ["echo"]
    assert runtime.deps_for("coder").escalation is not None


def test_a_new_agent_named_with_a_route_that_is_no_way_out_is_not_made(crew) -> None:
    client, runtime, home = crew

    reply = client.post(
        "/api/agents", json={"agent_id": "coder", "profile": {"escalation_route": "fake:echo"}}
    )

    assert reply.status_code == 422
    assert reply.json()["detail"] == texts.ESCALATION_ROUTE_SAME.format(route="fake:echo")
    assert not (home / "agents" / "coder" / "agent.yaml").exists()
    assert "coder" not in {profile.id for profile in runtime.profiles()}
    # Nothing of the refused agent is in the way of making it with a route that is one.
    again = client.post(
        "/api/agents", json={"agent_id": "coder", "profile": {"escalation_route": "fake:big"}}
    )
    assert again.status_code == 201


@pytest.mark.parametrize(
    "route", [{"provider": "fake"}, {"provider": "fake", "model": 3}, ["fake:big"], 7, "big"]
)
def test_an_escalation_route_of_another_shape_is_refused(crew, route) -> None:
    client, _, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})

    reply = client.patch("/api/agents/coder", json={"profile": {"escalation_route": route}})

    assert reply.status_code == 422 and "provider:model" in reply.json()["detail"]
    assert "escalation_route" not in manifest(home)


def test_a_file_written_by_hand_with_such_a_route_does_not_block_another_edit(crew) -> None:
    """A person may write the file for a machine with another key. What the editor did not
    touch is not held against the edit: the route stays in the file, unused."""
    client, runtime, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {"name": "Thợ mã"}})
    path = home / "agents" / "coder" / "agent.yaml"
    path.write_text("name: Thợ mã\nescalation_route: openrouter:big\n", encoding="utf-8")

    reply = client.patch("/api/agents/coder", json={"profile": {"description": "dọn mã"}})

    assert reply.status_code == 200
    assert "escalation_route: openrouter:big\n" in manifest(home)
    assert runtime.deps_for("coder").agent.description == "dọn mã"
    assert runtime.deps_for("coder").escalation is None
