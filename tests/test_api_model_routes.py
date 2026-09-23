"""Changing the routes every agent falls back on from the web: tried first, written to
`config.yaml` without disturbing what else the file holds, and read-only while the
environment variable decides them."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import load_settings
from my_agent_crew.config_parse import Route
from my_agent_crew.server.app import create_app
from my_agent_crew.server.credential_catalog import KNOWN
from my_agent_crew.server.runtime_build import build_runtime

HAND_WRITTEN = "# my crew\nlanguage: vi  # keep Vietnamese\nroutes:\n  - fake:echo\n"


@pytest.fixture
def environ():
    saved = dict(os.environ)
    for name in [known.name for known in KNOWN] + ["MY_AGENT_ROUTES"]:
        os.environ.pop(name, None)
    yield os.environ
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture
def home(tmp_path: Path, environ) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.yaml").write_text(HAND_WRITTEN)
    return home


def _crew(home: Path, **env: str):
    runtime = build_runtime(load_settings(env={"MY_AGENT_HOME": str(home), **env}))
    return TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1"), runtime


def test_saved_routes_reach_the_crew_and_keep_the_file_as_typed(home: Path) -> None:
    client, runtime = _crew(home)
    with client:
        assert client.get("/api/connections").json()["routes_source"] == "config"
        reply = client.put(
            "/api/connections/routes",
            json={
                "routes": [
                    {"provider": "fake", "model": "second"},
                    {"provider": "ollama", "model": "qwen3:8b"},
                ]
            },
        )

    assert reply.status_code == 200, reply.text
    assert reply.json()["routes"] == [
        {"provider": "fake", "model": "second"},
        {"provider": "ollama", "model": "qwen3:8b"},
    ]
    assert reply.json()["restart_required"] is None
    text = (home / "config.yaml").read_text()
    assert "# my crew" in text and "# keep Vietnamese" in text
    assert "- fake:second" in text and "- ollama:qwen3:8b" in text
    assert runtime.settings.routes == (Route("fake", "second"), Route("ollama", "qwen3:8b"))
    # An agent with no routes of its own answers with the new ones from the next turn.
    assert runtime.default.chain.routes[0] == Route("fake", "second")
    assert load_settings(env={"MY_AGENT_HOME": str(home)}).routes == runtime.settings.routes


def test_a_provider_with_no_key_is_refused_and_nothing_is_written(home: Path) -> None:
    client, runtime = _crew(home)
    with client:
        reply = client.put(
            "/api/connections/routes",
            json={"routes": [{"provider": "openrouter", "model": "some/model"}]},
        )

    assert reply.status_code == 409
    assert "openrouter" in reply.json()["detail"]
    assert (home / "config.yaml").read_text() == HAND_WRITTEN
    assert runtime.settings.routes == (Route("fake", "echo"),)


def test_routes_set_by_the_variable_are_not_saved_over(home: Path, environ) -> None:
    environ["MY_AGENT_ROUTES"] = "fake:echo"
    client, _ = _crew(home)
    with client:
        source = client.get("/api/connections").json()["routes_source"]
        reply = client.put(
            "/api/connections/routes", json={"routes": [{"provider": "fake", "model": "x"}]}
        )

    assert source == "env"
    assert reply.status_code == 409 and "MY_AGENT_ROUTES" in reply.json()["detail"]
    assert (home / "config.yaml").read_text() == HAND_WRITTEN


@pytest.mark.parametrize(
    "routes",
    [
        [],
        [{"provider": "Open Router", "model": "x"}],
        [{"provider": "fake", "model": "two words"}],
        [{"provider": "fake", "model": "a,b"}],
        [{"provider": "fake", "model": f"m{i}"} for i in range(11)],
    ],
)
def test_a_malformed_list_is_refused_before_anything_is_tried(home: Path, routes) -> None:
    client, _ = _crew(home)
    with client:
        reply = client.put("/api/connections/routes", json={"routes": routes})

    assert reply.status_code == 422
    assert (home / "config.yaml").read_text() == HAND_WRITTEN


def test_a_home_with_no_config_file_gets_one_with_just_the_routes(tmp_path: Path, environ) -> None:
    home = tmp_path / "home"
    home.mkdir()
    # The default route is OpenRouter's, so a crew with no file runs on that key.
    environ["OPENROUTER_API_KEY"] = "sk-or-v1-test"
    client, _ = _crew(home, OPENROUTER_API_KEY="sk-or-v1-test")
    with client:
        assert client.get("/api/connections").json()["routes_source"] == "default"
        reply = client.put(
            "/api/connections/routes", json={"routes": [{"provider": "fake", "model": "echo"}]}
        )

    assert reply.status_code == 200
    assert load_settings(env={"MY_AGENT_HOME": str(home)}).routes == (Route("fake", "echo"),)
