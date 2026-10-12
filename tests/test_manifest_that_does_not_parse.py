"""An `agent.yaml` that does not parse is refused by name wherever the crew is read again.

The start reads the file with one library, and the routes caught the error of the other. So
a parse error went past every one of them as a traceback: a reload, an install, a save of the
routes. It is a ValueError now, like a profile of the wrong shape, and it names the file,
which the reader's own error does not."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew import texts
from my_agent_crew.agents import load_profiles
from my_agent_crew.config import load_settings
from my_agent_crew.server import build_runtime, create_app
from my_agent_crew.server.credential_catalog import KNOWN

BROKEN = "name: [unclosed\n"
CONFIG = "# my crew\nroutes:\n  - fake:echo\n"


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
    (home / "config.yaml").write_text(CONFIG, encoding="utf-8")
    return home


def settings_of(home: Path):
    return load_settings(env={"MY_AGENT_HOME": str(home)})


def serve(home: Path):
    runtime = build_runtime(settings_of(home))
    return runtime, TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1")


def odd_file(home: Path) -> Path:
    folder = home / "agents" / "odd"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "agent.yaml"


@pytest.mark.parametrize("where", ["agent.yaml", "agents/odd/agent.yaml"])
def test_the_reader_says_which_file_does_not_parse(home, where):
    manifest = home / where
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(BROKEN, encoding="utf-8")

    with pytest.raises(ValueError) as refused:
        load_profiles(settings_of(home))

    said = str(refused.value)
    assert said.startswith(texts.MANIFEST_BROKEN.format(error=""))
    assert str(manifest) in said
    # What the reader itself says is kept: the line, the column, what it expected.
    assert "line 1" in said


def test_a_reload_refuses_a_folder_whose_file_does_not_parse_by_name(home):
    runtime, served = serve(home)
    with served as client:
        odd_file(home).write_text(BROKEN, encoding="utf-8")

        refused = client.post("/api/agents/reload")

        assert refused.status_code == 422, refused.text
        assert str(odd_file(home)) in refused.json()["detail"]
        assert sorted(runtime.agents) == ["default"]

        odd_file(home).write_text("name: Odd\n", encoding="utf-8")
        assert client.post("/api/agents/reload").json() == {"added": ["odd"]}


def test_the_routes_are_not_saved_beside_a_file_that_does_not_parse(home):
    """The crew is rebuilt from the home before the routes are written, and it cannot be."""
    runtime, served = serve(home)
    routes = runtime.settings.routes
    with served as client:
        odd_file(home).write_text(BROKEN, encoding="utf-8")
        body = {"routes": [{"provider": "fake", "model": "second"}]}

        refused = client.put("/api/connections/routes", json=body)

    assert refused.status_code == 409, refused.text
    assert str(odd_file(home)) in refused.json()["detail"]
    assert (home / "config.yaml").read_text(encoding="utf-8") == CONFIG
    assert runtime.settings.routes == routes
