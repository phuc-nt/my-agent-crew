"""Runs and their step timeline: events become steps, the hub stores and broadcasts."""

import asyncio

import pytest

from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.activity.steps import apply_event
from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    HaltedEvent,
    RouteFallbackEvent,
    TextDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from my_agent_crew.agent.loop import resolve_approval, run_turn
from my_agent_crew.config import Route
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store import Store
from my_agent_crew.store.runs import AWAITING, DONE, FAILED, HALTED, RUNNING, RunRecord
from tests.conftest import collect


def fresh_run() -> RunRecord:
    return RunRecord("r1", "default", "c1", "chat", "t", RUNNING, "2026-09-19T08:00:00")


def test_model_and_tool_steps_get_cost_and_durations():
    run = fresh_run()
    apply_event(run, TextDeltaEvent("xin "), 10.0)
    apply_event(run, TextDeltaEvent("chào"), 10.1)
    call = {"id": "c1", "name": "workspace_list", "arguments": {}}
    apply_event(run, AssistantMessageEvent(1, "xin chào", [call], "p", "m", 0.002), 10.5)
    apply_event(run, ToolCallEvent("c1", "workspace_list", {"path": "."}), 10.6)
    apply_event(run, ToolResultEvent("c1", "workspace_list", True, "a.txt\n" * 100), 11.6)
    apply_event(run, AssistantMessageEvent(2, "xong", [], "p", "m", None), 12.0)
    apply_event(run, DoneEvent(0.002, 1), 12.0)
    model, tool, last = run.steps
    assert model["kind"] == "model" and model["chars"] == 8 and model["duration_ms"] == 500
    assert model["cost_usd"] == 0.002 and model["tool_calls"] == ["workspace_list"]
    assert tool["kind"] == "tool" and tool["ok"] is True and tool["duration_ms"] == 1000
    assert len(tool["output"]) <= 161 and tool["output"].endswith("…")
    assert last["duration_ms"] == 0 and last["cost_usd"] is None
    assert run.status == DONE and run.summary == "xong"
    assert run.spent_usd == pytest.approx(0.002) and run.unknown_cost_calls == 1


def test_route_fallback_becomes_a_step_without_touching_cost():
    run = fresh_run()
    apply_event(run, RouteFallbackEvent("openrouter", "glm", "HTTP 429 from glm"), 10.0)
    apply_event(run, AssistantMessageEvent(1, "ok", [], "openrouter", "glm-5", 0.001), 11.0)
    fallback, model = run.steps
    assert fallback == {
        "kind": "fallback",
        "provider": "openrouter",
        "model": "glm",
        "error": "HTTP 429 from glm",
        "duration_ms": 0,
    }
    assert model["model"] == "glm-5" and run.spent_usd == pytest.approx(0.001)
    assert run.status == RUNNING


@pytest.mark.parametrize(
    "event,status,summary",
    [
        (ApprovalRequiredEvent("a1", "c1", "shell_run", {}), AWAITING, "shell_run"),
        (HaltedEvent("budget", 0.5), HALTED, "budget"),
        (ErrorEvent("down"), FAILED, "down"),
    ],
)
def test_terminal_events_set_status(event, status, summary):
    run = fresh_run()
    apply_event(run, event, 0.0)
    assert (run.status, run.summary) == (status, summary)


async def test_tracked_turn_is_stored_and_streamed(deps_factory):
    deps = deps_factory(
        script=[completion(tool_calls=(ToolCall("c1", "workspace_list", {}),)), completion("ok")]
    )
    hub = ActivityHub(deps.store)
    conv = deps.store.create(title="Việc A")
    seen: list[dict] = []

    async def watch():
        async for payload in hub.subscribe():
            seen.append(payload)
            if payload["type"] == "run" and payload["run"]["status"] == DONE:
                return

    watcher = asyncio.create_task(watch())
    await asyncio.sleep(0)
    events = tracked(hub, run_turn(deps, conv.id, "ls"), "default", "chat", conv.title, conv.id)
    loop_events = await collect(events)
    await asyncio.wait_for(watcher, 2)
    assert isinstance(loop_events[-1], DoneEvent)
    [run] = hub.recent()
    assert run.status == DONE and run.conversation_id == conv.id and hub.live() == []
    assert [s["kind"] for s in run.steps] == ["model", "tool", "model"]
    assert seen[0] == {"type": "snapshot", "runs": []}
    assert seen[1]["type"] == "run" and seen[1]["run"]["status"] == RUNNING
    assert [p["event"]["type"] for p in seen if p["type"] == "event"][-1] == "done"
    assert deps.store.runs.get(run.id).steps == run.steps


async def test_approval_pause_keeps_one_run_across_resume(deps_factory):
    deps = deps_factory(routes=(Route("fake", "echo"),))
    hub = ActivityHub(deps.store)
    conv = deps.store.create()
    paused = await collect(
        tracked(
            hub,
            run_turn(deps, conv.id, '/tool shell_run {"command": "echo 1"}'),
            "default",
            "chat",
            "t",
            conv.id,
        )
    )
    [run] = hub.live()
    assert run.status == AWAITING and run.summary == "shell_run"
    resumed = resolve_approval(deps, conv.id, paused[-1].approval_id, True)
    await collect(tracked(hub, resumed, "default", "chat", "t", conv.id))
    assert hub.live() == [] and [r.id for r in hub.recent()] == [run.id]
    assert hub.recent()[0].status == DONE


async def test_abandoned_consumer_marks_run_as_error(deps_factory):
    deps = deps_factory(script=[completion("x" * 200)])
    hub = ActivityHub(deps.store)
    conv = deps.store.create()
    gen = tracked(hub, run_turn(deps, conv.id, "hi"), "default", "chat", "t", conv.id)
    await gen.__anext__()
    await gen.aclose()
    [run] = hub.recent()
    assert run.status == FAILED and run.summary == "interrupted"


def test_runs_left_running_by_a_crash_are_marked_on_startup(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    store.runs.save(fresh_run())
    ActivityHub(store)
    assert store.runs.get("r1").status == FAILED
