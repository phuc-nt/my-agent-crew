"""An install that is refused leaves the home as it was.

What the request names is checked, and the home read, before a file is written; what was
written is put back when it cannot join the crew. One refusal used to leave a folder behind
that stopped every start after it, and an id with a path in it wrote outside the home."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew import texts
from my_agent_crew.agents import load_profiles, templates_cli
from my_agent_crew.config import load_settings
from my_agent_crew.server import build_runtime, create_app
from my_agent_crew.server.runtime_build import check_delegates

INSTALL = "/api/agents/install"
UNREADABLE = {
    "yaml that does not parse": "name: [unclosed\n",
    "a key of the wrong shape": "name: Odd\nmax_steps: [1]\n",
    "two schedules on one id": (
        "name: Odd\nschedules:\n"
        "  - {id: a, cron: '0 7 * * *', prompt: x}\n"
        "  - {id: a, cron: '0 8 * * *', prompt: y}\n"
    ),
}
NO_AGENT_ID = ["../../out", "a/b", "/abs", "Kong Ming", "KONG", ".trash", "kong\n", "-x"]
NO_TEMPLATE = ["../templates/kongming", "kongming/", "./kongming", "_shared_skills", ""]
REVIEWER_MD = "---\nname: Reviewer\ndescription: Reads code.\n---\nYou read code.\n"


def serve(home: Path):
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    return runtime, TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1")


@pytest.fixture
def crew(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    runtime, served = serve(home)
    with served as client:
        yield client, runtime, home


def standing(root: Path) -> dict[str, bytes | None]:
    """Every folder under `root`, and every file with what it holds. The database is left
    out: the server writes to it on its own."""
    return {
        str(path.relative_to(root)): path.read_bytes() if path.is_file() else None
        for path in sorted(root.rglob("*"))
        if "sqlite" not in path.name
    }


def starts(runtime) -> list[str]:
    """The ids the next start reads from this home. It raises when the start would stop."""
    profiles = load_profiles(runtime.settings)
    check_delegates(profiles)
    return sorted(profile.id for profile in profiles)


@pytest.mark.parametrize("text", UNREADABLE.values(), ids=UNREADABLE.keys())
def test_a_home_that_cannot_be_read_as_a_crew_refuses_the_install_before_it_writes(
    crew, tmp_path, text
):
    client, runtime, home = crew
    odd = home / "agents" / "odd"
    odd.mkdir(parents=True)
    (odd / "agent.yaml").write_text(text, encoding="utf-8")
    before = standing(tmp_path)
    # A workspace is made before the template is written, and nothing takes it away again:
    # one that is not there afterwards says the home was read first.
    body = {"template": "kongming", "workspace": str(tmp_path / "repo")}

    refused = client.post(INSTALL, json=body)

    assert refused.status_code == 422, refused.text
    assert "odd" in refused.json()["detail"]
    assert standing(tmp_path) == before
    assert sorted(runtime.agents) == ["default"]

    # Nothing of the refused install is in the way once the file is put right.
    (odd / "agent.yaml").write_text("name: Odd\n", encoding="utf-8")
    assert client.post(INSTALL, json={"template": "kongming"}).status_code == 201
    assert sorted(runtime.agents) == ["default", "kongming", "odd"]


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("agent_id", NO_AGENT_ID)
def test_an_id_that_is_no_agent_id_is_refused_and_nothing_is_written(
    crew, tmp_path, agent_id, force
):
    """`../../out` used to land beside the home, and `a/b` two folders deep inside it."""
    client, runtime, _ = crew
    before = standing(tmp_path)
    body = {"template": "kongming", "agent_id": agent_id, "force": force}

    refused = client.post(INSTALL, json=body)

    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"] == texts.AGENT_ID_INVALID
    assert standing(tmp_path) == before
    assert sorted(runtime.agents) == ["default"]


@pytest.mark.parametrize("template", NO_TEMPLATE)
def test_a_template_is_one_of_the_bundled_ones_by_its_plain_name(crew, tmp_path, template):
    """`../templates/kongming` used to install into the home's `templates` folder."""
    client, runtime, _ = crew
    before = standing(tmp_path)

    refused = client.post(INSTALL, json={"template": template, "force": True})

    assert refused.status_code == 404, refused.text
    assert standing(tmp_path) == before
    assert sorted(runtime.agents) == ["default"]


@pytest.mark.parametrize("force", [False, True])
def test_the_masters_id_is_taken_whatever_force_says(crew, tmp_path, force):
    """A folder by that id stopped every start after it."""
    client, runtime, _ = crew
    before = standing(tmp_path)
    body = {"template": "kongming", "agent_id": "default", "force": force}

    refused = client.post(INSTALL, json=body)

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == texts.AGENT_EXISTS.format(agent_id="default")
    assert standing(tmp_path) == before
    assert starts(runtime) == ["default"]


@pytest.mark.parametrize("force", [False, True])
def test_an_id_an_agent_from_a_kit_goes_by_is_taken_whatever_force_says(tmp_path, force):
    """It runs with no folder of its own, so `force` has nothing of its own to write over:
    a folder by its id took the id from it at the next start."""
    home = tmp_path / "home"
    (home / ".agents" / "agents").mkdir(parents=True)
    (home / ".agents" / "agents" / "reviewer.md").write_text(REVIEWER_MD, encoding="utf-8")
    runtime, served = serve(home)
    body = {"template": "kongming", "agent_id": "reviewer", "force": force}

    with served as client:
        before = standing(tmp_path)
        refused = client.post(INSTALL, json=body)

    assert refused.status_code == 409, refused.text
    assert standing(tmp_path) == before
    assert sorted(runtime.agents) == ["default", "reviewer"]


def test_a_workspace_that_cannot_be_a_folder_is_refused_before_anything_is_written(crew, tmp_path):
    client, runtime, _ = crew
    taken = tmp_path / "notes.txt"
    taken.write_text("x", encoding="utf-8")
    before = standing(tmp_path)

    for workspace in (taken, taken / "under"):
        body = {"template": "kongming", "workspace": str(workspace)}
        refused = client.post(INSTALL, json=body)
        assert refused.status_code == 422, refused.text
        assert "notes.txt" in refused.json()["detail"]

    assert standing(tmp_path) == before
    assert sorted(runtime.agents) == ["default"]


def test_forcing_a_bad_workspace_over_an_agent_that_runs_leaves_its_file_alone(crew, tmp_path):
    """An agent that runs is not built again, so nothing else asks whether the workspace
    can be a folder: this was a 201 whose file stopped the next start."""
    client, runtime, _ = crew
    assert client.post(INSTALL, json={"template": "kongming"}).status_code == 201
    taken = tmp_path / "notes.txt"
    taken.write_text("x", encoding="utf-8")
    before = standing(tmp_path)
    body = {"template": "kongming", "workspace": str(taken), "force": True}

    refused = client.post(INSTALL, json=body)

    assert refused.status_code == 422, refused.text
    assert standing(tmp_path) == before
    assert sorted(runtime.agents) == ["default", "kongming"]


def test_a_workspace_that_is_not_there_yet_is_made(crew, tmp_path):
    client, runtime, _ = crew
    repo = tmp_path / "repos" / "new"

    res = client.post(INSTALL, json={"template": "kongming", "workspace": str(repo)})

    assert res.status_code == 201, res.text
    assert repo.is_dir()
    assert runtime.deps_for("kongming").agent.workspace == repo.resolve()


@pytest.fixture
def lonely(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A template whose delegate nobody goes by: what it writes cannot join the crew. The
    bundled ones all can, so this is the one way to get past the checks before the write."""
    bundled = tmp_path / "bundled"
    (bundled / "lonely").mkdir(parents=True)
    manifest = "name: Lonely\ndelegates: [nobody]\n"
    (bundled / "lonely" / "agent.yaml").write_text(manifest, encoding="utf-8")
    (bundled / "lonely" / "SOUL.md").write_text("from the template\n", encoding="utf-8")
    (bundled / "_shared_skills").mkdir()
    (bundled / "_shared_skills" / "git.md").write_text("from the template\n", encoding="utf-8")
    monkeypatch.setattr(templates_cli, "TEMPLATES_DIR", bundled)
    return "lonely"


def test_what_an_install_wrote_is_taken_away_when_it_cannot_join_the_crew(crew, tmp_path, lonely):
    client, runtime, _ = crew
    before = standing(tmp_path)

    refused = client.post(INSTALL, json={"template": lonely})

    assert refused.status_code == 422, refused.text
    assert "nobody" in refused.json()["detail"]
    assert standing(tmp_path) == before
    assert sorted(runtime.agents) == ["default"]
    assert starts(runtime) == ["default"]


def test_a_forced_install_that_cannot_join_puts_back_what_it_wrote_over(crew, tmp_path, lonely):
    client, runtime, home = crew
    made = client.post("/api/agents", json={"agent_id": "lonely", "profile": {"name": "Mine"}})
    assert made.status_code == 201, made.text
    (home / "agents" / "lonely" / "SOUL.md").write_text("my own words\n", encoding="utf-8")
    (home / "skills" / "git.md").write_text("my own skill\n", encoding="utf-8")
    before = standing(tmp_path)

    refused = client.post(INSTALL, json={"template": lonely, "force": True})

    assert refused.status_code == 422, refused.text
    assert standing(tmp_path) == before
    assert starts(runtime) == ["default", "lonely"]
