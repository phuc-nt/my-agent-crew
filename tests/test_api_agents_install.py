"""Installing a template over HTTP: the files land in the home, the new agents join the
running crew, and the master can delegate to them without a restart."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import load_settings
from my_agent_crew.server import build_runtime, create_app
from my_agent_crew.tools.delegate import DELEGATE_TOOL_NAME


@pytest.fixture
def crew(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, runtime, home


def _enum(runtime) -> list[str]:
    tool = runtime.default.tools.get(DELEGATE_TOOL_NAME)
    return tool.parameters["properties"]["agent"]["enum"]


def test_installing_a_template_makes_it_live_for_the_master(crew):
    client, runtime, home = crew
    assert _enum(runtime) == ["default"]

    res = client.post("/api/agents/install", json={"template": "kongming"})

    assert res.status_code == 201, res.text
    assert res.json() == {"installed": ["kongming"], "live": ["kongming"], "needs_restart": False}
    assert (home / "agents" / "kongming" / "agent.yaml").is_file()
    assert _enum(runtime) == ["default", "kongming"]
    listed = {a["id"]: a for a in client.get("/api/agents").json()}
    assert listed["default"]["is_master"] and listed["default"]["delegates"] == ["kongming"]
    assert listed["kongming"]["delegates"] == [] and not listed["kongming"]["is_master"]
    # Without a workspace of its own the newcomer works where the master does.
    assert Path(listed["kongming"]["workspace"]) == runtime.default.agent.workspace


def test_a_workspace_is_pinned_into_the_agent_and_the_peers_it_brings(crew, tmp_path):
    client, runtime, home = crew
    repo = tmp_path / "repo"
    repo.mkdir()

    res = client.post(
        "/api/agents/install", json={"template": "fullstack-developer", "workspace": str(repo)}
    )

    body = res.json()
    assert res.status_code == 201 and body["installed"][0] == "fullstack-developer"
    assert set(body["live"]) == set(body["installed"]) and body["needs_restart"] is False
    for agent_id in body["installed"]:
        assert runtime.deps_for(agent_id).agent.workspace == repo.resolve(), agent_id
    text = (home / "agents" / "kongming" / "agent.yaml").read_text(encoding="utf-8")
    assert f"workspace: {repo.resolve()}" in text and "skills_dirs" in text


def test_unknown_templates_and_taken_ids_are_refused(crew):
    client, _, _ = crew
    assert client.post("/api/agents/install", json={"template": "architect"}).status_code == 404
    assert client.post("/api/agents/install", json={"template": "kongming"}).status_code == 201
    res = client.post("/api/agents/install", json={"template": "kongming"})
    assert res.status_code == 409 and "kongming" in res.json()["detail"]


def test_the_master_can_delegate_to_an_agent_installed_moments_ago(crew):
    client, runtime, _ = crew
    client.post("/api/agents/install", json={"template": "researcher"})
    conv = client.post("/api/conversations", json={"autonomous": True}).json()
    prompt = '/tool delegate {"agent": "researcher", "task": "tìm ba nguồn về sqlite"}'

    res = client.post(f"/api/conversations/{conv['id']}/messages", json={"text": prompt})

    assert res.status_code == 200
    children = [c for c in runtime.store.list("researcher")]
    assert len(children) == 1 and "sqlite" in children[0].title
