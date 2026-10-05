"""What a turn read away from the web chat is told after it makes a canvas.

On live a model asked over Telegram to write a canvas and send it exported the canvas to the
workspace and sent that file instead: the result it had just read said the person saw the
canvas beside the chat, and named no way to send it. A page and a picture then failed on
their suffix, and the note lost its caption."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from my_agent_crew.agent.turn_context import (
    CHAT,
    TELEGRAM,
    set_turn_conversation,
    set_turn_source,
)
from my_agent_crew.store.db import Store
from my_agent_crew.tools.artifact_texts import (
    ARTIFACT_CREATED,
    ARTIFACT_CREATED_AWAY,
    ARTIFACT_SEND_LINE,
)
from tests.canvas_helpers import call, tagged, turn

NOTE = "# Ghi chú\n\n- một\n"
AWAY = [TELEGRAM, "job:coach/brief"]


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    set_turn_source(CHAT)
    set_turn_conversation("")
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


async def _create(store: Store) -> tuple[str, list[str]]:
    args = {"title": "Ghi chú", "kind": "markdown", "content": NOTE}
    result = await call(store, "artifact_create", args)
    return tagged(result)[0], result.output.split("\n")[1:]


@pytest.mark.parametrize("source", AWAY)
async def test_a_turn_read_away_is_told_the_line_that_sends_its_new_canvas(store: Store, source):
    turn(store)
    set_turn_source(source)
    art, told = await _create(store)
    size = len(NOTE.encode())
    done = ARTIFACT_CREATED_AWAY.format(title="Ghi chú", kind="markdown", size=size, lines=4)
    assert told == [done, ARTIFACT_SEND_LINE.format(id=art)]
    assert f"`FILE: artifact:{art}`" in told[1]
    assert "cạnh khung" not in "\n".join(told)


async def test_a_turn_at_the_web_chat_is_told_the_canvas_opens_beside_it(store: Store):
    turn(store)
    _, told = await _create(store)
    size = len(NOTE.encode())
    assert told == [ARTIFACT_CREATED.format(title="Ghi chú", kind="markdown", size=size, lines=4)]


@pytest.mark.parametrize(
    ("source", "sent"), [(TELEGRAM, True), ("job:coach/brief", True), (CHAT, False)]
)
async def test_an_imported_file_is_sent_by_the_same_line(
    store: Store, tmp_path: Path, source: str, sent: bool
):
    """A picture is only ever imported, and is the canvas a chat can show best."""
    (tmp_path / "ghi-chu.md").write_text(NOTE, encoding="utf-8")
    turn(store)
    set_turn_source(source)
    result = await call(store, "artifact_import", {"path": "ghi-chu.md"}, root=tmp_path)
    line = ARTIFACT_SEND_LINE.format(id=tagged(result)[0])
    assert (result.output.split("\n")[-1] == line) is sent
    assert (line in result.output) is sent
