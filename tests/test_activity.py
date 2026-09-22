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
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.resume import resolve_approval
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


def test_a_shortened_tool_output_says_so_on_its_step():
    """The card shows a 161-character preview whatever happened, so without this the reader
    cannot tell an answer built on the whole output from one built on a shortened it."""
    run = fresh_run()
    apply_event(run, ToolCallEvent("c1", "shell_run", {}), 10.0)
    apply_event(
        run,
        ToolResultEvent("c1", "shell_run", True, "{}", shaped_kind="json", original_chars=41000),
        10.5,
    )
    assert run.steps[-1]["shaped"] == {"kind": "json", "original_chars": 41000}


def test_an_output_that_fitted_carries_no_shaping_note():
    run = fresh_run()
    apply_event(run, ToolCallEvent("c1", "shell_run", {}), 10.0)
    apply_event(run, ToolResultEvent("c1", "shell_run", True, "ngắn"), 10.5)
    assert "shaped" not in run.steps[-1]


def test_tool_arguments_stay_a_mapping_so_a_stored_run_reads_back_the_same():
    # The web shows arguments as name/value pairs. Flattened to one string, it walks the
    # characters instead and shows a row per character — which only ever happened to a run
    # read back from the store, never to one watched live.
    run = fresh_run()
    apply_event(run, ToolCallEvent("c1", "read_file", {"path": "notes.md", "limit": 20}), 10.0)
    arguments = run.steps[0]["arguments"]
    assert arguments == {"path": "notes.md", "limit": 20}


def test_a_long_tool_argument_is_cut_down_rather_than_stored_whole():
    run = fresh_run()
    apply_event(run, ToolCallEvent("c1", "write", {"text": "x" * 500, "n": 3}), 10.0)
    arguments = run.steps[0]["arguments"]
    assert len(arguments["text"]) <= 161 and arguments["text"].endswith("…")
    # A small value keeps its own type: the web renders a number better than "3".
    assert arguments["n"] == 3


def test_a_big_list_argument_is_cut_down_rather_than_stored_whole():
    # A list has no length limit of its own, and this preview is written to the store and
    # re-broadcast with every later step of the same run — so one big argument would be
    # paid for again on each of them.
    run = fresh_run()
    apply_event(run, ToolCallEvent("c1", "delegate", {"skills": ["s" * 100] * 50}), 10.0)
    skills = run.steps[0]["arguments"]["skills"]
    assert isinstance(skills, str)
    assert len(skills) <= 161 and skills.endswith("…")


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


def test_a_waiting_question_is_summarised_by_what_it_asked():
    """ "ask_user" on the card would say a tool is waiting. What waits is a sentence only
    the person can finish, so the card has to show the sentence."""
    run = fresh_run()
    event = ApprovalRequiredEvent(
        "a1",
        "c1",
        "ask_user",
        {"question": "Dời hạn sang thứ sáu?"},
        kind="question",
        options=["có", "không"],
    )
    apply_event(run, event, 0.0)
    assert run.status == AWAITING
    assert run.summary == "Dời hạn sang thứ sáu?"


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


async def test_a_question_leaves_an_open_step_on_the_stored_run(deps_factory):
    """The web draws the pause from this step. Without it the gap between the question
    and the answer shows as nothing at all, and reads as an agent thinking for an hour."""
    asking = ToolCall("q1", "ask_user", {"question": "Dời hạn sang thứ sáu?"})
    deps = deps_factory(script=[completion(tool_calls=(asking,)), completion("xong")])
    hub = ActivityHub(deps.store)
    conv = deps.store.create()
    await collect(tracked(hub, run_turn(deps, conv.id, "xem hạn"), "default", "chat", "t", conv.id))

    [run] = hub.live()
    assert run.status == AWAITING
    asked = run.steps[-1]
    assert asked["kind"] == "question" and asked["question"] == "Dời hạn sang thứ sáu?"
    # Never closed: the answer resumes the turn as a different run, so a duration here
    # would be a measurement of nothing.
    assert asked["duration_ms"] is None
    assert deps.store.runs.get(run.id).steps[-1]["kind"] == "question"


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


async def test_waiting_on_a_conversation_returns_its_finished_run(deps_factory):
    """What a delegating parent does: block on the child and read the run that ended."""
    deps = deps_factory(script=[completion("xong")])
    hub = ActivityHub(deps.store)
    conv = deps.store.create()

    async def child() -> None:
        await collect(tracked(hub, run_turn(deps, conv.id, "hi"), "default", "chat", "t", conv.id))

    task = asyncio.create_task(child())
    run = await hub.wait_finished(conv.id, timeout=2.0)
    await task

    assert run is not None and run.status == DONE and run.conversation_id == conv.id


async def test_waiting_gives_up_when_the_run_takes_too_long(deps_factory):
    """A timeout returns nothing rather than hanging the caller forever."""
    deps = deps_factory(script=[completion("x")])
    hub = ActivityHub(deps.store)
    conv = deps.store.create()
    hub.start("default", "chat", "t", conv.id)

    assert await hub.wait_finished(conv.id, timeout=0.01) is None


async def test_a_run_paused_for_approval_is_not_finished(deps_factory):
    """The parent keeps waiting while a person decides, and wakes when the resumed run
    ends — not when it paused."""
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

    assert await hub.wait_finished(conv.id, timeout=0.01) is None

    resumed = resolve_approval(deps, conv.id, paused[-1].approval_id, True)
    await collect(tracked(hub, resumed, "default", "chat", "t", conv.id))
    run = await hub.wait_finished(conv.id, timeout=2.0)
    assert run is not None and run.status == DONE
