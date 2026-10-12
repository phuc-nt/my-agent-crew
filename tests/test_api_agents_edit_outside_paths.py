"""Editing an agent whose hand-written file keeps a path outside the crew home.

`agent add --workspace` aims an agent at a repo elsewhere on purpose, and a file may name
a persona or a skills folder anywhere. Such an agent is still edited from the web: a path
it already runs with is not the edit's, and whoever reaches the port gains nothing by a
save that leaves it where it is. What an edit brings from outside the home is refused as
it always was, each kind of path measured against its own kind.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime_build import build_runtime

SECRET = "OPENROUTER_API_KEY=sk-that-must-not-travel"


@pytest.fixture
def start(tmp_path: Path):
    """A crew whose `coder` runs from a file written by hand, as given."""
    clients = []

    def started(manifest: str):
        agent_dir = tmp_path / "home" / "agents" / "coder"
        agent_dir.mkdir(parents=True)
        (agent_dir / "agent.yaml").write_text(manifest, encoding="utf-8")
        env = {"MY_AGENT_HOME": str(tmp_path / "home"), "MY_AGENT_ROUTES": "fake:echo"}
        runtime = build_runtime(load_settings(env=env))
        client = TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1")
        client.__enter__()
        clients.append(client)
        return client, runtime, agent_dir / "agent.yaml"

    yield started
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A tree beside the home, the kind an agent is aimed at on purpose."""
    path = tmp_path / "repo"
    (path / "src").mkdir(parents=True)
    (path / "NOTES.md").write_text(SECRET, encoding="utf-8")
    return path


def patch(client, **profile):
    return client.patch("/api/agents/coder", json={"profile": profile})


def prompt(client) -> str:
    return client.get("/api/agents/coder/prompt").json()["prompt"]


@pytest.mark.parametrize(
    ("change", "line", "in_force"),
    [
        ({"script_calls": "gated"}, "script_calls: gated\n", lambda a: a.settings.script_calls),
        ({"max_steps": 41}, "max_steps: 41\n", lambda a: a.settings.max_steps),
        ({"description": "dọn mã"}, "description: dọn mã\n", lambda a: a.description),
    ],
)
def test_another_key_saves_for_an_agent_that_works_outside_the_home(
    start, repo, change, line, in_force
) -> None:
    manifest = f"name: Thợ mã\nworkspace: {repo}\n"
    client, runtime, file = start(manifest)

    reply = patch(client, **change)

    assert reply.status_code == 200
    agent = runtime.deps_for("coder").agent
    (value,) = change.values()
    assert in_force(agent) == value
    # The tree the owner chose is still the one the file tools are scoped to.
    assert agent.workspace == repo.resolve()
    assert file.read_text(encoding="utf-8") == manifest + line


@pytest.mark.parametrize("spelled", ["{repo}", "{repo}/src/.."])
def test_the_workspace_the_file_already_holds_may_be_sent_again(start, repo, spelled) -> None:
    client, runtime, _ = start(f"workspace: {repo}\n")

    reply = patch(client, workspace=spelled.format(repo=repo), max_steps=41)

    assert reply.status_code == 200
    agent = runtime.deps_for("coder").agent
    assert agent.settings.max_steps == 41
    assert agent.workspace == repo.resolve()


@pytest.mark.parametrize("elsewhere", ["other", ".", "repo/src"])
def test_an_edit_cannot_move_an_outside_workspace_to_another_place_outside(
    start, repo, tmp_path: Path, elsewhere
) -> None:
    manifest = f"workspace: {repo}\n"
    client, runtime, file = start(manifest)
    target = tmp_path / elsewhere
    target.mkdir(exist_ok=True)

    reply = patch(client, workspace=str(target), max_steps=41)

    # Another tree, the folder above (which holds the home itself) or one below: each is
    # a place the file tools were not aimed at, and the owner's own choice vouches for
    # none of them.
    assert reply.status_code == 422
    assert str(target) in reply.json()["detail"]
    agent = runtime.deps_for("coder").agent
    assert agent.workspace == repo.resolve()
    assert agent.settings.max_steps != 41
    assert file.read_text(encoding="utf-8") == manifest


def test_an_outside_workspace_moved_into_the_home_cannot_be_moved_back(start, repo) -> None:
    client, runtime, file = start(f"workspace: {repo}\n")

    moved = patch(client, workspace="workspace")
    back = patch(client, workspace=str(repo))

    assert moved.status_code == 200
    inside = (file.parent / "workspace").resolve()
    # Once the agent no longer runs with the outside tree, naming it is an edit's doing.
    assert back.status_code == 422
    assert runtime.deps_for("coder").agent.workspace == inside


def test_an_outside_skills_folder_the_file_holds_does_not_hold_up_a_save(
    start, tmp_path: Path
) -> None:
    held, more = tmp_path / "shared-skills", tmp_path / "more-skills"
    held.mkdir()
    more.mkdir()
    client, runtime, _ = start(f"skills_dirs:\n- {held}\n")

    other = patch(client, max_steps=41)
    again = patch(client, skills_dirs=[str(held)], max_steps=42)
    added = patch(client, skills_dirs=[str(held), str(more)], max_steps=43)

    assert other.status_code == 200
    assert again.status_code == 200
    # A second folder outside the home is the edit's, whatever the first one is.
    assert added.status_code == 422
    assert str(more) in added.json()["detail"]
    agent = runtime.deps_for("coder").agent
    assert held.resolve() in agent.skills_dirs
    assert more.resolve() not in agent.skills_dirs
    assert agent.settings.max_steps == 42


def test_an_outside_persona_the_file_holds_does_not_hold_up_a_save(start, tmp_path: Path) -> None:
    persona, secret = tmp_path / "PERSONA.md", tmp_path / "credentials.txt"
    persona.write_text("Bạn là thợ mã của đội.", encoding="utf-8")
    secret.write_text(SECRET, encoding="utf-8")
    client, runtime, _ = start(f"persona_files:\n- {persona}\n")

    other = patch(client, max_steps=41)
    again = patch(client, persona_files=[str(persona)], max_steps=42)
    added = patch(client, persona_files=[str(persona), str(secret)], max_steps=43)

    assert other.status_code == 200
    assert again.status_code == 200
    # A persona file is read into the system prompt and goes to the model on the next
    # turn: a second one outside the home would hand any readable file to the provider.
    assert added.status_code == 422
    assert str(secret) in added.json()["detail"]
    assert runtime.deps_for("coder").agent.settings.max_steps == 42
    told = prompt(client)
    assert "Bạn là thợ mã của đội." in told
    assert SECRET not in told


def test_an_outside_workspace_vouches_for_no_other_kind_of_path(start, repo) -> None:
    client, runtime, file = start(f"workspace: {repo}\n")

    as_skills = patch(client, skills_dirs=[str(repo)])
    as_persona = patch(client, persona_files=[str(repo / "NOTES.md")])

    # The owner aimed the file tools at that tree. That makes it neither a place skills
    # are loaded from nor a place whose files are sent to the provider as a persona.
    assert as_skills.status_code == 422
    assert as_persona.status_code == 422
    assert repo.resolve() not in runtime.deps_for("coder").agent.skills_dirs
    assert SECRET not in prompt(client)
    assert file.read_text(encoding="utf-8") == f"workspace: {repo}\n"


def test_an_outside_skills_folder_vouches_for_no_workspace(start, tmp_path: Path) -> None:
    held = tmp_path / "shared-skills"
    held.mkdir()
    client, runtime, _ = start(f"skills_dirs:\n- {held}\n")
    before = runtime.deps_for("coder").agent.workspace

    reply = patch(client, workspace=str(held))

    assert reply.status_code == 422
    assert runtime.deps_for("coder").agent.workspace == before


def test_an_outside_persona_vouches_for_no_skills_folder_or_workspace(
    start, tmp_path: Path
) -> None:
    persona = tmp_path / "PERSONA.md"
    persona.write_text("Bạn là thợ mã của đội.", encoding="utf-8")
    client, runtime, _ = start(f"persona_files:\n- {persona}\n")
    before = runtime.deps_for("coder").agent

    as_skills = patch(client, skills_dirs=[str(persona)])
    as_workspace = patch(client, workspace=str(persona))

    assert as_skills.status_code == 422
    assert as_workspace.status_code == 422
    agent = runtime.deps_for("coder").agent
    assert (agent.workspace, agent.skills_dirs) == (before.workspace, before.skills_dirs)


def test_a_path_written_by_hand_since_the_start_is_not_yet_one_the_agent_runs_with(
    start, repo
) -> None:
    client, runtime, file = start("name: Thợ mã\n")
    before = runtime.deps_for("coder").agent.workspace
    file.write_text(f"name: Thợ mã\nworkspace: {repo}\n", encoding="utf-8")

    reply = patch(client, max_steps=41)

    # Measured against the running agent, not the file: a save here would aim the file
    # tools at that tree at once, without the restart a hand-written change waits for.
    assert reply.status_code == 422
    assert str(repo) in reply.json()["detail"]
    assert runtime.deps_for("coder").agent.workspace == before


def test_a_new_agent_may_not_be_aimed_where_another_already_works(start, repo) -> None:
    client, runtime, _ = start(f"workspace: {repo}\n")

    reply = client.post(
        "/api/agents", json={"agent_id": "helper", "profile": {"workspace": str(repo)}}
    )

    # A new agent runs with nothing yet, so every path it names is the edit's, and one
    # agent working in a tree by the owner's hand lets no caller aim a second one there.
    assert reply.status_code == 422
    assert str(repo) in reply.json()["detail"]
    assert "helper" not in runtime.agents
