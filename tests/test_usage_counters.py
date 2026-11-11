"""The counts no run keeps: a prompt sent with old tool output trimmed, an output kept on
disk, a kit hook run or blocking, a command invoked. Each is added where it happens, by
name, and is still there when the store is opened again."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from my_agent_crew.agent.context_trim import KEEP_TOOL_OUTPUTS
from my_agent_crew.agent.turn_context import set_tool_call_id, set_turn_conversation
from my_agent_crew.agents.kit_commands import Command, invoked
from my_agent_crew.agents.kit_hooks import POST, PRE, Hook
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store import Store
from my_agent_crew.store.counters import (
    COMMAND,
    HOOK_BLOCK,
    HOOK_RUN,
    NAME_CHARS,
    PROMPT_TRIM,
    SPILL,
    utc_day,
)
from my_agent_crew.tools.hooks import HookRunner
from my_agent_crew.tools.output_spill import Spill
from my_agent_crew.tools.registry import Tool, ToolRegistry
from tests.conftest import collect
from tests.queue_helpers import while_the_tool_runs

PLAN = Command("mk:plan", "Lập kế hoạch.", "Write a plan for $ARGUMENTS.")


def counted(store: Store) -> list[tuple[str, str, str, int]]:
    rows = store.counters.since(utc_day())
    return [(r["kind"], r["agent_id"], r["name"], r["count"]) for r in rows]


def test_a_count_adds_up_by_day_and_outlives_the_process(tmp_path: Path):
    path = tmp_path / "crew.db"
    store = Store(path)
    store.counters.add(SPILL, "a", "fetch_url")
    store.counters.add(SPILL, "a", "fetch_url")
    store.counters.add(SPILL, "a", "fetch_url", day="2020-01-01")
    store.counters.add(COMMAND, "a", "x" * 500)
    store.close()

    again = Store(path)
    assert counted(again) == [(COMMAND, "a", "x" * NAME_CHARS, 1), (SPILL, "a", "fetch_url", 2)]
    assert again.counters.since("2020-01-01")[-1]["count"] == 3


def test_a_count_that_cannot_be_written_stops_nothing():
    store = Store(":memory:")
    store.close()
    with pytest.raises(sqlite3.Error):
        store.runs.recent()
    store.counters.add(SPILL, "a", "fetch_url")  # logged, not raised


async def test_a_prompt_sent_with_old_tool_output_trimmed_is_counted_once_per_call(rigs):
    rig = rigs([completion("một"), completion("hai")])
    agent = rig.deps.agent.id
    await collect(rig.inbound.stream(rig.conv.id, "chào"))
    assert counted(rig.store) == []  # nothing was old enough to trim
    for index in range(KEEP_TOOL_OUTPUTS + 1):
        told = Message(role="tool", content="x" * 500, tool_call_id=f"c{index}", name="slow")
        rig.store.append(rig.conv.id, told)
    await collect(rig.inbound.stream(rig.conv.id, "tiếp"))
    assert counted(rig.store) == [(PROMPT_TRIM, agent, "", 1)]


@pytest.fixture
def turn():
    """As inside a turn: an output is kept on disk under its conversation and call id."""
    set_turn_conversation("conv1", 0)
    set_tool_call_id("call1")
    try:
        yield
    finally:
        set_turn_conversation("", 0)
        set_tool_call_id("")


def sized(chars: int) -> Tool:
    async def answer(args: dict) -> str:
        return "x" * chars

    return Tool("reader", "d", {"type": "object"}, answer)


async def test_an_output_kept_on_disk_is_counted_under_its_tool(tmp_path: Path, turn):
    store = Store(":memory:")
    spill = Spill(tmp_path, store.counters.add, "a")
    await ToolRegistry([sized(100)], limit=2000, spill=spill).execute("reader", {})
    assert counted(store) == []  # it fitted: nothing was kept
    await ToolRegistry([sized(20000)], limit=2000, spill=spill).execute("reader", {})
    assert counted(store) == [(SPILL, "a", "reader", 1)]
    assert spill.read("conv1", "call1") == "x" * 20000


async def test_an_output_that_could_not_be_kept_is_not_counted(tmp_path: Path, turn):
    store = Store(":memory:")
    (tmp_path / "spill").write_text("a file where the folder should be")
    spill = Spill(tmp_path, store.counters.add, "a")
    await ToolRegistry([sized(20000)], limit=2000, spill=spill).execute("reader", {})
    assert counted(store) == []


def py(code: str) -> str:
    return f"python3 -c {json.dumps(code)}"


async def test_each_hook_run_and_each_block_is_counted_under_the_hook(tmp_path: Path):
    store = Store(":memory:")
    guard = py("import json,sys; sys.exit(2 if 'rm' in json.load(sys.stdin)['tool_input'] else 0)")
    after = py("import sys; sys.exit(0)")
    hooks = [Hook(PRE, "Bash", guard, tmp_path, 10), Hook(POST, "Bash", after, tmp_path, 10)]
    runner = HookRunner(hooks, "a", store.counters.add)
    assert await runner.before("shell_run", {"ls": 1}) is None
    assert await runner.before("shell_run", {"rm": 1}) is not None
    assert await runner.before("workspace_read", {"rm": 1}) is None  # no hook matched
    await runner.after("shell_run", {"ls": 1}, True, "out")
    assert counted(store) == [
        (HOOK_RUN, "a", f"{POST}: {after}"[:NAME_CHARS], 1),
        (HOOK_RUN, "a", f"{PRE}: {guard}"[:NAME_CHARS], 2),
        (HOOK_BLOCK, "a", f"{PRE}: {guard}"[:NAME_CHARS], 1),
    ]


def test_a_message_names_the_command_it_invokes_and_nothing_else():
    assert invoked("/steer dừng lại", [PLAN]) == "steer"
    assert invoked("  /mk:plan chuyến đi Đà Lạt", [PLAN]) == "mk:plan"
    assert invoked("/mk:plan@crew_bot", [PLAN]) == "mk:plan"
    assert invoked("/unknown thing", [PLAN]) is None
    assert invoked("/path/like/this", [PLAN]) is None
    assert invoked("không phải lệnh", [PLAN]) is None


async def test_a_command_is_counted_by_name_and_a_plain_message_is_not(rigs):
    rig = rigs([completion("một"), completion("hai")], commands=(PLAN,))
    agent = rig.deps.agent.id
    await collect(rig.inbound.stream(rig.conv.id, "chào"))
    assert counted(rig.store) == []
    await collect(rig.inbound.stream(rig.conv.id, "/mk:plan chuyến đi"))
    assert counted(rig.store) == [(COMMAND, agent, "mk:plan", 1)]


async def test_a_command_that_joins_a_running_turn_is_counted_too(rigs):
    call = ToolCall("c1", "slow", {})
    rig = rigs([completion(tool_calls=[call]), completion("xong")], commands=(PLAN,))
    await while_the_tool_runs(rig, "/steer nhanh lên", "/mk:plan chuyến đi")
    agent = rig.deps.agent.id
    assert counted(rig.store) == [(COMMAND, agent, "mk:plan", 1), (COMMAND, agent, "steer", 1)]
