"""Half a character is text no canvas can keep. A lone surrogate, the half of an emoji that a
client or a model can send inside JSON, has no UTF-8 form, so it used to fail inside the
driver: a 500 over REST and "the tool crashed" for an agent. Every way to write a canvas is held
to one answer instead: a refusal that says which part to mend, and nothing written."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.artifacts.kinds import LANGUAGE_MAX, UnstorableText
from my_agent_crew.server import create_app
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.artifacts import ArtifactStore
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import (
    ARTIFACT_BAD_LANGUAGE,
    ARTIFACT_CONTENT_UNSTORABLE,
    ARTIFACT_EDIT_NO_MATCH,
    ARTIFACT_TITLE_UNSTORABLE,
)
from tests.canvas_helpers import call, created, lock_is_free, turn

# The first half of the runner emoji, alone, and the whole of it: one character that UTF-8
# writes in four bytes and JSON writes as the two escapes `🏃`.
HALF = "\ud83c"
RUNNER = "\U0001f3c3"
TEXT = 'say "hello"\nbye\n'
CONTENT, TITLE = ARTIFACT_CONTENT_UNSTORABLE, ARTIFACT_TITLE_UNSTORABLE

# Each way the store takes text, as it is called with a canvas already there.
STORE_WRITES: list[Any] = [
    pytest.param(
        lambda arts, art: arts.create("Plan", "markdown", "", USER, "", f"a{HALF}"),
        CONTENT,
        id="create-content",
    ),
    pytest.param(
        lambda arts, art: arts.create(f"Plan{HALF}", "markdown", "", USER, "", "a"),
        TITLE,
        id="create-title",
    ),
    pytest.param(
        lambda arts, art: arts.write(art, f"b{HALF}", USER, "", base_version=1),
        CONTENT,
        id="save-content",
    ),
    pytest.param(
        lambda arts, art: arts.write(art, "b", USER, "", title=f"Plan{HALF}"),
        TITLE,
        id="save-title",
    ),
    pytest.param(
        lambda arts, art: arts.apply(art, lambda head: f"b{HALF}", USER, ""),
        CONTENT,
        id="apply-content",
    ),
    pytest.param(lambda arts, art: arts.rename(art, f"Plan{HALF}"), TITLE, id="rename"),
]
REST_WRITES = [
    pytest.param(
        "POST",
        "/api/artifacts",
        {"title": "Plan", "kind": "markdown", "content": f"a{HALF}"},
        CONTENT,
        id="create-content",
    ),
    pytest.param(
        "POST",
        "/api/artifacts",
        {"title": f"Plan{HALF}", "kind": "markdown", "content": "a"},
        TITLE,
        id="create-title",
    ),
    pytest.param(
        "PUT",
        "/api/artifacts/{art}",
        {"content": f"b{HALF}", "base_version": 1},
        CONTENT,
        id="save-content",
    ),
    pytest.param("PATCH", "/api/artifacts/{art}", {"title": f"Plan{HALF}"}, TITLE, id="rename"),
]
# The `old` that matches TEXT without its curly quotes read as plain ones.
LOOSE = "say “hello”"
CREATE = {"title": "Mới", "kind": "markdown"}
TOOL_WRITES = [
    pytest.param(
        "artifact_create", {**CREATE, "content": f"a{HALF}"}, CONTENT, id="create-content"
    ),
    pytest.param(
        "artifact_create",
        {**CREATE, "title": f"Mới{HALF}", "content": "a"},
        TITLE,
        id="create-title",
    ),
    pytest.param(
        "artifact_create",
        {**CREATE, "kind": "code", "content": "a", "language": f"py{HALF}"},
        ARTIFACT_BAD_LANGUAGE.format(limit=LANGUAGE_MAX),
        id="create-language",
    ),
    pytest.param(
        "artifact_edit", {"old": "bye", "new": f"ciao{HALF}"}, CONTENT, id="edit-exact-match"
    ),
    pytest.param(
        "artifact_edit", {"old": LOOSE, "new": f"hi{HALF}"}, CONTENT, id="edit-loose-match"
    ),
    pytest.param(
        "artifact_edit",
        {"old": "bye", "new": "ciao", "title": f"Mới{HALF}"},
        TITLE,
        id="edit-title",
    ),
    pytest.param(
        "artifact_edit",
        {"old": "bye", "new": "bye", "title": f"Mới{HALF}"},
        TITLE,
        id="edit-that-changes-nothing-title",
    ),
    pytest.param("artifact_rewrite", {"content": f"z{HALF}"}, CONTENT, id="rewrite-content"),
    pytest.param(
        "artifact_rewrite", {"content": "z\n", "title": f"Mới{HALF}"}, TITLE, id="rewrite-title"
    ),
    pytest.param(
        "artifact_rewrite",
        {"content": TEXT, "title": f"Mới{HALF}"},
        TITLE,
        id="rewrite-that-changes-nothing-title",
    ),
]


@pytest.fixture
def client(deps_factory):
    """A failure no route turned into an answer comes back as the 500 a browser would see,
    instead of as an exception raised inside the test."""
    app = create_app(deps_factory(), schedule=False)
    with TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as client:
        yield client


def _send(client: TestClient, method: str, path: str, body: dict[str, Any]):
    """A body as a browser writes it. `json.dumps` writes a lone surrogate and an emoji alike
    as `\\u` escapes, which httpx's own `json=` would refuse to encode."""
    return client.request(
        method, path, content=json.dumps(body), headers={"content-type": "application/json"}
    )


def _canvas(store: Store) -> str:
    return store.artifacts.create("Plan", "markdown", "", USER, "", "a").id


def _state(store: Store, art: str) -> tuple[Any, ...]:
    """Everything a write could change: the canvases and their titles, the newest version's
    text, and the numbers of the versions behind it."""
    head = store.artifacts.head(art)
    return (
        [(summary.id, summary.title) for summary in store.artifacts.list()],
        head.version,
        head.content,
        [version.version for version in store.artifacts.versions(art)],
    )


@pytest.mark.parametrize(("write", "reason"), STORE_WRITES)
def test_the_store_refuses_half_a_character_saying_which_part_and_writes_nothing(
    store: Store, write: Callable[[ArtifactStore, str], object], reason: str
):
    art = _canvas(store)
    before = _state(store, art)
    with pytest.raises(UnstorableText) as refused:
        write(store.artifacts, art)
    assert str(refused.value) == reason
    assert _state(store, art) == before


@pytest.mark.parametrize(("method", "path", "body", "reason"), REST_WRITES)
def test_a_request_with_half_a_character_is_422_saying_which_part_and_writes_nothing(
    client, store: Store, method: str, path: str, body: dict[str, Any], reason: str
):
    art = _canvas(store)
    before = _state(store, art)
    response = _send(client, method, path.format(art=art), body)
    assert response.status_code == 422, response.text
    assert response.json() == {"detail": reason}
    assert _state(store, art) == before


def test_a_whole_emoji_sent_as_an_escaped_pair_is_kept_by_every_write(client, store: Store):
    """JSON writes an emoji as two escapes and the parser joins them: only a half left over,
    with no other half beside it, is refused."""
    new = {"title": f"Chạy {RUNNER}", "kind": "markdown", "content": f"a {RUNNER}"}
    made = _send(client, "POST", "/api/artifacts", new)
    assert made.status_code == 201, made.text
    art = made.json()["id"]
    assert store.artifacts.head(art).content == f"a {RUNNER}"
    assert store.artifacts.get(art).title == f"Chạy {RUNNER}"
    save = {"content": f"b {RUNNER}", "base_version": 1}
    saved = _send(client, "PUT", f"/api/artifacts/{art}", save)
    renamed = _send(client, "PATCH", f"/api/artifacts/{art}", {"title": f"Bơi {RUNNER}"})
    assert (saved.status_code, renamed.status_code) == (200, 200), (saved.text, renamed.text)
    assert store.artifacts.head(art).content == f"b {RUNNER}"
    assert store.artifacts.get(art).title == f"Bơi {RUNNER}"


@pytest.mark.parametrize(("name", "args", "reason"), TOOL_WRITES)
async def test_the_tool_refuses_half_a_character_saying_which_part_and_writes_nothing(
    store: Store, name: str, args: dict[str, Any], reason: str
):
    turn(store)
    art = await created(store, TEXT)
    before = _state(store, art)
    arguments = args if name == "artifact_create" else {"id": art, **args}
    result = await call(store, name, arguments)
    assert not result.ok
    assert result.output == TOOL_FAILED.format(error=reason)
    assert _state(store, art) == before
    assert lock_is_free(store)


async def test_a_whole_emoji_is_written_by_every_tool(store: Store):
    turn(store)
    art = await created(store, TEXT, title=f"Chạy {RUNNER}")
    edited = await call(store, "artifact_edit", {"id": art, "old": "bye", "new": f"ciao {RUNNER}"})
    rewrite = {"id": art, "content": f"z {RUNNER}\n", "title": f"Bơi {RUNNER}"}
    rewritten = await call(store, "artifact_rewrite", rewrite)
    assert edited.ok, edited.output
    assert rewritten.ok, rewritten.output
    assert store.artifacts.head(art).content == f"z {RUNNER}\n"
    assert store.artifacts.get(art).title == f"Bơi {RUNNER}"


async def test_an_old_passage_with_half_a_character_is_one_the_canvas_does_not_hold(store: Store):
    """A canvas never holds half a character, so `old` simply is not found and needs no check
    of its own, whether or not part of it matches."""
    turn(store)
    art = await created(store, TEXT)
    for old in (HALF, f"bye{HALF}"):
        result = await call(store, "artifact_edit", {"id": art, "old": old, "new": "ciao"})
        assert not result.ok
        assert result.output.startswith(TOOL_FAILED.format(error=ARTIFACT_EDIT_NO_MATCH))
    assert store.artifacts.head(art).content == TEXT
