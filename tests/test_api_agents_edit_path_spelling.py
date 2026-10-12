"""How an edit may spell a path that lies outside the crew home.

`agent.yaml` keeps the text an edit sent, and that text is followed again at the next
start and whenever the crew is rebuilt. A text that reaches the agent's tree through a
link, or by going into a folder and back out with `..`, is that tree only until the link
or the folder is moved, and an agent with a shell can move either. So an edit spells such
a path as the file already does, or as the path itself with nothing left to follow.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from my_agent_crew.agents.profile import AgentProfile
from my_agent_crew.agents.profile_yaml import load_yaml_profiles
from my_agent_crew.config import load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime_build import build_runtime

SECRET = "OPENROUTER_API_KEY=sk-that-must-not-travel"
PERSONA = "Bạn là thợ mã của đội."
KEYS = ("workspace", "skills_dirs", "persona_files")
# The name the start reads for each kind when the file says nothing: the agent's own
# `workspace` and `skills` folders and the first of its persona files.
READ_UNASKED = {"workspace": "workspace", "skills_dirs": "skills", "persona_files": "AGENTS.md"}


@dataclass(frozen=True)
class Aim:
    """One kind of path a manifest names, aimed at something outside the home."""

    key: str
    real: Path  # where the owner aimed the agent
    entered: Path  # a folder beside it that a spelling can go into and come back out of
    alias: Path  # a link that leads to `real`

    @property
    def through_a_link(self) -> str:
        return str(self.alias)

    @property
    def in_and_back_out(self) -> str:
        back = Path("..", self.real.name) if self.real.is_file() else Path("..")
        return str(self.entered / back)

    def spelled(self, how: str) -> str:
        return str(self.real) if how == "real" else getattr(self, how)

    def value(self, text: str) -> Any:
        return text if self.key == "workspace" else [text]

    def manifest(self, text: str) -> str:
        # A list is laid out as the save lays it out, so a file can be compared whole.
        return f"workspace: {text}\n" if self.key == "workspace" else f"{self.key}:\n  - {text}\n"

    def followed_by(self, profile: AgentProfile) -> Path:
        """Where a profile read from the file points for this kind."""
        if self.key == "workspace":
            return profile.workspace
        if self.key == "skills_dirs":
            return profile.skills_dirs[-1]
        return (profile.dir / profile.persona_files[-1]).resolve()


@pytest.fixture(params=KEYS)
def aim(request, tmp_path: Path) -> Aim:
    outside = tmp_path / "outside"
    real = {
        "workspace": outside / "repo",
        "skills_dirs": outside / "shared-skills",
        "persona_files": outside / "notes" / "PERSONA.md",
    }[request.param]
    folder = real.parent if request.param == "persona_files" else real
    (folder / "sub").mkdir(parents=True)
    if request.param == "persona_files":
        real.write_text(PERSONA, encoding="utf-8")
    alias = tmp_path / "alias"
    alias.symlink_to(real)
    return Aim(request.param, real.resolve(), folder.resolve() / "sub", alias)


@pytest.fixture
def agent_dir(tmp_path: Path) -> Path:
    path = tmp_path / "home" / "agents" / "coder"
    path.mkdir(parents=True)
    return path


@pytest.fixture
def start(tmp_path: Path, agent_dir: Path):
    """A crew whose `coder` runs from a file written by hand, as given."""
    clients = []

    def started(manifest: str):
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


def patch(client, **profile):
    return client.patch("/api/agents/coder", json={"profile": profile})


def booted(file: Path) -> dict[str, Any]:
    return yaml.safe_load(file.read_text(encoding="utf-8"))


def read_again(runtime) -> AgentProfile:
    """The agent as a start reads it from the file, links followed afresh."""
    return next(p for p in load_yaml_profiles(runtime.settings) if p.id == "coder")


def move_what_can_be_moved(aim: Aim, tmp_path: Path) -> None:
    """What an agent with a shell can do after a save: point the link somewhere else, and
    swap the folder a spelling went into for a link, so that coming back out lands
    elsewhere. Elsewhere holds a file nobody meant to hand over."""
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "deep").mkdir(parents=True)
    (elsewhere / "PERSONA.md").write_text(SECRET, encoding="utf-8")
    aim.alias.unlink()
    aim.alias.symlink_to(elsewhere / "PERSONA.md" if aim.real.is_file() else elsewhere)
    aim.entered.rmdir()
    aim.entered.symlink_to(elsewhere / "deep")


@pytest.mark.parametrize("how", ["through_a_link", "in_and_back_out"])
def test_a_new_spelling_of_the_kept_path_is_refused_with_the_path_to_write(
    start, aim: Aim, how
) -> None:
    manifest = aim.manifest(str(aim.real))
    client, runtime, file = start(manifest)

    reply = patch(client, **{aim.key: aim.value(aim.spelled(how))}, max_steps=41)

    assert reply.status_code == 422
    detail = reply.json()["detail"]
    # The sentence names the text that was sent and the one to send in its place.
    assert aim.spelled(how) in detail
    assert f" {aim.real}" in detail.replace(aim.spelled(how), "")
    assert file.read_text(encoding="utf-8") == manifest
    agent = runtime.deps_for("coder").agent
    assert agent.settings.max_steps != 41
    assert aim.followed_by(agent) == aim.real


@pytest.mark.parametrize("how", ["through_a_link", "in_and_back_out"])
def test_the_files_own_spelling_sent_back_is_taken_and_stays_as_typed(start, aim: Aim, how) -> None:
    typed = aim.spelled(how)
    client, runtime, file = start(aim.manifest(typed))

    reply = patch(client, **{aim.key: aim.value(typed)}, max_steps=41)

    # The owner wrote it so: the save writes nothing the file did not hold, and it is not
    # rewritten into the path it leads to on the owner's behalf.
    assert reply.status_code == 200
    assert booted(file)[aim.key] == aim.value(typed)
    agent = runtime.deps_for("coder").agent
    assert agent.settings.max_steps == 41
    assert aim.followed_by(agent) == aim.real


@pytest.mark.parametrize("how", ["through_a_link", "in_and_back_out"])
def test_the_owners_spelling_holds_up_no_save_of_another_key(start, aim: Aim, how) -> None:
    manifest = aim.manifest(aim.spelled(how))
    client, runtime, file = start(manifest)

    reply = patch(client, max_steps=41)

    assert reply.status_code == 200
    assert file.read_text(encoding="utf-8") == manifest + "max_steps: 41\n"
    assert aim.followed_by(runtime.deps_for("coder").agent) == aim.real


@pytest.mark.parametrize("held", ["real", "through_a_link", "in_and_back_out"])
def test_the_path_with_nothing_left_to_follow_is_taken(start, aim: Aim, held) -> None:
    client, runtime, file = start(aim.manifest(aim.spelled(held)))

    reply = patch(client, **{aim.key: aim.value(str(aim.real))}, max_steps=41)

    assert reply.status_code == 200
    assert booted(file)[aim.key] == aim.value(str(aim.real))
    assert runtime.deps_for("coder").agent.settings.max_steps == 41


@pytest.mark.parametrize("how", ["real", "through_a_link", "in_and_back_out"])
def test_nothing_moved_after_a_save_changes_where_the_saved_file_points(
    start, aim: Aim, tmp_path: Path, how
) -> None:
    client, runtime, _ = start(aim.manifest(str(aim.real)))

    patch(client, **{aim.key: aim.value(aim.spelled(how))})
    move_what_can_be_moved(aim, tmp_path)

    # Whatever the save answered, the file it left is read at the next start, and what it
    # names is still what the owner aimed the agent at.
    assert aim.followed_by(read_again(runtime)) == aim.real


def unasked(aim: Aim, agent_dir: Path) -> str:
    """The agent's own folder holds a link, under the name the start reads unasked, to
    what the owner keeps elsewhere."""
    name = READ_UNASKED[aim.key]
    (agent_dir / name).symlink_to(aim.real)
    return name


def test_the_name_the_start_reads_unasked_is_no_new_spelling(start, aim: Aim, agent_dir) -> None:
    name = unasked(aim, agent_dir)
    client, runtime, file = start("name: Thợ mã\n")

    reply = patch(client, **{aim.key: aim.value(name)}, max_steps=41)

    # The start follows that name whether or not the file says it, so writing it down
    # gives nobody a link the agent did not already follow.
    assert reply.status_code == 200
    assert booted(file)[aim.key] == aim.value(name)
    assert runtime.deps_for("coder").agent.settings.max_steps == 41


# The agent's own skills folder is read beside whatever the file names, so taking that
# key out leaves no name in its place.
@pytest.mark.parametrize("aim", ["workspace", "persona_files"], indirect=True)
def test_taking_the_key_out_may_not_leave_a_link_in_its_place(
    start, aim: Aim, agent_dir, tmp_path: Path
) -> None:
    unasked(aim, agent_dir)
    manifest = aim.manifest(str(aim.real))
    client, runtime, file = start(manifest)

    reply = patch(client, **{aim.key: None})

    # With the key gone the start reads the name it falls back on, and that name is a
    # link: the same place today, and wherever the link is pointed tomorrow.
    assert reply.status_code == 422
    assert f" {aim.real}" in reply.json()["detail"]
    assert file.read_text(encoding="utf-8") == manifest
    (agent_dir / READ_UNASKED[aim.key]).unlink()
    (agent_dir / READ_UNASKED[aim.key]).symlink_to(tmp_path)
    assert aim.followed_by(read_again(runtime)) == aim.real


def test_a_spelling_that_stays_inside_the_home_is_judged_as_before(start, agent_dir) -> None:
    client, runtime, file = start("name: Thợ mã\n")
    (agent_dir / "notes").mkdir()

    reply = patch(client, workspace="notes/../workspace", skills_dirs=["../coder/notes"])

    assert reply.status_code == 200
    agent = runtime.deps_for("coder").agent
    assert agent.workspace == (agent_dir / "workspace").resolve()
    assert (agent_dir / "notes").resolve() in agent.skills_dirs
    assert booted(file)["workspace"] == "notes/../workspace"
