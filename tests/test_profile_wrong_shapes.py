"""A profile of the wrong shape is refused where it is read, and crashes nobody who reads it.

One parser reads a profile (`agents/profile_yaml.py`), whether a person wrote the file by
hand or the web sent an edit, and what it is handed is loose: whatever YAML or JSON holds
under each key. Where it met a shape it did not expect and raised anything but the error a
bad profile is told by, a start died on a traceback and an edit was answered 500, with
nothing saying which key was wrong. A value it let through unread did the same later, at
the first listing of the agents.

So every place a profile holds a value is walked here with every shape a value can take:
each key of a profile, each field of a schedule row of each kind, each field of the Telegram
block, and the body of the two edit routes itself. A key that names a path is walked with
the texts no path is written as besides. The places come from the code's own tables, so a
key added later is walked too. Whatever the pair, the parser hands back a
profile that can be listed or says what is wrong, and a route takes the edit or refuses it
with 422, the files and the running crew as they were.
"""

from __future__ import annotations

import errno
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from my_agent_crew.agents import DEFAULT_AGENT_ID
from my_agent_crew.agents.channels import TELEGRAM_KEYS
from my_agent_crew.agents.profile import PROFILE_KEYS
from my_agent_crew.agents.profile_edit_paths import PATH_KEYS
from my_agent_crew.agents.profile_read_back import read_now
from my_agent_crew.agents.profile_yaml import load_yaml_profiles, parse_profile
from my_agent_crew.agents.schedule import SCHEDULE_KEYS
from my_agent_crew.config import Route, Settings, load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.server.runtime_build import build_runtime

# The agent the edits are sent to, and the one the creations ask for.
EDITED, NEW = "coder", "moi"
EDIT, CREATE = f"/api/agents/{EDITED}", "/api/agents"
# What each route answers an edit it took.
TAKEN = {"PATCH": 200, "POST": 201}

# The shapes a value can take, as far as one level down: each kind, the empty one of each,
# and a list holding each.
SHAPES: dict[str, Any] = {
    "a number": 5,
    "zero": 0,
    "true": True,
    "false": False,
    "null": None,
    "a text": "chữ",
    "an empty text": "",
    "a list of texts": ["chữ"],
    "an empty list": [],
    "a mapping": {"k": "v"},
    "an empty mapping": {},
    "a list of a number": [5],
    "a list of null": [None],
    "a list of an empty text": [""],
    "a list of a mapping": [{"k": "v"}],
    "a list of an empty mapping": [{}],
    "a list of a list": [["chữ"]],
    "a list of an empty list": [[]],
}
# A schedule of each kind. Between them they hold every field a row is told apart by, so a
# field is walked as a row's own and beside what another row already does.
ROWS: dict[str, dict[str, Any]] = {
    "prompt": {"id": "sang", "name": "Sáng", "cron": "0 7 * * *", "prompt": "chào"},
    "command": {"id": "sang", "name": "Sáng", "every": "1h", "command": "echo xong"},
    "script": {
        "id": "sang",
        "name": "Sáng",
        "cron": "0 7 * * *",
        "script": 'print("x")',
        "then_prompt": "xem",
    },
}
# Names no variable of any machine's, so no bot is ever started for it.
TELEGRAM = {"token_env": "A_BOT_TOKEN_NOBODY_SET", "chat_id": 7}
# Texts of the right shape for a path that no path is written as: each fails somewhere
# past the reading of its shape, where the text is followed to a place on the disk.
ODD_PATHS: dict[str, str] = {
    "the home of nobody": "~nosuchuser-zz/x",
    "a lone tilde": "~",
    "spaces only": "   ",
    "a text holding a NUL": "a\x00b",
    "5000 characters of folders": "thu-muc/" * 625,
    "5000 characters in one name": "a" * 5000,
    "300 characters in one name": "a" * 300,
}


def profiles() -> Iterator[tuple[str, dict[str, Any]]]:
    """Every profile holding one value of one shape in one place, and which."""
    for shape, value in SHAPES.items():
        for key in sorted(PROFILE_KEYS):
            yield f"{key} as {shape}", {key: value}
        for kind, row in ROWS.items():
            for field in sorted(SCHEDULE_KEYS):
                where = f"{field} of a {kind} schedule as {shape}"
                yield where, {"schedules": [row | {field: value}]}
        for field in sorted(TELEGRAM_KEYS):
            yield f"{field} of telegram as {shape}", {"telegram": TELEGRAM | {field: value}}
    # Alone and in a list: which of the two a key takes is the code's to say, not this
    # walk's, and the empty text is among the shapes above.
    for odd, text in ODD_PATHS.items():
        for key in PATH_KEYS:
            yield f"{key} as {odd}", {key: text}
            yield f"{key} as a list of {odd}", {key: [text]}


def requests() -> Iterator[Any]:
    """Every request to the two edit routes that holds one such value, down to the body."""
    for where, profile in profiles():
        yield pytest.param("PATCH", EDIT, {"profile": profile}, id=f"edit: {where}")
        created = {"agent_id": NEW, "profile": profile}
        yield pytest.param("POST", CREATE, created, id=f"create: {where}")
    for shape, value in SHAPES.items():
        yield pytest.param("PATCH", EDIT, {"profile": value}, id=f"edit: profile as {shape}")
        yield pytest.param("PATCH", EDIT, value, id=f"edit: the body as {shape}")
        created = {"agent_id": NEW, "profile": value}
        yield pytest.param("POST", CREATE, created, id=f"create: profile as {shape}")
        named = {"agent_id": value, "profile": {}}
        yield pytest.param("POST", CREATE, named, id=f"create: agent_id as {shape}")
        yield pytest.param("POST", CREATE, value, id=f"create: the body as {shape}")


# --- the parser, which a start reads every file with ---


@pytest.fixture(scope="module")
def agent_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("agent")


@pytest.mark.parametrize("raw", [pytest.param(raw, id=where) for where, raw in profiles()])
def test_the_parser_reads_a_profile_that_can_be_listed_or_says_what_is_wrong(agent_dir, raw):
    base = Settings(home=agent_dir / "home", routes=(Route("scripted", "m"),))

    try:
        profile = parse_profile(EDITED, agent_dir, raw, base)
    except ValueError:
        # A bad profile is told by this error and no other: whoever reads a file or takes
        # an edit says what is wrong by catching it, and catches nothing else.
        return

    # What it read is what an agent is listed by, and what its turns are put together from.
    assert profile.to_dict()["id"] == EDITED
    assert all(isinstance(name, str) for name in profile.persona_files)


# --- the routes, which hand an edit to the same parser ---


@pytest.fixture(scope="module")
def served(tmp_path_factory) -> Iterator[tuple[TestClient, Runtime, Path]]:
    """One crew for the whole walk. A server error is an answer here, not an exception, so
    a pair that met one fails by its status and under its own name."""
    home = tmp_path_factory.mktemp("crew") / "home"
    home.mkdir()
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    app = create_app(runtime, schedule=False)
    with TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as client:
        yield client, runtime, home


def manifests(home: Path) -> dict[Path, bytes]:
    """Every agent's file as it stands on the disk, the master's among them."""
    files = [home / "agent.yaml", *home.glob("agents/*/agent.yaml")]
    return {file: file.read_bytes() for file in files if file.is_file()}


@pytest.fixture
def crew(served) -> tuple[TestClient, Runtime, Path]:
    """The crew as nobody edited it: the master, and one agent whose file says nothing.
    What the pair before left is taken away first, so no pair is answered for another's."""
    client, runtime, home = served
    untouched = set(runtime.agents) == {DEFAULT_AGENT_ID, EDITED}
    if not (untouched and read_now(home / "agents" / EDITED / "agent.yaml") == {}):
        for agent_id in sorted(set(runtime.agents) - {DEFAULT_AGENT_ID}):
            assert client.delete(f"/api/agents/{agent_id}").status_code == 200
        made = client.post(CREATE, json={"agent_id": EDITED, "profile": {}})
        assert made.status_code == 201
    return served


@pytest.mark.parametrize(("verb", "address", "body"), list(requests()))
def test_an_edit_is_taken_or_refused_with_422_and_a_refused_one_changes_nothing(
    crew, verb, address, body
):
    client, runtime, home = crew
    files = manifests(home)
    running = {agent_id: deps.agent for agent_id, deps in runtime.agents.items()}

    answer = client.request(verb, address, json=body)

    assert answer.status_code in (TAKEN[verb], 422), answer.text
    if answer.status_code == 422:
        assert manifests(home) == files
        assert {agent_id: deps.agent for agent_id, deps in runtime.agents.items()} == running
        return
    # Taken: the file it wrote is one the next start reads, and the crew can be listed.
    saved = load_yaml_profiles(runtime.settings)
    assert [profile.id for profile in saved]
    assert client.get("/api/agents").status_code == 200
    # What a job does goes to the model or to a shell as it stands, so it is a text. A job
    # holding anything else fails when its time comes, and holds up the jobs due beside it.
    doing = [
        schedule.script or schedule.command or schedule.prompt
        for profile in saved
        for schedule in profile.schedules
        if not schedule.consolidate
    ]
    assert all(isinstance(action, str) for action in doing), doing


# --- the shapes that crashed, and the words each is refused in ---

NO_NAMES = "persona_files must be a list of names"
NO_ROWS = "schedules must be a list of mappings"
NO_SKILLS = "schedule sang: skills must be a list of names"
# Two texts no place is reached by, and the words each is refused in: the text, cut where
# it is long, and what the library or the disk itself says of it.
NOBODY, LONG = "~nosuchuser-zz/x", "a" * 300


def nobody_home() -> str:
    try:
        Path(NOBODY).expanduser()
    except RuntimeError as unknown:
        return f"{NOBODY!r} cannot be followed: {unknown}"
    raise AssertionError(f"somebody on this machine is called {NOBODY[1:-2]}")


NO_HOME = nobody_home()
TOO_LONG = f"{LONG[:80] + '…'!r} cannot be followed: {os.strerror(errno.ENAMETOOLONG)}"
# What an edit was answered 500 for, and a reading of a hand-written file as well.
CRASHED = [
    pytest.param({"persona_files": [5]}, NO_NAMES, id="a persona that is a number"),
    pytest.param({"persona_files": [None]}, NO_NAMES, id="a persona that is null"),
    pytest.param({"persona_files": [{"k": "v"}]}, NO_NAMES, id="a persona that is a mapping"),
    pytest.param({"persona_files": [["SOUL.md"]]}, NO_NAMES, id="a persona that is a list"),
    # One entry that is no name spoils the list, wherever it stands in it.
    pytest.param({"persona_files": ["SOUL.md", 5]}, NO_NAMES, id="a number after a persona"),
    pytest.param({"schedules": [ROWS["prompt"], 5]}, NO_ROWS, id="a number after a row"),
    pytest.param({"schedules": 5}, NO_ROWS, id="schedules that are a number"),
    pytest.param({"schedules": True}, NO_ROWS, id="schedules that are a switch"),
    pytest.param({"schedules": [5]}, NO_ROWS, id="a row that is a number"),
    pytest.param({"schedules": [None]}, NO_ROWS, id="a row that is null"),
    pytest.param({"schedules": [""]}, NO_ROWS, id="a row that is an empty text"),
    # Every entry is a field a row may hold, so the check for unknown fields let it by.
    pytest.param({"schedules": [["id", "cron"]]}, NO_ROWS, id="a row that is a list of fields"),
    pytest.param({"schedules": [ROWS["prompt"] | {"skills": 5}]}, NO_SKILLS, id="skills: 5"),
    pytest.param({"schedules": [ROWS["prompt"] | {"skills": True}]}, NO_SKILLS, id="skills: on"),
    pytest.param({"workspace": NOBODY}, f"workspace {NO_HOME}", id="a workspace at nobody's"),
    pytest.param({"skills_dirs": [NOBODY]}, f"skills_dirs {NO_HOME}", id="skills at nobody's"),
    # Saved, it was looked up by whoever listed the agents next, and failed them all.
    pytest.param({"persona_files": [LONG]}, f"persona_files {TOO_LONG}", id="a long persona"),
]
# What only a file can hold: the edit routes take neither unless it is a list.
CRASHED_IN_A_FILE = [
    pytest.param({"persona_files": 5}, NO_NAMES, id="personas that are a number"),
    pytest.param({"skills_dirs": True}, "skills_dirs must be a list of folders", id="folders: on"),
]


@pytest.mark.parametrize(("profile", "told"), CRASHED)
def test_an_edit_of_a_shape_that_crashed_is_refused_by_the_name_of_its_key(crew, profile, told):
    client, _, home = crew
    files = manifests(home)

    edited = client.patch(EDIT, json={"profile": profile})
    created = client.post(CREATE, json={"agent_id": NEW, "profile": profile})
    master = client.patch(f"/api/agents/{DEFAULT_AGENT_ID}", json={"profile": profile})

    assert [(answer.status_code, answer.json()["detail"]) for answer in (edited, created)] == [
        (422, f"agent {EDITED}: {told}"),
        (422, f"agent {NEW}: {told}"),
    ]
    # The master's file is the home's own, and is read by the same parser.
    assert (master.status_code, master.json()["detail"]) == (422, f"agent default: {told}")
    assert manifests(home) == files


@pytest.mark.parametrize(("raw", "told"), [*CRASHED, *CRASHED_IN_A_FILE])
def test_a_file_of_a_shape_that_crashed_is_refused_when_the_agents_are_read_again(
    tmp_path, raw, told
):
    """A folder copied in by hand is read by `POST /api/agents/reload`, which says which file
    is the bad one. It can only say so of a file the parser refused as a bad profile."""
    home = tmp_path / "home"
    folder = home / "agents" / "tay"
    folder.mkdir(parents=True)
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    app = create_app(runtime, schedule=False)
    (folder / "agent.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")

    with TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as client:
        answer = client.post("/api/agents/reload")

    assert (answer.status_code, answer.json()["detail"]) == (422, f"agent tay: {told}")
    assert set(runtime.agents) == {DEFAULT_AGENT_ID}


# --- a job that does no text, which an edit may not bring ---

NO_TEXTS = [5, True, ["chào"], {"k": "v"}]


@pytest.mark.parametrize("held", NO_TEXTS, ids=repr)
@pytest.mark.parametrize("action", ["prompt", "command"])
def test_an_edit_may_not_bring_a_job_that_does_no_text(crew, action, held):
    client, _, home = crew
    files = manifests(home)
    profile = {"schedules": [ROWS[action] | {action: held}]}

    edited = client.patch(EDIT, json={"profile": profile})
    created = client.post(CREATE, json={"agent_id": NEW, "profile": profile})

    told = f"schedule sang: {action} must be a non-empty string"
    assert [(answer.status_code, answer.json()["detail"]) for answer in (edited, created)] == [
        (422, f"agent {EDITED}: {told}"),
        (422, f"agent {NEW}: {told}"),
    ]
    assert manifests(home) == files


@pytest.mark.parametrize("action", ["prompt", "command"])
def test_a_job_the_file_already_holds_does_not_hold_up_a_save_about_something_else(
    tmp_path, action
):
    """A file written by hand may hold such a job, and the start takes it. The agent runs
    with it, so it is not the edit's: a save that leaves the row as it is goes through."""
    home = tmp_path / "home"
    folder = home / "agents" / "tay"
    folder.mkdir(parents=True)
    rows = [ROWS[action] | {action: 5}]
    (folder / "agent.yaml").write_text(yaml.safe_dump({"schedules": rows}), encoding="utf-8")
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    app = create_app(runtime, schedule=False)

    with TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as client:
        renamed = client.patch("/api/agents/tay", json={"profile": {"name": "Tay"}})
        resent = client.patch("/api/agents/tay", json={"profile": {"schedules": rows}})
        changed = [rows[0] | {"name": "Khác"}]
        moved = client.patch("/api/agents/tay", json={"profile": {"schedules": changed}})

    assert (renamed.status_code, resent.status_code) == (200, 200)
    # Changed, the row is the edit's, and is asked what any row an edit brings is.
    told = f"agent tay: schedule sang: {action} must be a non-empty string"
    assert (moved.status_code, moved.json()["detail"]) == (422, told)


# --- a file a hand changed under the crew that runs, and the edit that comes next ---


def changed_by_hand() -> Iterator[Any]:
    """Every file holding one such value, with an edit that takes the key out and one that
    is about something else."""
    for where, profile in profiles():
        (key,) = profile
        other = "name" if key == "description" else "description"
        yield pytest.param(profile, {key: None}, id=f"{where}, taken out")
        yield pytest.param(profile, {other: "khác"}, id=f"{where}, beside an edit of {other}")


@pytest.mark.parametrize(("written", "edit"), list(changed_by_hand()))
def test_an_edit_over_a_file_changed_by_hand_is_taken_or_refused_with_422(crew, written, edit):
    """The agent runs as it started; its file is what a person has since made of it. An edit
    is laid over the file, so every reader on the way of a save meets what the file holds
    now: a shape the start would refuse among them, and the start is not there to refuse."""
    client, runtime, home = crew
    file = home / "agents" / EDITED / "agent.yaml"
    file.write_text(yaml.safe_dump(written, allow_unicode=True), encoding="utf-8")
    files = manifests(home)
    running = {agent_id: deps.agent for agent_id, deps in runtime.agents.items()}

    answer = client.patch(EDIT, json={"profile": edit})

    assert answer.status_code in (200, 422), answer.text
    if answer.status_code == 422:
        assert manifests(home) == files
        assert {agent_id: deps.agent for agent_id, deps in runtime.agents.items()} == running
        return
    # Taken: the file it wrote is one the next start reads, and the crew can be listed.
    assert [profile.id for profile in load_yaml_profiles(runtime.settings)]
    assert client.get("/api/agents").status_code == 200
