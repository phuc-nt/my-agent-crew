"""`ToolRegistry`'s optional `spill`: a long output gets a spill file and a pointer line
telling the model how to read the whole thing back, on top of the shaping it already got.
Everything here is additive — a registry with no `spill` behaves exactly as before."""

from __future__ import annotations

from pathlib import Path

import pytest

from my_agent_crew.agent.turn_context import set_tool_call_id, set_turn_conversation
from my_agent_crew.tools.output_spill import READ_TOOL, Spill
from my_agent_crew.tools.registry import Tool, ToolRegistry


def tool(name: str = "t", run=None) -> Tool:
    async def default(args: dict) -> str:
        return "ok"

    return Tool(name, "d", {"type": "object"}, run or default)


@pytest.fixture(autouse=True)
def turn():
    """Every test here runs as if inside a real turn: `shape_with_spill` needs both a
    conversation and a call id in context to have anywhere to write to. Both are
    ContextVars with process-wide default state, so this resets them on the way out —
    a test elsewhere in the suite must never see "conv1" left over from here."""
    set_turn_conversation("conv1", 0)
    set_tool_call_id("call1")
    try:
        yield
    finally:
        set_turn_conversation("", 0)
        set_tool_call_id("")


@pytest.fixture
def spill(tmp_path: Path) -> Spill:
    return Spill(tmp_path)


async def test_a_long_output_gets_a_spill_file_and_a_pointer_line(spill: Spill, tmp_path: Path):
    async def big(args: dict) -> str:
        return "x" * 20000

    reg = ToolRegistry([tool(run=big)], limit=2000, spill=spill)
    result = await reg.execute("t", {})

    assert result.ok and READ_TOOL in result.output and "call1" in result.output
    assert len(result.output) <= 2000
    assert spill.read("conv1", "call1") == "x" * 20000


async def test_the_shaped_kind_on_the_result_is_unchanged_by_spilling(spill: Spill):
    async def big(args: dict) -> str:
        return "x" * 20000

    result = await ToolRegistry([tool(run=big)], limit=2000, spill=spill).execute("t", {})

    assert result.shaped_kind == "cut"


async def test_a_short_output_is_never_spilled(spill: Spill):
    reg = ToolRegistry([tool()], limit=2000, spill=spill)
    result = await reg.execute("t", {})

    assert result.output == "ok"
    assert spill.read("conv1", "call1") is None


async def test_a_write_failure_still_returns_the_ordinary_shaped_output(tmp_path: Path):
    """A read-only spill directory cannot be written to; the tool call itself must not fail
    because of it, and the model gets the plain shaped output with no dangling pointer."""

    async def big(args: dict) -> str:
        return "x" * 20000

    ro_home = tmp_path / "ro"
    ro_home.mkdir()
    ro_home.chmod(0o500)
    try:
        result = await ToolRegistry([tool(run=big)], limit=2000, spill=Spill(ro_home)).execute(
            "t", {}
        )
    finally:
        ro_home.chmod(0o700)

    assert result.ok and len(result.output) <= 2000
    assert READ_TOOL not in result.output


async def test_a_registry_with_no_spill_behaves_exactly_as_before():
    async def big(args: dict) -> str:
        return "x" * 20000

    result = await ToolRegistry([tool(run=big)], limit=2000).execute("t", {})

    assert result.ok and len(result.output) <= 2000
    assert READ_TOOL not in result.output


async def test_without_keeps_the_spill_its_parent_had(spill: Spill):
    reg = ToolRegistry([tool(), tool("other")], spill=spill)

    assert reg.without("other").spill is spill


async def test_tool_output_reads_own_output_is_never_spilled_even_with_a_tiny_cap(spill: Spill):
    """The read tool's own reply must never itself become a pointer to a spill file, or
    reading a segment back could spawn another one, defeating the point of the cap."""

    async def big(args: dict) -> str:
        return "x" * 20000

    reg = ToolRegistry([tool(name=READ_TOOL, run=big)], limit=50, spill=spill)
    result = await reg.execute(READ_TOOL, {})

    assert len(result.output) <= 50
    assert spill.read("conv1", "call1") is None


async def test_missing_turn_context_never_spills_even_with_a_configured_spill(spill: Spill):
    """A tool call outside a real turn — a direct registry call in a script, say — has no
    conversation or call id to spill under; spilling must not be attempted in that case."""
    set_turn_conversation("", 0)
    set_tool_call_id("")

    async def big(args: dict) -> str:
        return "x" * 20000

    result = await ToolRegistry([tool(run=big)], limit=2000, spill=spill).execute("t", {})

    assert result.ok and READ_TOOL not in result.output


async def test_the_after_hook_note_still_caps_a_spilled_output_exactly_as_before(
    spill: Spill, tmp_path: Path
):
    """A short after-hook note added to a pointer-bearing output is the same case the
    registry already handles for any shaped output: appended, then the combined text is
    re-capped by the same `truncate` call as always. Spilling changes nothing about that
    step — it only changes what `execute` had already shaped before the hook ever runs."""
    from my_agent_crew.agents.kit_hooks import POST, Hook
    from my_agent_crew.tools.hooks import HookRunner

    async def big(args: dict) -> str:
        return "x" * 20000

    note_hook = "python3 -c \"print('ghi chú', end='')\" 1>&2; exit 2"
    hooks = HookRunner([Hook(POST, "t", note_hook, tmp_path, timeout=10)], "a")
    without_spill = await ToolRegistry([tool(run=big)], limit=2000, hooks=hooks).execute("t", {})
    with_spill = await ToolRegistry([tool(run=big)], limit=2000, hooks=hooks, spill=spill).execute(
        "t", {}
    )

    assert len(without_spill.output) <= 2000 and len(with_spill.output) <= 2000
    # Spilling only changes the text the after-hook step starts from (it now ends in a
    # pointer line instead of a plain cut note); that step's own capping is unaffected —
    # both land at the same final length once the note is folded in and re-capped.
    assert len(with_spill.output) == len(without_spill.output)
