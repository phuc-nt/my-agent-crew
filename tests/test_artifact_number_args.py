"""A number a canvas tool is sent. One written as text is read as the number and one that is
no number reads as left out, as before; one that is not finite (JSON lets `1e999` through as
infinity) is refused in words before a file is written or a read cursor moves."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import ARTIFACT_ARG_NUMBER
from tests.canvas_helpers import PLAN, SWIM, call, created, persons_canvas, seen, turn

NOT_FINITE = ["1e999", "-1e999", "Infinity", "-Infinity", "NaN"]


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


def _refusal(name: str) -> str:
    return TOOL_FAILED.format(error=ARTIFACT_ARG_NUMBER.format(name=name))


@pytest.mark.parametrize("sent", NOT_FINITE)
async def test_a_version_that_is_no_finite_number_exports_nothing(
    store: Store, tmp_path: Path, sent: str
):
    turn(store)
    art = await created(store, PLAN)
    args = {"id": art, "path": "out/x.md", "version": json.loads(sent)}
    result = await call(store, "artifact_export", args, root=tmp_path)
    assert result.output == _refusal("version")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("name", ["version", "from_line", "lines"])
@pytest.mark.parametrize("sent", NOT_FINITE)
async def test_a_read_sent_one_shows_no_page_and_moves_no_cursor(
    store: Store, name: str, sent: str
):
    conv = turn(store)
    art = persons_canvas(store, PLAN, conv.id)
    result = await call(store, "artifact_read", {"id": art, name: json.loads(sent)})
    assert result.output == _refusal(name)
    assert seen(store, conv, art) == 0


@pytest.mark.parametrize(
    ("version", "number"),
    [(1, 1), (1.0, 1), ("1", 1), (1.9, 1), (None, 2), ("", 2), ("một", 2), ([1], 2), (0, 2)],
)
async def test_a_number_as_text_is_read_and_what_is_no_number_reads_as_left_out(
    store: Store, tmp_path: Path, version: Any, number: int
):
    turn(store)
    art = await created(store, PLAN)
    store.artifacts.write(art, SWIM, USER, "")
    args = {"id": art, "path": "x.md", "version": version}
    result = await call(store, "artifact_export", args, root=tmp_path)
    assert result.ok, result.output
    assert (tmp_path / "x.md").read_text(encoding="utf-8") == (PLAN, SWIM)[number - 1]
    page = await call(store, "artifact_read", {"id": art, "version": version, "lines": "1"})
    shown = page.output.splitlines()
    assert page.ok and f"v{number}," in shown[0], page.output
    assert "# Kế hoạch" in shown and "chạy 5 km" not in shown
