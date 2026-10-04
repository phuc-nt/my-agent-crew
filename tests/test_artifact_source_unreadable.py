"""A workspace file the process may not read. It is a file like any other, so the refusal says
what is wrong with it rather than calling it no file: the same sentence from the import tool
and from the web's re-import, which answers 422 as it does for any file it cannot take in."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.agent.turn_context import (
    CHAT,
    canvas_writes,
    set_turn_conversation,
    set_turn_source,
)
from my_agent_crew.server import create_app
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.tools.artifact_file_texts import IMPORT_NOT_READABLE
from my_agent_crew.tools.artifact_scope import NEW_CANVAS
from my_agent_crew.tools.artifact_source import SourceError, read_source
from tests.canvas_helpers import PLAN, call, put, turn
from tests.test_api_artifact_import import FILE, imported, reimport

pytestmark = pytest.mark.skipif(os.geteuid() == 0, reason="root may read any file")
REFUSAL = IMPORT_NOT_READABLE.format(path=FILE)


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture
def closing() -> Iterator[list[Path]]:
    """Whatever a test puts here is closed to everyone, and opened again once the test is
    over so the folder it sits in can be cleared away."""
    closed: list[Path] = []
    yield closed
    for entry in closed:
        entry.chmod(0o700)


def _closed(root: Path, closing: list[Path], what: str = "file") -> None:
    file = put(root, FILE, PLAN)
    closing.append(file if what == "file" else file.parent)
    closing[-1].chmod(0o000)


@pytest.mark.parametrize("what", ["file", "folder"])
def test_a_file_closed_to_the_process_is_refused_for_that(
    tmp_path: Path, closing: list[Path], what: str
):
    _closed(tmp_path, closing, what)
    with pytest.raises(SourceError) as caught:
        read_source(tmp_path, FILE, "markdown")
    assert (caught.value.status, str(caught.value)) == (422, REFUSAL)
    assert str(tmp_path) not in str(caught.value)


async def test_the_import_tool_says_so_and_makes_no_canvas(
    store: Store, tmp_path: Path, closing: list[Path]
):
    turn(store)
    _closed(tmp_path, closing)
    result = await call(store, "artifact_import", {"path": FILE}, root=tmp_path)
    assert result.output == TOOL_FAILED.format(error=REFUSAL)
    assert store.artifacts.list() == [] and canvas_writes(NEW_CANVAS) == 0


def test_the_webs_reimport_answers_422_with_the_same_sentence(
    deps_factory, store: Store, closing: list[Path]
):
    deps = deps_factory()
    _closed(deps.agent.workspace, closing)
    art = imported(store)
    with TestClient(create_app(deps, schedule=False), base_url="http://127.0.0.1") as client:
        answer = reimport(client, art)
    assert (answer.status_code, answer.json()["detail"]) == (422, REFUSAL)
    assert store.artifacts.head(art).version == 1
