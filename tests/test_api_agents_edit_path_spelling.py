"""How an edit may spell a path that lies outside the crew home.

`agent.yaml` keeps the text an edit sent, and that text is followed again at the next
start and whenever the crew is rebuilt. A text that reaches the agent's tree through a
link, or by going into a folder and back out with `..`, is that tree only until the link
or the folder is moved, and an agent with a shell can move either. So an edit spells such
a path as the file already does, or as the path itself with nothing left to follow.
"""

import os
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


@pytest.mark.parametrize(
    ("held_as", "sent_as"), [("workspace", "skills_dirs"), ("skills_dirs", "workspace")]
)
def test_a_spelling_the_file_holds_for_one_kind_is_a_new_one_for_another(
    start, tmp_path: Path, held_as, sent_as
) -> None:
    """One tree outside the home is the agent's workspace and a folder its skills are read
    from. The file reaches it through a link for one of the two, and by the path itself
    for the other: the link is the owner's spelling of the one, and of that one alone."""
    tree = tmp_path / "outside" / "repo"
    tree.mkdir(parents=True)
    tree = tree.resolve()
    alias = tmp_path / "alias"
    alias.symlink_to(tree)
    written = {held_as: str(alias), sent_as: str(tree)}
    manifest = f"workspace: {written['workspace']}\nskills_dirs:\n  - {written['skills_dirs']}\n"
    client, runtime, file = start(manifest)

    sent = str(alias) if sent_as == "workspace" else [str(alias)]
    reply = patch(client, **{sent_as: sent}, max_steps=41)

    assert reply.status_code == 422
    assert f" {tree}" in reply.json()["detail"].replace(str(alias), "")
    assert file.read_text(encoding="utf-8") == manifest
    assert runtime.deps_for("coder").agent.settings.max_steps != 41


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


# --- a link that lies outside the home and leads into it ---


@pytest.fixture(params=KEYS)
def door(request, tmp_path: Path, agent_dir: Path) -> Aim:
    """A place of each kind inside the home, and a link to it lying in a tree outside the
    home: where an agent that works in that tree can point the link somewhere else."""
    inside = {
        "workspace": agent_dir / "bench",
        "skills_dirs": agent_dir / "more-skills",
        "persona_files": agent_dir / "NOTES.md",
    }[request.param]
    if request.param == "persona_files":
        inside.write_text(PERSONA, encoding="utf-8")
    else:
        inside.mkdir()
    tree = tmp_path / "outside" / "repo"
    tree.mkdir(parents=True)
    (tree / "door").symlink_to(inside)
    return Aim(request.param, inside.resolve(), tree, tree / "door")


def through(door: Aim, agent_dir: Path, how: str) -> str:
    """The link named by its own path, or from the agent's folder by climbing out of the
    home with `..`: a text that begins inside the home and lies outside it once folded."""
    return str(door.alias) if how == "by its path" else os.path.relpath(door.alias, agent_dir)


@pytest.mark.parametrize("how", ["by its path", "climbing out of the home"])
def test_a_link_outside_the_home_that_leads_into_it_is_refused_with_the_place_to_write(
    start, door: Aim, agent_dir, how
) -> None:
    manifest = "name: Thợ mã\n"
    client, runtime, file = start(manifest)
    sent = through(door, agent_dir, how)

    reply = patch(client, **{door.key: door.value(sent)}, max_steps=41)

    # Where it leads today is inside the home. Where it lies is not, and whoever works in
    # that tree points it elsewhere tomorrow.
    assert reply.status_code == 422
    detail = reply.json()["detail"]
    assert sent in detail
    assert f" {door.real}" in detail.replace(sent, "")
    assert file.read_text(encoding="utf-8") == manifest
    assert runtime.deps_for("coder").agent.settings.max_steps != 41


@pytest.mark.parametrize("how", ["by its path", "climbing out of the home"])
def test_pointing_such_a_link_elsewhere_after_a_save_leads_the_agent_nowhere_new(
    start, door: Aim, agent_dir, tmp_path: Path, how
) -> None:
    client, runtime, _ = start("name: Thợ mã\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "PERSONA.md").write_text(SECRET, encoding="utf-8")

    patch(client, **{door.key: door.value(through(door, agent_dir, how))})
    door.alias.unlink()
    door.alias.symlink_to(elsewhere / "PERSONA.md" if door.real.is_file() else elsewhere)

    # Whatever the save answered, neither the agent as it runs nor the file read at the
    # next start follows the link to where it was pointed afterwards.
    for agent in (runtime.deps_for("coder").agent, read_again(runtime)):
        assert not door.followed_by(agent).is_relative_to(elsewhere.resolve())


def test_the_place_such_a_link_leads_to_is_taken_by_its_own_path(start, door: Aim) -> None:
    client, runtime, file = start("name: Thợ mã\n")

    reply = patch(client, **{door.key: door.value(str(door.real))}, max_steps=41)

    assert reply.status_code == 200
    assert booted(file)[door.key] == door.value(str(door.real))
    agent = runtime.deps_for("coder").agent
    assert agent.settings.max_steps == 41
    assert door.followed_by(agent) == door.real


def test_such_a_link_the_owner_wrote_in_the_file_is_sent_back_and_taken(start, door: Aim) -> None:
    typed = str(door.alias)
    client, runtime, file = start(door.manifest(typed))

    reply = patch(client, **{door.key: door.value(typed)}, max_steps=41)

    # The owner wrote it so, for this kind of path: the save writes nothing new.
    assert reply.status_code == 200
    assert booted(file)[door.key] == door.value(typed)
    agent = runtime.deps_for("coder").agent
    assert agent.settings.max_steps == 41
    assert door.followed_by(agent) == door.real


# --- `~`, which a workspace and a skills folder are read with, and a persona's name is not ---


@pytest.fixture
def own_folder(tmp_path: Path, monkeypatch) -> Path:
    """The folder `~` stands for, somewhere outside the crew home."""
    own = tmp_path / "nguoi-dung"
    own.mkdir()
    monkeypatch.setenv("HOME", str(own))
    return own


@pytest.mark.parametrize("aim", ["workspace", "skills_dirs"], indirect=True)
def test_a_spelling_from_the_persons_own_folder_through_a_link_is_refused(
    start, aim: Aim, own_folder: Path
) -> None:
    (own_folder / "alias").symlink_to(aim.real)
    manifest = aim.manifest(str(aim.real))
    client, runtime, file = start(manifest)

    reply = patch(client, **{aim.key: aim.value("~/alias")}, max_steps=41)

    # The start reads `~` as the person's own folder, so that is where the text is followed
    # from here too: to a link, and not to a folder called `~` beside the agent's file.
    assert reply.status_code == 422
    assert f" {aim.real}" in reply.json()["detail"]
    assert file.read_text(encoding="utf-8") == manifest
    assert runtime.deps_for("coder").agent.settings.max_steps != 41


@pytest.mark.parametrize("door", ["workspace", "skills_dirs"], indirect=True)
def test_a_link_into_the_home_named_from_the_persons_own_folder_is_refused(
    start, door: Aim, own_folder: Path
) -> None:
    (own_folder / "door").symlink_to(door.real)
    manifest = "name: Thợ mã\n"
    client, runtime, file = start(manifest)

    reply = patch(client, **{door.key: door.value("~/door")}, max_steps=41)

    assert reply.status_code == 422
    assert f" {door.real}" in reply.json()["detail"]
    assert file.read_text(encoding="utf-8") == manifest
    assert runtime.deps_for("coder").agent.settings.max_steps != 41


def test_a_personas_name_that_begins_with_a_tilde_is_a_folder_beside_the_agents_file(
    start, agent_dir: Path, own_folder: Path, tmp_path: Path
) -> None:
    (agent_dir / "~").mkdir(parents=True)
    (agent_dir / "~" / "NOTES.md").write_text(PERSONA, encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (own_folder / "NOTES.md").symlink_to(elsewhere)
    client, runtime, file = start("name: Thợ mã\n")

    reply = patch(client, persona_files=["~/NOTES.md"], max_steps=41)

    # The start joins a persona's name to the agent's folder as it stands, so the name is
    # judged there: what the person's own folder holds under that name has no say.
    assert reply.status_code == 200
    assert booted(file)["persona_files"] == ["~/NOTES.md"]
    agent = runtime.deps_for("coder").agent
    assert [agent.dir / name for name in agent.persona_files] == [agent_dir / "~" / "NOTES.md"]


def test_a_home_named_through_a_link_is_written_by_where_it_is_or_from_the_agents_folder(
    tmp_path: Path,
) -> None:
    """The home is the place its name led to when the server started. A text that reaches
    it by that name goes through a link lying outside it, like any other."""
    folder = tmp_path / "home" / "agents" / "coder"
    (folder / "bench").mkdir(parents=True)
    (folder / "agent.yaml").write_text("name: Thợ mã\n", encoding="utf-8")
    (tmp_path / "shortcut").symlink_to(tmp_path / "home")
    env = {"MY_AGENT_HOME": str(tmp_path / "shortcut"), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    real = folder.resolve() / "bench"

    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        by_the_link = patch(client, workspace=str(tmp_path / "shortcut/agents/coder/bench"))
        from_the_folder = patch(client, workspace="bench")
        by_itself = patch(client, workspace=str(real))

    assert by_the_link.status_code == 422
    assert f" {real}" in by_the_link.json()["detail"]
    assert (from_the_folder.status_code, by_itself.status_code) == (200, 200)
    assert runtime.deps_for("coder").agent.workspace == real


# A word the start's reader takes for a switch or for a text, and the library a save writes
# with takes another way: the key, the line a hand wrote, the name the library reads in it.
READ_TWO_WAYS = [
    ("workspace", "workspace: no\n", "no"),
    ("skills_dirs", "skills_dirs:\n  - no\n", "no"),
    ("persona_files", "persona_files:\n  - 0o10\n", "8"),
]


@pytest.mark.parametrize(("key", "by_hand", "read_otherwise"), READ_TWO_WAYS, ids=KEYS)
def test_a_path_is_spelled_as_the_start_reads_the_file_and_no_other_way(
    start, tmp_path: Path, agent_dir: Path, key: str, by_hand: str, read_otherwise: str
) -> None:
    """The file to be is judged as the next start will read it. Read as the library that
    writes it reads it, a word of the file names a place the file never named: here a link
    out of the home, and a save about something else would be refused over it."""
    (tmp_path / "elsewhere").mkdir()
    (agent_dir / read_otherwise).symlink_to(tmp_path / "elsewhere")
    client, runtime, file = start("name: Thợ mã\n" + by_hand)
    before = runtime.deps_for("coder").agent

    reply = patch(client, description="Viết mã")

    assert reply.status_code == 200, reply.text
    assert by_hand in file.read_text(encoding="utf-8")
    assert booted(file)["description"] == "Viết mã"
    after = runtime.deps_for("coder").agent
    assert after.description == "Viết mã"
    for name in ("workspace", "skills_dirs", "persona_files"):
        assert getattr(after, name) == getattr(before, name) == getattr(read_again(runtime), name)
