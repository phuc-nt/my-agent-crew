"""What an agent's scripts have kept, as a person is shown it:
`GET /api/agents/<id>/script-store`.

A value gets there from a script that ended well and from nowhere else, so no verb on this
address writes one; the rows are put in here as a script's end puts them, and once by a
script a turn really ran. How a script keeps is in `test_script_store.py`; reading one value
whole and forgetting what is kept are in `test_api_script_store_edit.py`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import load_settings
from my_agent_crew.script import limits
from my_agent_crew.server import build_runtime, create_app
from my_agent_crew.server.routes_script_store import PREVIEW_CHARS
from my_agent_crew.server.runtime import Runtime
from tests.test_server_api import parse_sse

ADDRESS = "/api/agents/{agent}/script-store"
ROOM = 100_000
# The one schedule the coach declares, and what it is called.
DUE, DUE_NAME = "due", "Sách sắp đến hạn"
COACH = f"""\
name: Coach
routes: [fake:echo]
schedules:
  - id: {DUE}
    name: {DUE_NAME}
    cron: '0 7 * * *'
    prompt: kiểm sách
"""
# What a place nothing is known of is told as, beside what it is and whose.
GONE = {"title": None, "orphan": True}


@contextmanager
def serving(home: Path) -> Iterator[tuple[TestClient, Runtime]]:
    """A home of the master and a coach with one schedule, served as the web is."""
    coach = home / "agents" / "coach"
    coach.mkdir(parents=True)
    (coach / "agent.yaml").write_text(COACH)
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, runtime


@pytest.fixture
def house(tmp_path: Path):
    with serving(tmp_path) as served:
        yield served


@pytest.fixture
def crew(house):
    client, runtime = house
    return client, runtime.store.script_store


def shown(client: TestClient, agent: str = "default") -> list[dict]:
    answer = client.get(ADDRESS.format(agent=agent))
    assert answer.status_code == 200 and set(answer.json()) == {"limit_chars", "namespaces"}
    return answer.json()["namespaces"]


def place(client: TestClient, namespace: str, agent: str = "default") -> dict:
    """What one place is told as: all but what it holds."""
    [found] = [told for told in shown(client, agent) if told["namespace"] == namespace]
    return {name: said for name, said in found.items() if name not in ("chars", "entries")}


def test_an_agent_that_kept_nothing_is_shown_nothing(crew):
    client, _ = crew

    assert shown(client) == []


def test_each_place_is_shown_with_its_size_and_each_value_with_its_own(crew):
    client, table = crew
    # As a script's end writes them: the value's own letters, not their escapes.
    seen, told = '["HP3-12","HP3-13"]', '{"đã nhắc":true}'
    assert table.apply("default", "job:due", {"seen": seen, "a": "1"}, ROOM)
    assert table.apply("default", "conv:c1", {"told": told}, ROOM)

    places = shown(client)

    stamps = [entry.pop("updated_at") for place in places for entry in place["entries"]]
    # By place, then by key; a place's size is its keys and its values, as its limit counts.
    assert places == [
        {
            "namespace": "conv:c1",
            "kind": "conv",
            "ref": "c1",
            **GONE,
            "chars": len("told") + len(told),
            "entries": [{"key": "told", "preview": told, "chars": len(told)}],
        },
        {
            "namespace": "job:due",
            "kind": "job",
            "ref": "due",
            **GONE,
            "chars": len("seen") + len(seen) + len("a") + 1,
            "entries": [
                {"key": "a", "preview": "1", "chars": 1},
                {"key": "seen", "preview": seen, "chars": len(seen)},
            ],
        },
    ]
    # When each was last written, as every other time the server tells: with its offset.
    written = [datetime.fromisoformat(stamp) for stamp in stamps]
    assert all(stamp.utcoffset() == timedelta(0) for stamp in written)
    assert stamps == [row.updated_at for row in table.kept_by("default")]


def test_a_long_value_is_shown_by_its_beginning_and_its_whole_length(crew):
    client, table = crew
    whole, long = json.dumps("x" * (PREVIEW_CHARS - 2)), json.dumps("y" * (PREVIEW_CHARS - 1))
    assert table.apply("default", "job:due", {"long": long, "whole": whole}, ROOM)

    entries = {entry["key"]: entry for entry in shown(client)[0]["entries"]}

    assert (entries["whole"]["preview"], entries["whole"]["chars"]) == (whole, PREVIEW_CHARS)
    # One character more, and it is cut where the other ended, with a mark that it was.
    assert entries["long"]["preview"] == long[:PREVIEW_CHARS] + "…"
    assert entries["long"]["chars"] == PREVIEW_CHARS + 1
    assert shown(client)[0]["chars"] == len("long") + len(long) + len("whole") + len(whole)


def test_an_agent_is_shown_only_what_its_own_scripts_kept(crew):
    client, table = crew
    assert table.apply("default", "job:due", {"n": "1"}, ROOM)
    assert table.apply("coach", "job:due", {"n": "2"}, ROOM)

    ours, theirs = shown(client), shown(client, "coach")

    assert [entry["preview"] for entry in ours[0]["entries"]] == ["1"]
    assert [entry["preview"] for entry in theirs[0]["entries"]] == ["2"]


def test_an_agent_nobody_knows_is_not_found(crew):
    client, _ = crew

    answer = client.get(ADDRESS.format(agent="nobody"))

    assert (answer.status_code, answer.json()) == (404, {"detail": "agent not found"})


def test_the_most_a_place_may_hold_is_told_once_beside_them(crew):
    client, table = crew

    before = client.get(ADDRESS.format(agent="default")).json()
    assert table.apply("default", "job:due", {"n": "1"}, ROOM)
    after = client.get(ADDRESS.format(agent="coach")).json()

    # The limit of each place, which a place's own size is measured against: the one a
    # script's `store` is held to, whoever the agent is and whatever it kept.
    assert before == {"limit_chars": limits.MAX_STORE_TOTAL_CHARS, "namespaces": []}
    assert after["limit_chars"] == limits.MAX_STORE_TOTAL_CHARS == 262_144


def test_what_a_schedule_kept_is_told_by_the_schedules_name(crew):
    client, table = crew
    assert table.apply("coach", f"job:{DUE}", {"n": "1"}, ROOM)

    told = place(client, f"job:{DUE}", "coach")

    assert told == {
        "namespace": f"job:{DUE}",
        "kind": "job",
        "ref": DUE,
        "title": DUE_NAME,
        "orphan": False,
    }


def test_a_schedule_of_another_agents_names_nothing_of_this_ones(crew):
    client, table = crew
    # The coach declares `due`; the master, whose scripts kept this, never did.
    assert table.apply("default", f"job:{DUE}", {"n": "1"}, ROOM)

    assert place(client, f"job:{DUE}") == {
        "namespace": f"job:{DUE}",
        "kind": "job",
        "ref": DUE,
        **GONE,
    }


def test_a_schedule_made_in_a_chat_names_what_its_turns_kept_until_it_is_removed(house):
    client, runtime = house
    row = {"agent_id": "default", "name": "Nhắc uống nước", "cron": "0 9 * * *", "every": None}
    made = runtime.store.created_schedules.add(
        {**row, "prompt": "p", "skills": [], "created_by_conversation": "c1"}, cap=20
    )
    namespace = f"job:{made.id}"
    assert runtime.store.script_store.apply("default", namespace, {"n": "1"}, ROOM)

    while_there = place(client, namespace)
    assert client.delete(f"/api/jobs/default/{made.id}").status_code == 204
    once_gone = place(client, namespace)

    known = {"namespace": namespace, "kind": "job", "ref": made.id}
    assert while_there == {**known, "title": "Nhắc uống nước", "orphan": False}
    # What it kept outlives it, with nothing left to read it: told as left behind.
    assert once_gone == {**known, **GONE}


def test_what_a_conversation_kept_is_told_by_the_conversations_title(house):
    client, runtime = house
    conv = client.post("/api/conversations", json={"title": "Sách tháng mười"}).json()["id"]
    assert runtime.store.script_store.apply("default", f"conv:{conv}", {"n": "1"}, ROOM)
    assert runtime.store.script_store.apply("default", "conv:gone", {"n": "1"}, ROOM)

    there, gone = place(client, f"conv:{conv}"), place(client, "conv:gone")

    assert there == {
        "namespace": f"conv:{conv}",
        "kind": "conv",
        "ref": conv,
        "title": "Sách tháng mười",
        "orphan": False,
    }
    assert gone == {"namespace": "conv:gone", "kind": "conv", "ref": "gone", **GONE}


def test_a_title_of_nothing_but_space_is_told_as_none_and_its_place_is_not_left_behind(house):
    client, runtime = house
    conv = runtime.store.create(title=" \n", agent_id="default")
    assert runtime.store.script_store.apply("default", f"conv:{conv.id}", {"n": "1"}, ROOM)

    told = place(client, f"conv:{conv.id}")

    assert (told["title"], told["orphan"]) == (None, False)


@pytest.mark.parametrize("namespace", ["misc", "jobs:due", "job", "conv", "Job:due", " conv:c1"])
def test_a_place_of_neither_kind_is_told_as_it_is_stored(crew, namespace):
    client, table = crew
    assert table.apply("coach", namespace, {"n": "1"}, ROOM)

    told = place(client, namespace, "coach")

    # Nothing it could be left behind by: no schedule and no conversation is asked after.
    assert told == {
        "namespace": namespace,
        "kind": "other",
        "ref": namespace,
        "title": None,
        "orphan": False,
    }


@pytest.mark.parametrize("verb", ["post", "put", "patch"])
def test_no_verb_on_the_address_writes(crew, verb):
    client, table = crew
    assert table.apply("default", "job:due", {"n": "1"}, ROOM)

    answer = getattr(client, verb)(ADDRESS.format(agent="default"))
    one = getattr(client, verb)(ADDRESS.format(agent="default") + "/job:due/n")

    assert answer.status_code == 405
    assert one.status_code in (404, 405)
    assert [(row.namespace, row.key, row.text) for row in table.kept_by("default")] == [
        ("job:due", "n", "1")
    ]


def test_what_a_turns_script_kept_is_shown_and_goes_with_its_conversation(crew):
    client, table = crew
    conv = client.post("/api/conversations", json={}).json()["id"]
    script = json.dumps({"script": 'store("told", ["HP3-12"])\nprint("xong")'})
    with client.stream(
        "POST", f"/api/conversations/{conv}/messages", json={"text": f"/tool tool_script {script}"}
    ) as answer:
        events = parse_sse("".join(answer.iter_text()))
    result = next(event for event in events if event["type"] == "tool_result")
    assert (result["ok"], result["output"]) == (True, "xong")

    places = shown(client)

    assert [place["namespace"] for place in places] == [f"conv:{conv}"]
    assert [(entry["key"], entry["preview"]) for entry in places[0]["entries"]] == [
        ("told", '["HP3-12"]')
    ]

    deleted = client.delete(f"/api/conversations/{conv}")

    assert (deleted.status_code, deleted.content) == (204, b"")
    assert shown(client) == [] and table.kept_by("default") == []
