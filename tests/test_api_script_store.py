"""What an agent's scripts have kept, as a person is shown it:
`GET /api/agents/<id>/script-store`.

Reading only. A value gets there from a script that ended well and from nowhere else, so no
verb on this address writes one; the rows are put in here as a script's end puts them, and
once by a script a turn really ran. How a script keeps is in `test_script_store.py`.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import load_settings
from my_agent_crew.server import build_runtime, create_app
from my_agent_crew.server.routes_script_store import PREVIEW_CHARS
from tests.test_server_api import parse_sse

ADDRESS = "/api/agents/{agent}/script-store"
ROOM = 100_000


@pytest.fixture
def crew(tmp_path: Path):
    coach = tmp_path / "agents" / "coach"
    coach.mkdir(parents=True)
    (coach / "agent.yaml").write_text("name: Coach\nroutes: [fake:echo]\n")
    env = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, runtime.deps_for("default").store.script_store


def shown(client: TestClient, agent: str = "default") -> list[dict]:
    answer = client.get(ADDRESS.format(agent=agent))
    assert answer.status_code == 200 and list(answer.json()) == ["namespaces"]
    return answer.json()["namespaces"]


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
            "chars": len("told") + len(told),
            "entries": [{"key": "told", "preview": told, "chars": len(told)}],
        },
        {
            "namespace": "job:due",
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


@pytest.mark.parametrize("verb", ["post", "put", "patch", "delete"])
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
