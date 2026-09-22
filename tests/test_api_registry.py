import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime_build import build_runtime

FAKE_KEY = "sk-khong-duoc-lo-ra-12345"


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
    with TestClient(create_app(runtime, schedule=False)) as client:
        yield client, runtime, home


def test_the_tool_list_says_which_agents_hold_each_tool(crew) -> None:
    client, _, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {"tools": ["workspace_read"]}})

    tools = {t["name"]: t for t in client.get("/api/tools").json()}

    assert tools["workspace_read"]["agents"] == ["coder", "default"]
    # A profile that names its tools caps them, so the specialist holds only that one.
    assert tools["shell_run"]["agents"] == ["default"]


def test_a_tool_only_one_agent_holds_still_appears(crew) -> None:
    client, _, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {"tools": ["workspace_read"]}})

    names = [t["name"] for t in client.get("/api/tools").json()]

    # Read from the union of every agent's registry, not the master's alone.
    assert "delegate" in names
    assert names == sorted(names)


def test_connections_report_a_key_as_present_without_showing_it(crew) -> None:
    client, _, _ = crew

    reply = client.get("/api/connections")
    body = reply.json()

    keys = {k["name"]: k["present"] for k in body["keys"]}
    assert keys["OPENROUTER_API_KEY"] is True
    assert keys["BRAVE_API_KEY"] is False
    assert body["routes"] == [{"provider": "fake", "model": "echo"}]
    # The whole response, not only the keys section: a secret must not reach the browser
    # by any field, and this is the assertion that keeps that true as fields are added.
    assert FAKE_KEY not in json.dumps(body, ensure_ascii=False)


def test_an_agents_channel_is_listed_by_the_name_of_its_env_var(crew) -> None:
    client, _, _ = crew
    client.post(
        "/api/agents",
        json={
            "agent_id": "coder",
            "profile": {"telegram": {"token_env": "KHONG_HE_DAT", "chat_id": 42}},
        },
    )

    body = client.get("/api/connections").json()

    assert body["telegram"] == [
        {
            "agent_id": "coder",
            "token_env": "KHONG_HE_DAT",
            "configured": False,
            # Only the master's block builds a channel, so this one never runs.
            "ignored": True,
        }
    ]
    # This view is the one people screenshot and share, so it stays down to what tells a
    # missing key from a wrong one. The agent's own editor does return chat_id, because
    # a field nobody can see is a field nobody can edit.
    assert "42" not in json.dumps(body)
    assert FAKE_KEY not in json.dumps(body)


def test_a_channel_whose_token_is_set_reads_as_configured(crew, monkeypatch) -> None:
    client, _, _ = crew
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_KEY)
    client.patch(
        "/api/agents/default",
        json={"profile": {"telegram": {"token_env": "TELEGRAM_BOT_TOKEN", "chat_id": 42}}},
    )

    body = client.get("/api/connections").json()

    # Each row reports its own env var. Reporting whether the crew has any channel at all
    # would mark an agent configured whose token was never set.
    assert body["telegram"] == [
        {
            "agent_id": "default",
            "token_env": "TELEGRAM_BOT_TOKEN",
            "configured": True,
            "ignored": False,
        }
    ]
    assert FAKE_KEY not in json.dumps(body)
    assert "42" not in json.dumps(body)
