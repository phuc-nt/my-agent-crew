"""Reading one kept value whole, and forgetting what an agent's scripts kept:
`GET /api/agents/<id>/script-store/value` and `DELETE /api/agents/<id>/script-store`.

What a script keeps can be wrong for good. A list of what was already told that holds what
never was keeps it from ever being told, and no later run of the script puts that right. So
the owner reads a value as it is kept and forgets it, one key or all of a place at a time,
and what an agent kept goes when the agent does. No verb writes a value in: that is still a
script's alone (`test_api_script_store.py`, where the listing is too).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.script import limits
from my_agent_crew.script.kept import LOAD, STORE
from my_agent_crew.script.store_session import Kept
from my_agent_crew.server import routes_agents_edit
from my_agent_crew.server.routes_script_store import PREVIEW_CHARS
from my_agent_crew.store.script_store import ScriptStore
from tests.test_api_script_store import ADDRESS, ROOM, serving, shown

ONE = ADDRESS + "/value"
NO_AGENT = (404, {"detail": "agent not found"})
NO_VALUE = (404, {"detail": "value not found"})
# Keys a script may write and an address must carry as they are.
ODD_KEYS = [
    "a&b=c",
    "đã nhắc",
    "a/b#c?d",
    "50%",
    "a b+c",
    "%2F",
    "_",
    "x" * limits.MAX_STORE_KEY_CHARS,
]


@pytest.fixture
def house(tmp_path: Path):
    with serving(tmp_path) as served:
        yield served


@pytest.fixture
def crew(house):
    client, runtime = house
    return client, runtime.store.script_store


def rows(table: ScriptStore, agent: str = "default") -> list[tuple[str, str, str]]:
    return [(row.namespace, row.key, row.text) for row in table.kept_by(agent)]


def answered(answer) -> tuple[int, dict]:
    return answer.status_code, answer.json()


def forget(client: TestClient, agent: str = "default", **named: str) -> tuple[int, dict]:
    return answered(client.delete(ADDRESS.format(agent=agent), params=named))


def read(client: TestClient, agent: str = "default", **named: str) -> tuple[int, dict]:
    return answered(client.get(ONE.format(agent=agent), params=named))


# --- one value, whole ---------------------------------------------------------------------


def test_a_value_is_read_whole_however_long_it_is(crew):
    client, table = crew
    long = json.dumps(["HP3-12"] * 7000, separators=(",", ":"))
    assert PREVIEW_CHARS < len(long) <= limits.MAX_STORE_VALUE_CHARS
    assert table.apply("default", "job:due", {"seen": long, "other": "1"}, ROOM * 10)

    status, told = read(client, namespace="job:due", key="seen")

    [listed] = [e for e in shown(client)[0]["entries"] if e["key"] == "seen"]
    assert status == 200
    # The text as it is kept, not the beginning the listing shows, and when it was written.
    assert told == {
        "namespace": "job:due",
        "key": "seen",
        "text": long,
        "chars": len(long),
        "updated_at": listed["updated_at"],
    }
    assert listed["preview"] != long and listed["chars"] == len(long)


@pytest.mark.parametrize("key", ODD_KEYS)
def test_a_key_is_named_as_the_script_wrote_it(crew, key):
    client, table = crew
    assert table.apply("default", "conv:c 1/&", {key: '"của nó"', key + "x": '"khác"'}, ROOM)

    status, told = read(client, namespace="conv:c 1/&", key=key)

    assert (status, told["key"], told["text"]) == (200, key, '"của nó"')


@pytest.mark.parametrize(
    "named",
    [
        {"namespace": "job:due", "key": "none"},
        {"namespace": "job:other", "key": "seen"},
        {"namespace": "job:du", "key": "seen"},
        {"namespace": "job:%", "key": "seen"},
        {"namespace": "job:due", "key": "see_"},
        {"namespace": "job:due", "key": ""},
        {"namespace": "job:due", "key": "theirs"},
    ],
)
def test_a_value_nobody_kept_there_is_not_found(crew, named):
    client, table = crew
    assert table.apply("default", "job:due", {"seen": "1"}, ROOM)
    # What another agent kept in a place of the same name is not this one's to read.
    assert table.apply("coach", "job:due", {"theirs": "2"}, ROOM)

    assert read(client, **named) == NO_VALUE


def test_a_value_of_an_agent_nobody_knows_is_not_found(crew):
    client, table = crew
    assert table.apply("nobody", "job:due", {"seen": "1"}, ROOM)

    assert read(client, "nobody", namespace="job:due", key="seen") == NO_AGENT


@pytest.mark.parametrize("named", [{}, {"namespace": "job:due"}, {"key": "seen"}])
def test_a_value_is_asked_for_by_its_place_and_its_key_both(crew, named):
    client, table = crew
    assert table.apply("default", "job:due", {"seen": "1"}, ROOM)

    status, _ = read(client, **named)

    assert status == 422


# --- forgetting ---------------------------------------------------------------------------


def test_one_key_is_forgotten_and_all_else_stays(crew):
    client, table = crew
    assert table.apply("default", "job:due", {"seen": "[1]", "kept": "2"}, ROOM)
    assert table.apply("default", "conv:c1", {"seen": "3"}, ROOM)

    answer = forget(client, namespace="job:due", key="seen")

    assert answer == (200, {"deleted": 1})
    assert rows(table) == [("conv:c1", "seen", "3"), ("job:due", "kept", "2")]
    # Gone for whoever looks next: the listing, the one value, and a script that loads it.
    assert [entry["key"] for entry in shown(client)[1]["entries"]] == ["kept"]
    assert read(client, namespace="job:due", key="seen") == NO_VALUE
    assert Kept(table, "default", "job:due").answer(LOAD, {"key": "seen"}) is None


def test_all_a_place_holds_is_forgotten_when_no_key_is_named(crew):
    client, table = crew
    assert table.apply("default", "job:due", {"seen": "[1]", "kept": "2", "more": "3"}, ROOM)
    assert table.apply("default", "job:due2", {"seen": "4"}, ROOM)
    assert table.apply("default", "conv:c1", {"seen": "5"}, ROOM)

    answer = forget(client, namespace="job:due")

    # A place is named whole: one that only begins the same is another place.
    assert answer == (200, {"deleted": 3})
    assert rows(table) == [("conv:c1", "seen", "5"), ("job:due2", "seen", "4")]
    assert [told["namespace"] for told in shown(client)] == ["conv:c1", "job:due2"]


@pytest.mark.parametrize("key", ODD_KEYS)
def test_a_key_is_forgotten_by_the_name_the_script_wrote(crew, key):
    client, table = crew
    assert table.apply("default", "job:due", {key: "1", key + "x": "2", "a": "3"}, ROOM)

    answer = forget(client, namespace="job:due", key=key)

    assert answer == (200, {"deleted": 1})
    assert sorted(rows(table)) == sorted([("job:due", "a", "3"), ("job:due", key + "x", "2")])


@pytest.mark.parametrize(
    "named",
    [
        {"namespace": "job:due", "key": "none"},
        {"namespace": "job:other"},
        {"namespace": "job:du"},
        {"namespace": "job:%"},
        {"namespace": "job:du_"},
        {"namespace": "job:due", "key": "%"},
        {"namespace": "job:due", "key": "see_"},
        # A key of no letters is a key nothing was kept under, never the whole place.
        {"namespace": "job:due", "key": ""},
        {"namespace": ""},
    ],
)
def test_forgetting_what_is_not_there_forgets_nothing_and_is_no_mistake(crew, named):
    client, table = crew
    assert table.apply("default", "job:due", {"seen": "1", "kept": "2"}, ROOM)

    answer = forget(client, **named)

    assert answer == (200, {"deleted": 0})
    assert rows(table) == [("job:due", "kept", "2"), ("job:due", "seen", "1")]


@pytest.mark.parametrize("named", [{"namespace": "job:due"}, {"namespace": "job:due", "key": "n"}])
def test_an_agent_forgets_only_what_its_own_scripts_kept(crew, named):
    client, table = crew
    assert table.apply("default", "job:due", {"n": "1"}, ROOM)
    assert table.apply("coach", "job:due", {"n": "2"}, ROOM)

    answer = forget(client, "coach", **named)

    assert answer == (200, {"deleted": 1})
    assert (rows(table), rows(table, "coach")) == ([("job:due", "n", "1")], [])


@pytest.mark.parametrize("named", [{"namespace": "job:due"}, {"namespace": "job:due", "key": "n"}])
def test_nothing_is_forgotten_for_an_agent_nobody_knows(crew, named):
    client, table = crew
    assert table.apply("nobody", "job:due", {"n": "1"}, ROOM)
    assert table.apply("default", "job:due", {"n": "2"}, ROOM)

    assert forget(client, "nobody", **named) == NO_AGENT
    assert (rows(table, "nobody"), rows(table)) == (
        [("job:due", "n", "1")],
        [("job:due", "n", "2")],
    )


@pytest.mark.parametrize("named", [{}, {"key": "n"}])
def test_forgetting_names_a_place_or_forgets_nothing(crew, named):
    client, table = crew
    assert table.apply("default", "job:due", {"n": "1"}, ROOM)
    assert table.apply("default", "conv:c1", {"n": "2"}, ROOM)

    status, _ = forget(client, **named)

    # No address forgets all an agent kept at once, by a parameter left out least of all.
    assert status == 422
    assert rows(table) == [("conv:c1", "n", "2"), ("job:due", "n", "1")]


# One place and one key, then one of the two named again: with another name, with the same
# name, and with no key at all, where a forgetting would take a whole place.
TWICE = [
    pytest.param("namespace", [("namespace", "job:due"), ("key", "n"), ("namespace", "conv:c1")]),
    pytest.param("namespace", [("namespace", "job:due"), ("key", "n"), ("namespace", "job:due")]),
    pytest.param("namespace", [("namespace", "job:due"), ("namespace", "conv:c1")]),
    pytest.param("key", [("namespace", "job:due"), ("key", "n"), ("key", "m")]),
    pytest.param("key", [("namespace", "job:due"), ("key", "n"), ("key", "n")]),
    pytest.param("key", [("namespace", "job:due"), ("key", ""), ("key", "n")]),
]


@pytest.mark.parametrize(("twice", "named"), TWICE)
def test_a_place_or_a_key_named_twice_is_refused_and_nothing_is_read_or_forgotten(
    crew, twice, named
):
    """Only one of the two would be gone by, and which is the library's to say. A forgetting
    that goes by a guess forgets what the person did not mean, and it cannot be taken back."""
    client, table = crew
    assert table.apply("default", "job:due", {"n": "1", "m": "2"}, ROOM)
    assert table.apply("default", "conv:c1", {"n": "3"}, ROOM)
    kept = rows(table)

    wanted = answered(client.get(ONE.format(agent="default"), params=named))
    forgotten = answered(client.delete(ADDRESS.format(agent="default"), params=named))

    refused = (422, {"detail": f"{twice} is named more than once"})
    assert (wanted, forgotten) == (refused, refused)
    assert rows(table) == kept


def test_what_was_forgotten_stays_so_when_the_next_script_is_refused_what_it_wrote(crew):
    client, table = crew
    assert table.apply("default", "job:due", {"seen": "[1]", "kept": "2"}, ROOM)

    assert forget(client, namespace="job:due", key="seen") == (200, {"deleted": 1})
    # A script ending with more than its place may hold has what it wrote undone: that only.
    assert not table.apply("default", "job:due", {"big": json.dumps("x" * 50)}, 20)

    assert rows(table) == [("job:due", "kept", "2")]


# --- a script running meanwhile ------------------------------------------------------------


def test_a_script_that_had_looked_writes_back_only_what_it_wrote_itself(crew):
    client, table = crew
    assert table.apply("default", "job:due", {"seen": "[1]", "read": "7", "kept": "2"}, ROOM)
    script = Kept(table, "default", "job:due")
    assert script.answer(LOAD, {"key": "read"}) == "7"  # it has looked: this is its view

    assert forget(client, namespace="job:due") == (200, {"deleted": 3})
    # It goes by what it saw to its end, and what it wrote is told as kept.
    assert script.answer(LOAD, {"key": "seen"}) == "[1]"
    assert script.answer(STORE, {"key": "seen", "value": [1, 2]}) is None
    assert script.commit() is None

    # Its own key is there as it wrote it. What it only read stays forgotten.
    assert rows(table) == [("job:due", "seen", "[1,2]")]


def test_a_script_that_had_not_looked_finds_its_place_as_it_was_left(crew):
    client, table = crew
    assert table.apply("default", "job:due", {"seen": "[1]", "kept": "2"}, ROOM)
    script = Kept(table, "default", "job:due")

    assert forget(client, namespace="job:due", key="seen") == (200, {"deleted": 1})

    assert script.answer(LOAD, {"key": "seen"}) is None
    assert script.answer(LOAD, {"key": "kept"}) == "2"
    assert script.answer(STORE, {"key": "new", "value": 3}) is None
    assert script.commit() is None
    assert rows(table) == [("job:due", "kept", "2"), ("job:due", "new", "3")]


def test_a_script_that_drops_a_key_already_forgotten_ends_as_well_as_ever(crew):
    client, table = crew
    assert table.apply("default", "job:due", {"seen": "[1]", "kept": "2"}, ROOM)
    script = Kept(table, "default", "job:due")
    assert script.answer(LOAD, {"key": "seen"}) == "[1]"

    assert forget(client, namespace="job:due", key="seen") == (200, {"deleted": 1})
    assert script.answer(STORE, {"key": "seen", "value": None}) is None

    assert script.commit() is None
    assert rows(table) == [("job:due", "kept", "2")]


# --- with its agent ------------------------------------------------------------------------


def made(client: TestClient, agent_id: str, **profile) -> None:
    created = client.post("/api/agents", json={"agent_id": agent_id, "profile": profile})
    assert created.status_code == 201


def test_what_an_agent_kept_goes_when_the_agent_is_removed(crew):
    client, table = crew
    made(client, "coder")
    assert table.apply("coder", "job:due", {"seen": "[1]"}, ROOM)
    assert table.apply("coder", "conv:c1", {"told": "2"}, ROOM)
    assert table.apply("default", "job:due", {"seen": "[9]"}, ROOM)
    assert table.apply("coach", "conv:c1", {"told": "8"}, ROOM)

    removed = client.delete("/api/agents/coder")

    assert removed.status_code == 200
    assert rows(table, "coder") == []
    assert rows(table) == [("job:due", "seen", "[9]")]
    assert rows(table, "coach") == [("conv:c1", "told", "8")]
    # An agent later given the same id begins with nothing kept: it is another agent.
    made(client, "coder")
    assert shown(client, "coder") == []


def test_an_agent_that_could_not_be_removed_keeps_what_it_kept(crew, monkeypatch):
    client, table = crew
    made(client, "coder")
    made(client, "lead", delegates=["coder"])
    assert table.apply("coder", "job:due", {"seen": "[1]"}, ROOM)
    assert table.apply("default", "job:due", {"seen": "[9]"}, ROOM)

    in_use = client.delete("/api/agents/coder")
    master = client.delete("/api/agents/default")

    assert (in_use.status_code, master.status_code) == (409, 409)
    assert rows(table, "coder") == [("job:due", "seen", "[1]")]
    assert rows(table) == [("job:due", "seen", "[9]")]

    def stuck(home: Path, agent_id: str) -> Path:
        raise OSError("thư mục đang bị giữ")

    assert table.apply("lead", "conv:c1", {"told": "3"}, ROOM)
    monkeypatch.setattr(routes_agents_edit, "trash_agent", stuck)
    assert client.delete("/api/agents/lead").status_code == 409
    # Its folder is where it was and it is still of the crew: so is what it kept.
    assert rows(table, "lead") == [("conv:c1", "told", "3")]
    assert client.get("/api/agents/lead").status_code == 200
