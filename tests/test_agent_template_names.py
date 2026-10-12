"""The two names an add takes both become a path segment: the template is one of the bundled
folders by its plain name, the id a folder under the home's `agents`. One with a path in it
read a template from elsewhere or wrote the agent outside the home. And a folder copied in
by hand joins a running crew with the others or not at all."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew import __main__ as entry
from my_agent_crew import texts
from my_agent_crew.agent_ids import is_agent_id
from my_agent_crew.agents.templates_cli import (
    SHARED_SKILLS,
    add_template,
    landing,
    list_templates,
)
from my_agent_crew.config import load_settings
from my_agent_crew.server import build_runtime, create_app

BUNDLED = sorted(t.id for t in list_templates())
NO_AGENT_ID = ["../../out", "a/b", "/abs", "Kong Ming", ".trash", "kong\n", "-x"]
NO_TEMPLATE = ["../templates/kongming", "kongming/", "./kongming", SHARED_SKILLS]


def everything(root: Path) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in root.rglob("*"))


def test_every_bundled_template_goes_by_an_agent_id():
    assert BUNDLED and all(is_agent_id(name) for name in BUNDLED)


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("agent_id", NO_AGENT_ID)
def test_an_id_no_agent_can_go_by_is_refused_and_nothing_is_written(tmp_path, agent_id, force):
    home = tmp_path / "home"
    home.mkdir()

    with pytest.raises(ValueError, match=texts.AGENT_ID_INVALID):
        add_template("kongming", home, agent_id, force)

    assert everything(tmp_path) == ["home"]


@pytest.mark.parametrize("force", [False, True])
def test_the_masters_id_is_not_one_a_template_can_take(tmp_path, force):
    """The master's file is the home's own: a folder by its id stops the next start."""
    home = tmp_path / "home"
    home.mkdir()

    with pytest.raises(ValueError, match=texts.AGENT_EXISTS.format(agent_id="default")):
        add_template("kongming", home, "default", force)

    assert everything(tmp_path) == ["home"]


@pytest.mark.parametrize("template", NO_TEMPLATE)
def test_a_template_name_with_a_path_in_it_is_no_template(tmp_path, template):
    home = tmp_path / "home"
    home.mkdir()

    with pytest.raises(KeyError):
        add_template(template, home, force=True)

    assert everything(tmp_path) == ["home"]


@pytest.mark.parametrize("template", BUNDLED)
def test_landing_lists_every_file_an_add_writes_outside_the_peers_it_brings(tmp_path, template):
    """The install puts back what stood at each of these when it is refused after the
    write, so a file an add writes and this leaves out would stay changed."""
    home = tmp_path / "home"

    _, peers = add_template(template, home, "mine")

    written = {path for path in home.rglob("*") if path.is_file()}
    brought = {p for peer in peers for p in (home / "agents" / peer).rglob("*") if p.is_file()}
    assert set(landing(template, home, "mine")) == written - brought
    assert written - brought


def test_the_command_line_says_why_an_id_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MY_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(sys, "argv", ["my-agent-crew", "agent", "add", "kongming", "--id", "../x"])

    assert entry.main() == 1

    assert texts.AGENT_ID_INVALID in capsys.readouterr().out
    assert not (tmp_path / "x").exists()
    assert not (tmp_path / "home" / "agents").exists()


@pytest.fixture
def crew(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, runtime, home


def copy_in(home: Path, name: str, workspace: Path | None = None) -> None:
    folder = home / "agents" / name
    folder.mkdir(parents=True, exist_ok=True)
    pinned = f"workspace: {workspace}\n" if workspace else ""
    (folder / "agent.yaml").write_text(f"name: {name}\n{pinned}", encoding="utf-8")


def test_a_reload_takes_in_every_folder_copied_in_or_none(crew, tmp_path):
    """Building an agent makes its workspace. One that cannot be a folder was a traceback,
    and the folders read before it had joined the crew by then."""
    client, runtime, home = crew
    taken = tmp_path / "notes.txt"
    taken.write_text("x", encoding="utf-8")
    copy_in(home, "alpha", tmp_path / "repo")
    copy_in(home, "beta", taken)
    copy_in(home, "gamma")

    refused = client.post("/api/agents/reload")

    assert refused.status_code == 422, refused.text
    assert "notes.txt" in refused.json()["detail"]
    assert sorted(runtime.agents) == ["default"]
    assert [agent["id"] for agent in client.get("/api/agents").json()] == ["default"]
    assert client.get("/api/agents").json()[0]["delegates"] == []

    copy_in(home, "beta")
    assert client.post("/api/agents/reload").json() == {"added": ["alpha", "beta", "gamma"]}
    assert client.get("/api/agents").json()[0]["delegates"] == ["alpha", "beta", "gamma"]
