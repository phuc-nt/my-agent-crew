"""Reading a canvas's workspace file again over REST. The person pressing the button decides:
the file becomes their newest version, marked as an import, unless something was saved since
the version the panel loaded. A file that changes nothing adds no version, whatever version
the panel loaded."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from my_agent_crew.agents.profile import DEFAULT_AGENT_ID
from my_agent_crew.server import create_app, routes_artifact_import
from my_agent_crew.store.artifact_models import IMPORT_NOTE, USER
from my_agent_crew.store.db import Store
from my_agent_crew.tools.artifact_source import SourceFile
from tests.canvas_helpers import PLAN, PNG, SWIM, put

FILE = "notes/plan.md"
SOURCE = f"workspace:{DEFAULT_AGENT_ID}/{FILE}"
AGENT = f"agent:{DEFAULT_AGENT_ID}"
FROM_FILE = "# Kế hoạch\ntừ tệp\n"


@pytest.fixture
def served(deps_factory) -> Iterator[tuple[TestClient, Path]]:
    """The app, and the default agent's workspace with FILE holding PLAN."""
    deps = deps_factory()
    put(deps.agent.workspace, FILE, PLAN)
    with TestClient(create_app(deps, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, deps.agent.workspace


def imported(
    store: Store, payload: str | bytes = PLAN, source: str = SOURCE, kind: str = "markdown"
) -> str:
    """A canvas the default agent made from a file, as `artifact_import` leaves one."""
    held = {"data": payload} if isinstance(payload, bytes) else {"content": payload}
    made = store.artifacts.create(
        "Kế hoạch", kind, DEFAULT_AGENT_ID, AGENT, "", source=source, **held
    )
    return made.id


def reimport(client: TestClient, art: str, base_version: int = 1, **more: object) -> httpx.Response:
    body = {"base_version": base_version, **more}
    return client.post(f"/api/artifacts/{art}/reimport", json=body)


def test_a_changed_file_becomes_the_persons_newest_version_marked_as_an_import(
    served, store: Store
):
    client, root = served
    art = imported(store)
    put(root, FILE, SWIM)
    answer = reimport(client, art)
    summary, head = store.artifacts.get(art), store.artifacts.head(art)
    assert (answer.status_code, answer.json()) == (
        200,
        {"changed": True, "artifact": summary.to_dict()},
    )
    assert "content" not in answer.json()["artifact"]
    assert (head.version, head.content, head.author) == (2, SWIM, USER)
    assert (head.note, head.conversation_id, summary.source) == (IMPORT_NOTE, "", SOURCE)


def test_a_file_that_changes_nothing_adds_no_version(served, store: Store):
    """Compared as the store keeps text, so a file that differs only in its byte-order mark
    and line endings is the same file."""
    client, root = served
    art = imported(store)
    before = store.artifacts.get(art)
    for payload in (PLAN.encode(), b"\xef\xbb\xbf" + PLAN.replace("\n", "\r\n").encode()):
        put(root, FILE, payload)
        answer = reimport(client, art)
        assert (answer.status_code, answer.json()) == (
            200,
            {"changed": False, "artifact": before.to_dict()},
        )
    assert store.artifacts.get(art) == before
    assert [version.version for version in store.artifacts.versions(art)] == [1]


@pytest.mark.parametrize("body", [{}, {"base_version": 0}, {"base_version": "1"}, {"version": 1}])
def test_a_reimport_must_say_which_version_the_panel_loaded(served, store: Store, body: dict):
    client, root = served
    art = imported(store)
    put(root, FILE, SWIM)
    assert client.post(f"/api/artifacts/{art}/reimport", json=body).status_code == 422
    assert store.artifacts.get(art).head_version == 1


def test_a_file_never_goes_over_a_version_saved_since_the_panel_loaded(served, store: Store):
    """The refusal carries the newest version to show. A file holding what that version holds
    has nothing to write, so there is nothing to refuse."""
    client, root = served
    art = imported(store)
    store.artifacts.write(art, SWIM, USER, "")
    put(root, FILE, FROM_FILE)
    refused = reimport(client, art, base_version=1)
    assert refused.status_code == 409
    assert refused.json()["detail"] == {"head_version": 2, "content": SWIM, "author": USER}
    assert store.artifacts.get(art).head_version == 2
    put(root, FILE, SWIM)
    same = reimport(client, art, base_version=1)
    assert (same.status_code, same.json()["changed"]) == (200, False)
    assert store.artifacts.get(art).head_version == 2
    put(root, FILE, FROM_FILE)
    assert reimport(client, art, base_version=2).json()["changed"] is True
    kept = [store.artifacts.version(art, number).content for number in (1, 2, 3)]
    assert kept == [PLAN, SWIM, FROM_FILE]


def test_a_save_made_while_the_file_was_read_is_what_the_file_is_compared_with(
    served, store: Store, monkeypatch
):
    """The newest version is looked up with the file in hand, not before the disk is read."""
    client, root = served
    art = imported(store)
    put(root, FILE, SWIM)
    read = routes_artifact_import.read_source

    def read_while_the_person_saves(root: Path, relative: str, kind: str) -> SourceFile:
        store.artifacts.write(art, SWIM, USER, "")
        return read(root, relative, kind)

    monkeypatch.setattr(routes_artifact_import, "read_source", read_while_the_person_saves)
    answer = reimport(client, art)
    assert (answer.status_code, answer.json()["changed"]) == (200, False)
    assert answer.json()["artifact"]["head_version"] == store.artifacts.get(art).head_version == 2


def test_a_picture_is_compared_and_replaced_byte_for_byte(served, store: Store):
    client, root = served
    put(root, "img/logo.png", PNG)
    art = imported(store, PNG, f"workspace:{DEFAULT_AGENT_ID}/img/logo.png", "image")
    assert reimport(client, art).json()["changed"] is False
    put(root, "img/logo.png", PNG + b"\x00")
    assert reimport(client, art).json()["changed"] is True
    head = store.artifacts.head(art)
    assert (head.version, head.content, head.data) == (2, None, PNG + b"\x00")
    assert (head.author, head.note) == (USER, IMPORT_NOTE)
