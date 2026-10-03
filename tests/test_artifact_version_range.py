"""A version number the database cannot hold is a version that is not there. SQLite keeps an
INTEGER in 64 bits and the driver refuses a Python int past them, so such a number used to fail
inside the driver: a 500 over REST and "the tool crashed" for an agent. Every way to name a
version reaches the store through one read, and each is held here to the answer a version that
is gone gets: 404 with the newest number, a sentence the agent can act on, a conflict for a save."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.server import create_app
from my_agent_crew.store.artifact_models import VersionGone
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import ARTIFACT_VERSION_GONE
from tests.canvas_helpers import PLAN, agents_canvas, call, persons_canvas, turn

# One past what SQLite keeps in either direction, and numbers far beyond.
TOO_BIG = 2**63
TOO_SMALL = -(2**63) - 1
BEYOND = [TOO_BIG, TOO_BIG + 1, 2**200, TOO_SMALL, -(2**200)]
# The last numbers the database does hold: asked for, they are just as absent.
AT_THE_EDGE = [2**63 - 1, -(2**63)]
FIRST, SECOND = "<p>one</p>", "<p>two</p>"

READS = [
    pytest.param("versions/{n}", TOO_BIG, id="one-version"),
    pytest.param("versions/{n}", 2**200, id="one-version-far-beyond"),
    pytest.param("versions/{n}", TOO_SMALL, id="one-version-below"),
    pytest.param("raw?version={n}", TOO_BIG, id="raw"),
    pytest.param("render?version={n}", TOO_BIG, id="page"),
]


@pytest.fixture
def client(deps_factory):
    """A failure no route turned into an answer comes back as the 500 a browser would see,
    instead of as an exception raised inside the test."""
    app = create_app(deps_factory(), schedule=False)
    with TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as client:
        yield client


def _page_at_version_two(store: Store) -> str:
    """The coach's html canvas, which every route reads, at version 2."""
    art = agents_canvas(store, "coach", FIRST, kind="html")
    store.artifacts.write(art, SECOND, "agent:coach", "")
    return art


@pytest.mark.parametrize("number", [*BEYOND, *AT_THE_EDGE])
def test_a_version_number_at_or_beyond_the_64_bit_edge_is_gone_and_names_the_newest(
    store: Store, number: int
):
    art = _page_at_version_two(store)
    with pytest.raises(VersionGone) as gone:
        store.artifacts.version(art, number)
    assert (gone.value.version, gone.value.head_version) == (number, 2)


def test_a_canvas_that_is_not_there_stays_a_missing_canvas_whatever_version_is_asked(store: Store):
    with pytest.raises(KeyError) as missing:
        store.artifacts.version("nope", TOO_BIG)
    assert not isinstance(missing.value, VersionGone)
    assert missing.value.args == ("nope",)


@pytest.mark.parametrize(("route", "number"), READS)
def test_a_read_of_a_version_too_large_to_exist_is_404_with_the_newest_number(
    client, store: Store, route: str, number: int
):
    art = _page_at_version_two(store)
    response = client.get(f"/api/artifacts/{art}/" + route.format(n=number))
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": {"head_version": 2}}


def test_a_restore_of_a_version_too_large_to_exist_is_404_and_writes_nothing(client, store: Store):
    art = _page_at_version_two(store)
    response = client.post(f"/api/artifacts/{art}/restore", json={"version": TOO_BIG})
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": {"head_version": 2}}
    assert [version.version for version in store.artifacts.versions(art)] == [1, 2]


def test_a_save_on_a_version_too_large_to_exist_is_a_conflict_and_writes_nothing(
    client, store: Store
):
    art = _page_at_version_two(store)
    body = {"content": "<p>mine</p>", "base_version": TOO_BIG}
    response = client.put(f"/api/artifacts/{art}", json=body)
    assert response.status_code == 409, response.text
    newest = {"head_version": 2, "content": SECOND, "author": "agent:coach"}
    assert response.json() == {"detail": newest}
    assert store.artifacts.head(art).content == SECOND


@pytest.mark.parametrize("version", [TOO_BIG, str(2**200)])
async def test_the_tool_reads_a_version_too_large_to_exist_as_one_that_is_gone(
    store: Store, version
):
    """A model may send the number as a string, which reads the same."""
    conv = turn(store)
    art = persons_canvas(store, PLAN, conv.id)
    result = await call(store, "artifact_read", {"id": art, "version": version})
    gone = ARTIFACT_VERSION_GONE.format(version=int(version), head=1, id=art)
    assert result.output == TOOL_FAILED.format(error=gone)
    assert not result.ok
