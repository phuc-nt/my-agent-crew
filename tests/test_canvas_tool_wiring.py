"""How the canvas tools reach an agent: one that does not narrow `tools` gets all seven, sized
to its own output cap, showing times in the owner's zone and reaching what its place in the
crew lets it reach; an allow-list keeps out any it does not name."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from zoneinfo import ZoneInfo

import httpx
import pytest

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.agents import DEFAULT_AGENT_ID, default_profile
from my_agent_crew.clock import day_and_time
from my_agent_crew.config import Settings
from my_agent_crew.server.tool_assembly import build_tools
from my_agent_crew.store.db import Store
from my_agent_crew.tools import ToolRegistry
from tests.canvas_helpers import agents_canvas, lines_text, persons_canvas, turn
from tests.conftest import CanvasClock

CANVAS_TOOLS = [
    "artifact_create",
    "artifact_list",
    "artifact_read",
    "artifact_edit",
    "artifact_rewrite",
    "artifact_import",
    "artifact_export",
]


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


def _assemble(
    settings: Settings, store: Store, agent_id: str = DEFAULT_AGENT_ID, tools: tuple[str, ...] = ()
) -> ToolRegistry:
    profile = replace(default_profile(settings), id=agent_id, tools=tools)
    return build_tools(profile, httpx.AsyncClient(), store, [])


def _canvas_names(registry: ToolRegistry) -> list[str]:
    return [name for name in registry.names() if name.startswith("artifact_")]


def test_an_agent_with_no_allow_list_gets_the_seven_canvas_tools(settings: Settings, store: Store):
    """Of the seven, only the one that writes over a workspace file stops for approval."""
    for agent_id in (DEFAULT_AGENT_ID, "coach"):
        registry = _assemble(settings, store, agent_id)
        assert _canvas_names(registry) == CANVAS_TOOLS, agent_id
        asking = [name for name in CANVAS_TOOLS if registry.get(name).requires_approval]
        assert asking == ["artifact_export"], agent_id


def test_an_allow_list_keeps_out_the_canvas_tools_it_does_not_name(
    settings: Settings, store: Store
):
    """A list written before canvases existed gains none of them, least of all a write."""
    reader = _assemble(settings, store, tools=("workspace_read", "artifact_list", "artifact_read"))
    assert reader.names() == ["workspace_read", "artifact_list", "artifact_read"]
    assert _canvas_names(_assemble(settings, store, tools=("workspace_read",))) == []


async def test_the_master_lists_every_canvas_in_the_owners_time_and_another_agent_does_not(
    settings: Settings, store: Store, canvas_clock: CanvasClock
):
    """A canvas another agent made in a conversation linked to none: only the master reaches
    it. The time a list shows is the owner's, not the machine's."""
    owner = replace(settings, timezone="America/New_York")
    art = agents_canvas(store, "ledger")
    turn(store)
    master = await _assemble(owner, store).execute("artifact_list", {})
    peer = await _assemble(owner, store, "coach").execute("artifact_list", {})
    when = day_and_time(canvas_clock.now, ZoneInfo("America/New_York"))
    assert f"- {art} «Kế hoạch»" in master.output and f"sửa {when})" in master.output
    assert art not in peer.output


async def test_a_canvas_page_fits_the_agents_own_output_cap(settings: Settings, store: Store):
    """A page sized for some other cap would come back cut by the registry."""
    registry = _assemble(replace(settings, tool_output_chars=3000), store)
    conv = turn(store)
    art = persons_canvas(store, lines_text(400), conv.id)
    result = await registry.execute("artifact_read", {"id": art})
    assert result.ok and result.shaped_kind == "none"
    assert "dòng 00001" in result.output and len(result.output) <= 3000
