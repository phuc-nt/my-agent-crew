"""A delegated run that stops early: its last words are often half a thought, so what it
had already done travels with them. Without that the delegator reads "nothing happened"
and hands the same work out again with a wider remit, on top of a row already written."""

from __future__ import annotations

from dataclasses import replace

import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.config import Route
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store import Store
from my_agent_crew.store.runs import DONE, HALTED, RunRecord
from my_agent_crew.tools.delegate_report import MAX_LISTED, unfinished_note
from tests.test_tools_delegate import agent, delegate

UNFINISHED = texts.DELEGATE_UNFINISHED.split("(")[0]


@pytest.fixture
def runtime(deps_factory, store: Store) -> Runtime:
    """A worker allowed two steps: it asks for a tool, the tool runs, and it is stopped before
    it can close the turn — the step cap a real child hit mid-verification."""
    base = deps_factory(routes=(Route("fake", "echo"),))
    worker = agent(base, "worker")
    agents = {
        "boss": agent(base, "boss", delegates=("worker",)),
        "worker": replace(worker, settings=replace(worker.settings, max_steps=2)),
    }
    rt = Runtime(base.settings, store, agents, ActivityHub(store))
    rt.wire_delegation()
    return rt


async def test_a_halted_child_reports_the_calls_that_went_through(runtime: Runtime):
    parent = runtime.store.create(agent_id="boss", autonomous=True)
    task = '/tool workspace_write {"path": "note.md", "content": "rpe 4"}'
    out = await delegate(runtime, parent.id, "call-1", task=task, agent="worker")

    child = runtime.store.for_parent_call("call-1")
    assert (runtime.deps_for("worker").profile.workspace / "note.md").exists()
    assert f"status={HALTED}" in out and UNFINISHED in out
    assert texts.DELEGATE_UNFINISHED_DONE in out
    assert "workspace_write note.md" in out
    assert child is not None


async def test_a_finished_child_carries_no_unfinished_note(deps_factory, store: Store):
    base = deps_factory(routes=(Route("fake", "echo"),))
    agents = {"boss": agent(base, "boss", delegates=("worker",)), "worker": agent(base, "worker")}
    rt = Runtime(base.settings, store, agents, ActivityHub(store))
    rt.wire_delegation()
    parent = rt.store.create(agent_id="boss", autonomous=True)

    out = await delegate(rt, parent.id, "call-1", task="đếm tệp", agent="worker")

    assert f"status={DONE}" in out and UNFINISHED not in out


def _run(steps: list[dict], status: str = HALTED) -> RunRecord:
    return RunRecord(
        id="r", agent_id="worker", conversation_id="c", source="delegate:p", title="t",
        status=status, started_at="2026-09-24T10:00:00+00:00", steps=steps, summary="max_steps",
    )  # fmt: skip


def _tool(name: str, ok: bool, output: str, **arguments) -> dict:
    return {"kind": "tool", "name": name, "arguments": arguments, "ok": ok, "output": output}


def test_failed_calls_are_left_out_and_the_command_is_shown_bare():
    failed = _tool("shell_run", False, "no such table", command="sqlite3 db .schema x")
    wrote = _tool("shell_run", True, "recorded note #11", command="event.py note", timeout_s=60)
    note = unfinished_note(_run([failed, wrote]))

    assert "max_steps" in note
    assert "- shell_run event.py note → recorded note #11" in note
    assert "no such table" not in note and "timeout_s" not in note


def test_a_long_run_lists_the_latest_calls_and_counts_the_rest():
    steps = [_tool("shell_run", True, "ok", command=f"cmd {i}") for i in range(MAX_LISTED + 3)]
    note = unfinished_note(_run(steps))

    assert texts.DELEGATE_UNFINISHED_EARLIER.format(count=3) in note
    assert f"cmd {MAX_LISTED + 2}" in note and "cmd 2 " not in note


def test_a_child_that_changed_nothing_says_so():
    note = unfinished_note(_run([_tool("shell_run", False, "boom", command="x")], status="error"))
    assert texts.DELEGATE_UNFINISHED_NOTHING in note


def test_a_done_run_gets_no_note():
    assert unfinished_note(_run([_tool("shell_run", True, "ok", command="x")], status=DONE)) == ""
