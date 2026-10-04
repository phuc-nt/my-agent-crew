"""What reading a canvas's workspace file again refuses, each with a status the web can act
on: no workspace file named, the canvas, its agent or its file gone, a file outside the
workspace or one that cannot be a version of the canvas, and a request from another site. A
refusal writes nothing and never says where the workspace sits on this machine."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from my_agent_crew.agents.profile import DEFAULT_AGENT_ID
from my_agent_crew.artifacts.kinds import cap_bytes
from my_agent_crew.server import create_app, routes_artifact_import
from my_agent_crew.server.artifact_errors import NOT_FOUND
from my_agent_crew.store.db import Store
from my_agent_crew.texts import FILE_OUTSIDE_WORKSPACE, WORKSPACE_IS_DIR, WORKSPACE_NOT_FOUND
from my_agent_crew.texts_canvas import (
    IMPORT_NOT_FILE,
    IMPORT_NOT_IMAGE,
    IMPORT_NOT_TEXT,
    IMPORT_TOO_LARGE,
    REIMPORT_AGENT_GONE,
    REIMPORT_NO_SOURCE,
)
from my_agent_crew.texts_credentials import CROSS_SITE_REQUEST
from my_agent_crew.tools.artifact_source import SourceFile
from tests.canvas_helpers import PLAN, PNG, SWIM, put
from tests.test_api_artifact_import import FILE, imported, reimport

CAP = cap_bytes("markdown")
OURS = f"workspace:{DEFAULT_AGENT_ID}/"


@pytest.fixture
def served(deps_factory) -> Iterator[tuple[TestClient, Path]]:
    """The app, and the default agent's workspace with FILE changed since it was imported."""
    deps = deps_factory()
    put(deps.agent.workspace, FILE, SWIM)
    put(deps.agent.workspace.parent, "outside.md", SWIM)
    with TestClient(create_app(deps, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, deps.agent.workspace


def _refused(answer: httpx.Response, root: Path) -> tuple[int, Any]:
    assert str(root.resolve().parent) not in answer.text, answer.text
    return answer.status_code, answer.json()["detail"]


def _untouched(store: Store, art: str) -> bool:
    head = store.artifacts.head(art)
    return (head.version, head.content or head.data) in ((1, PLAN), (1, PNG))


@pytest.mark.parametrize(
    "source",
    [
        "",
        "https://docs.example.com/deck?id=1",
        "file:///etc/hosts",
        "workspace:",
        f"workspace:{DEFAULT_AGENT_ID}",
        OURS,
        f"workspace:Not An Id/{FILE}",
        f"WORKSPACE:{DEFAULT_AGENT_ID}/{FILE}",
    ],
)
def test_a_canvas_that_names_no_workspace_file_is_422(served, store: Store, source: str):
    client, root = served
    art = imported(store, source=source)
    assert _refused(reimport(client, art), root) == (422, REIMPORT_NO_SOURCE)
    assert _untouched(store, art)


def test_a_canvas_that_is_not_there_is_404(served):
    client, root = served
    assert _refused(reimport(client, "art_khong_co"), root) == (404, NOT_FOUND)


def test_a_canvas_deleted_while_its_file_was_read_is_404(served, store: Store, monkeypatch):
    client, root = served
    art = imported(store)
    read = routes_artifact_import.read_source

    def read_while_the_person_deletes(root: Path, relative: str, kind: str) -> SourceFile:
        store.artifacts.delete(art)
        return read(root, relative, kind)

    monkeypatch.setattr(routes_artifact_import, "read_source", read_while_the_person_deletes)
    assert _refused(reimport(client, art), root) == (404, NOT_FOUND)


def test_a_source_whose_agent_left_the_crew_is_410(served, store: Store):
    """Gone, not missing: the canvas is there, and asking again will not bring the file back."""
    client, root = served
    art = imported(store, source=f"workspace:nguoi-da-roi/{FILE}")
    assert _refused(reimport(client, art), root) == (410, REIMPORT_AGENT_GONE)
    assert _untouched(store, art)


@pytest.mark.parametrize("path", ["notes/da-xoa.md", f"{FILE}/trong-tep.md"])
def test_a_source_file_that_is_gone_is_410(served, store: Store, path: str):
    client, root = served
    art = imported(store, source=OURS + path)
    assert _refused(reimport(client, art), root) == (410, WORKSPACE_NOT_FOUND.format(path=path))
    assert _untouched(store, art)


@pytest.mark.parametrize("path", ["../outside.md", "notes/../../outside.md", "/etc/hosts", "~root"])
def test_a_source_outside_the_workspace_is_403_in_words_for_a_person(
    served, store: Store, path: str
):
    """Not the refusal an agent gets, which tells it to reach for the shell."""
    client, root = served
    art = imported(store, source=OURS + path)
    assert _refused(reimport(client, art), root) == (403, FILE_OUTSIDE_WORKSPACE)
    assert _untouched(store, art)


@pytest.mark.parametrize(
    ("kind", "payload", "status", "refusal"),
    [
        (
            "markdown",
            b"a" * (CAP + 1),
            413,
            IMPORT_TOO_LARGE.format(path=FILE, kind="markdown", cap=CAP),
        ),
        ("markdown", b"\xff\xfe\x00a", 422, IMPORT_NOT_TEXT.format(path=FILE, kind="markdown")),
        ("markdown", b"a\x00b", 422, IMPORT_NOT_TEXT.format(path=FILE, kind="markdown")),
        ("image", SWIM.encode(), 422, IMPORT_NOT_IMAGE.format(path=FILE)),
        ("markdown", None, 422, WORKSPACE_IS_DIR.format(path=FILE)),
    ],
)
def test_a_file_that_cannot_be_a_version_of_the_canvas_is_refused_by_the_canvas_kind(
    served, store: Store, kind: str, payload: bytes | None, status: int, refusal: str
):
    """The detail is the sentence an agent's import would get, naming the path as stored."""
    client, root = served
    (root / FILE).unlink()
    if payload is None:
        (root / FILE).mkdir()
    else:
        put(root, FILE, payload)
    art = imported(store, PNG if kind == "image" else PLAN, kind=kind)
    assert _refused(reimport(client, art), root) == (status, refusal)
    assert _untouched(store, art)


def test_a_source_that_became_a_pipe_is_422_without_waiting_for_a_writer(served, store: Store):
    """A request waiting on a pipe would hold a server thread for good."""
    client, root = served
    (root / FILE).unlink()
    os.mkfifo(root / FILE)
    art = imported(store)
    answers: list[httpx.Response] = []
    asking = threading.Thread(target=lambda: answers.append(reimport(client, art)), daemon=True)
    asking.start()
    try:
        asking.join(timeout=5)
        waited = asking.is_alive()
    finally:
        # A request still waiting is let go by a writer, so it cannot outlive the test.
        writer = os.open(root / FILE, os.O_RDWR | os.O_NONBLOCK)
        asking.join(timeout=5)
        os.close(writer)
    assert not waited
    [answer] = answers
    assert _refused(answer, root) == (422, IMPORT_NOT_FILE.format(path=FILE))
    assert _untouched(store, art)


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
def test_a_page_of_another_site_cannot_ask_for_a_reimport(served, store: Store, site: str):
    client, root = served
    art = imported(store)
    answer = client.post(
        f"/api/artifacts/{art}/reimport",
        json={"base_version": 1},
        headers={"Sec-Fetch-Site": site},
    )
    assert _refused(answer, root) == (403, CROSS_SITE_REQUEST)
    assert _untouched(store, art)
    assert reimport(client, art).json()["changed"] is True


def test_full_storage_is_507_and_the_canvas_stays(served, store: Store, monkeypatch):
    client, root = served
    art = imported(store)
    monkeypatch.setattr("my_agent_crew.store.artifacts.STORAGE_CAP", len(PLAN.encode()) + 1)
    status, detail = _refused(reimport(client, art), root)
    assert (status, detail["cap"], detail["largest"][0]["id"]) == (507, len(PLAN.encode()) + 1, art)
    assert _untouched(store, art)
