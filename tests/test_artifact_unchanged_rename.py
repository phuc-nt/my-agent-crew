"""A write that changes nothing still renames the canvas, and that rename is a store call of
its own: the person may delete the canvas between the write that found nothing to change and
the rename. The agent is then told the canvas is gone, in the words every canvas tool uses,
rather than that the tool broke."""

import pytest

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.store.artifact_models import ArtifactSummary
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import ARTIFACT_NOT_FOUND
from tests.canvas_helpers import PLAN, call, created, turn


@pytest.fixture(autouse=True)
def fresh_turn():
    set_turn_source(CHAT)
    set_turn_conversation("")
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.mark.parametrize(
    ("tool", "same"),
    [
        ("artifact_edit", {"old": "bơi", "new": "bơi"}),
        ("artifact_rewrite", {"content": PLAN}),
    ],
)
async def test_a_canvas_deleted_before_an_unchanged_write_renames_it_reads_as_not_found(
    store: Store, monkeypatch, tool: str, same: dict[str, str]
):
    turn(store)
    art = await created(store, PLAN)
    rename = store.artifacts.rename
    renames: list[str] = []

    def deleted_first(artifact_id: str, title: str) -> ArtifactSummary:
        renames.append(title)
        store.artifacts.delete(artifact_id)
        return rename(artifact_id, title)

    monkeypatch.setattr(store.artifacts, "rename", deleted_first)
    result = await call(store, tool, {"id": art, **same, "title": "Kế hoạch mới"})
    assert renames == ["Kế hoạch mới"]
    assert not result.ok
    assert result.output == TOOL_FAILED.format(error=ARTIFACT_NOT_FOUND.format(id=art))
