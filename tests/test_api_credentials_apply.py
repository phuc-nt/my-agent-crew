"""How a saved or removed key reaches the running crew: tried first, refused when the
crew could not run with it, and swapped in without disturbing what is already running."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import load_settings
from my_agent_crew.env_file import read_env
from my_agent_crew.server import runtime_connections
from my_agent_crew.server.app import create_app
from my_agent_crew.server.credential_catalog import KNOWN
from my_agent_crew.server.runtime_build import build_runtime

SECRET = "sk-or-v1-apply-secret"


@pytest.fixture
def environ():
    saved = dict(os.environ)
    for known in KNOWN:
        os.environ.pop(known.name, None)
    os.environ.pop("CREW_BOT_TOKEN", None)
    yield os.environ
    os.environ.clear()
    os.environ.update(saved)


def _crew(home: Path, routes: str, **env: str):
    home.mkdir(exist_ok=True)
    settings = load_settings(env={"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": routes, **env})
    runtime = build_runtime(settings)
    return TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1"), runtime


def test_removing_the_key_the_only_route_needs_is_refused_and_nothing_changes(
    tmp_path: Path, environ
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "env").write_text(f"OPENROUTER_API_KEY='{SECRET}'\n")
    environ["OPENROUTER_API_KEY"] = SECRET
    client, runtime = _crew(home, "openrouter:some/model", OPENROUTER_API_KEY=SECRET)
    with client:
        reply = client.delete("/api/credentials/OPENROUTER_API_KEY")

    assert reply.status_code == 409
    assert SECRET not in reply.text
    # Says which route needs the key, readably, and what to do first.
    detail = reply.json()["detail"]
    assert "openrouter:some/model" in detail and "Route(" not in detail
    assert "Đổi tuyến" in detail
    assert read_env(home / "env") == {"OPENROUTER_API_KEY": SECRET}
    assert environ["OPENROUTER_API_KEY"] == SECRET
    assert "openrouter" in runtime.providers
    assert "openrouter" in runtime.default.chain.providers


def test_a_turn_already_running_keeps_the_providers_it_started_with(
    tmp_path: Path, environ
) -> None:
    client, runtime = _crew(tmp_path / "home", "fake:echo")
    with client:
        client.put("/api/credentials/OPENROUTER_API_KEY", json={"value": SECRET})
        running = runtime.default.chain
        before = dict(running.providers)

        reply = client.delete("/api/credentials/OPENROUTER_API_KEY")

    assert reply.status_code == 200
    assert "openrouter" not in runtime.providers
    # The chain a turn holds still has every provider it was built with.
    assert dict(running.providers) == before and "openrouter" in running.providers


def test_the_bot_is_rebuilt_only_when_its_token_or_chat_changes(tmp_path: Path, environ) -> None:
    client, runtime = _crew(tmp_path / "home", "fake:echo")
    with client:
        client.patch(
            "/api/agents/default",
            json={"profile": {"telegram": {"token_env": "CREW_BOT_TOKEN", "chat_id": 7}}},
        )
        assert runtime.channel is None  # no token yet
        client.put("/api/credentials/CREW_BOT_TOKEN", json={"value": "123:first"})
        first = runtime.channel
        assert first is not None

        client.put("/api/credentials/BRAVE_API_KEY", json={"value": "brave"})
        client.patch("/api/agents/default", json={"profile": {"name": "Thư ký"}})
        kept = runtime.channel
        client.put("/api/credentials/CREW_BOT_TOKEN", json={"value": "123:second"})
        after_token = runtime.channel
        client.patch(
            "/api/agents/default",
            json={"profile": {"telegram": {"token_env": "CREW_BOT_TOKEN", "chat_id": 8}}},
        )
        after_chat = runtime.channel

    assert kept is first
    # The running bot answers with the rebuilt agents: the new key and the new name.
    assert kept.deps.agent.name == "Thư ký"
    assert after_token is not first and after_token is not None
    assert after_chat is not after_token and after_chat is not None
    assert after_chat.chat_id == 8


def test_a_host_with_a_password_in_it_is_shown_without_the_password(
    tmp_path: Path, environ
) -> None:
    client, _ = _crew(tmp_path / "home", "fake:echo")
    with client:
        reply = client.put(
            "/api/credentials/FIRECRAWL_BASE_URL",
            json={"value": "http://crawler:hunter2@10.0.0.5:3002"},
        )

    item = next(i for i in reply.json()["items"] if i["name"] == "FIRECRAWL_BASE_URL")
    assert item["value"] == "http://…@10.0.0.5:3002"
    assert "hunter2" not in reply.text


def test_a_password_in_an_ipv6_host_is_masked_and_the_brackets_kept() -> None:
    from my_agent_crew.server.credential_catalog import shown_url

    assert shown_url("http://u:p@[::1]:11434/v1") == "http://…@[::1]:11434/v1"
    assert shown_url("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434/v1"


def test_a_name_the_routes_refuse_is_listed_without_controls(tmp_path: Path, environ) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "env").write_text("lower_case=x\nMY_AGENT_ROUTES=fake:echo\nGOOD_NAME=y\n")
    client, _ = _crew(home, "fake:echo")
    with client:
        items = {i["name"]: i for i in client.get("/api/credentials").json()["items"]}

    assert items["lower_case"]["editable"] is False
    assert items["MY_AGENT_ROUTES"]["editable"] is False
    assert items["GOOD_NAME"]["editable"] is True


async def test_a_bot_that_fails_to_rebuild_leaves_the_crew_still_polling(
    tmp_path: Path, environ, monkeypatch
) -> None:
    _, runtime = _crew(tmp_path / "home", "fake:echo")

    class Bot:
        def __init__(self) -> None:
            self.running = True

        async def stop(self) -> None:
            self.running = False

        def start(self) -> None:
            self.running = True

    old = Bot()
    runtime.channel, runtime.channel_live = old, True

    def broken(*args, **kwargs):
        raise RuntimeError("bad profile")

    monkeypatch.setattr(runtime_connections, "build_channel", broken)
    with pytest.raises(RuntimeError):
        await runtime_connections.restart_channel(runtime)

    # The old bot was stopped before the rebuild; the crew still means to poll, and does
    # with whichever bot it has.
    assert runtime.channel_live is True
    assert runtime.channel is old and old.running
