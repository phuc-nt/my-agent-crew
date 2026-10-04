"""Canvas storage use over REST, as the library shows it: how many canvases there are, the bytes
they keep across every version, each canvas's own share, and the ceiling they all fit under."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.artifacts.kinds import STORAGE_CAP
from my_agent_crew.server import create_app
from my_agent_crew.server.artifact_errors import NOT_FOUND
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store
from tests.canvas_helpers import PNG, agents_canvas

COACH = "agent:coach"
USAGE = "/api/artifacts/usage"


@pytest.fixture
def client(deps_factory):
    app = create_app(deps_factory(), schedule=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


def test_usage_adds_up_every_version_of_every_canvas(client, store: Store):
    """An old version keeps its room, so a canvas weighs what all its versions do; and a
    picture's bytes count beside the text's."""
    plan = agents_canvas(store, "coach", "# a")
    store.artifacts.write(plan, "# bơi", COACH, "")  # six bytes in five characters
    logo = store.artifacts.create("Logo", "image", "", USER, "", data=PNG).id
    assert len(PNG) == 40
    response = client.get(USAGE)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "count": 2,
        "bytes": 49,
        "cap": STORAGE_CAP,
        "by_artifact": {plan: 9, logo: 40},
    }


def test_a_deleted_canvas_gives_its_room_back(client, store: Store):
    gone, kept = agents_canvas(store, "coach", "# a"), agents_canvas(store, "coach", "# bơi")
    assert client.get(USAGE).json()["by_artifact"] == {gone: 3, kept: 6}
    assert client.delete(f"/api/artifacts/{gone}").status_code == 204
    assert client.get(USAGE).json() == {
        "count": 1,
        "bytes": 6,
        "cap": STORAGE_CAP,
        "by_artifact": {kept: 6},
    }


def test_usage_with_no_canvas_is_nothing_under_the_same_ceiling(client):
    response = client.get(USAGE)
    assert response.status_code == 200, response.text
    assert response.json() == {"count": 0, "bytes": 0, "cap": STORAGE_CAP, "by_artifact": {}}


def test_usage_is_not_read_as_the_id_of_a_canvas(client, store: Store):
    """`/artifacts/usage` fits `/artifacts/{artifact_id}` too, and the route declared first
    answers: behind the read of one canvas it would be a canvas nobody has, a 404. Only that
    one word is taken, and no canvas's id is a word."""
    art = agents_canvas(store, "coach", "# a")
    assert (client.get(USAGE).status_code, sorted(client.get(USAGE).json())) == (
        200,
        ["by_artifact", "bytes", "cap", "count"],
    )
    other = client.get("/api/artifacts/usages")
    assert (other.status_code, other.json()["detail"]) == (404, NOT_FOUND)
    assert client.get(f"/api/artifacts/{art}").json()["id"] == art


def test_usage_counts_the_canvases_a_list_is_too_short_to_return(client, store: Store):
    """A list stops at 200 canvases; the count is how the library knows there are more."""
    for _ in range(201):
        agents_canvas(store, "coach", "# a")
    assert len(client.get("/api/artifacts?limit=200").json()) == 200
    usage = client.get(USAGE).json()
    assert (usage["count"], usage["bytes"], len(usage["by_artifact"])) == (201, 603, 201)
