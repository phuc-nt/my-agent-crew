"""How loop events become steps on a run: a model call is one step, a tool call opens a
step that its result closes with a duration, and the terminal events set the status."""

from __future__ import annotations

from typing import Any

from my_agent_crew.activity.step_previews import argument_preview, preview
from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    HaltedEvent,
    ModelCallEvent,
    RouteFallbackEvent,
    TextDeltaEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from my_agent_crew.store.models import QUESTION
from my_agent_crew.store.runs import AWAITING, DONE, FAILED, HALTED, RUNNING, RunRecord
from my_agent_crew.tools.progress_note import PROGRESS_NOTE_TOOL_NAME, note_text

CLOCK_KEY = "_clock"


def _open_step(run: RunRecord, step: dict[str, Any], clock: float) -> None:
    step[CLOCK_KEY] = clock
    step["duration_ms"] = None
    run.steps.append(step)


def _close_step(step: dict[str, Any], clock: float) -> None:
    started = step.pop(CLOCK_KEY, clock)
    step["duration_ms"] = int((clock - started) * 1000)


def _model_step(run: RunRecord, clock: float) -> dict[str, Any]:
    """The open model step, opened now when the call sent no event before this one."""
    pending = _pending_model_step(run)
    if pending is None:
        _open_step(run, {"kind": "model", "chars": 0, "first_token_ms": None}, clock)
        pending = run.steps[-1]
    return pending


def _mark_first_token(step: dict[str, Any], clock: float) -> None:
    if step.get("first_token_ms") is None:
        step["first_token_ms"] = int((clock - step.get(CLOCK_KEY, clock)) * 1000)


def apply_event(run: RunRecord, event: Event, clock: float) -> None:
    if isinstance(event, ModelCallEvent):
        # The step opens when the request leaves, so the wait for a tool-only answer,
        # which streams no word, is counted like any other.
        step = _model_step(run, clock)
        if event.stage == "first_token":
            _mark_first_token(step, clock)
        return
    if isinstance(event, TextDeltaEvent | ThinkingEvent):
        # Thinking opens the model step too, so its duration counts the silent part.
        pending = _model_step(run, clock)
        _mark_first_token(pending, clock)
        if isinstance(event, ThinkingEvent):
            pending["thinking"] = True
        else:
            pending["chars"] = int(pending.get("chars", 0)) + len(event.text)
        return
    if isinstance(event, AssistantMessageEvent):
        step = _model_step(run, clock)
        if not step.get("chars"):
            step["chars"] = len(event.content)
        step.update(
            provider=event.provider,
            model=event.model,
            cost_usd=event.cost_usd,
            prompt_tokens=event.prompt_tokens,
            cached_tokens=event.cached_tokens,
            tool_calls=[tc["name"] for tc in event.tool_calls],
            preview=preview(event.content),
        )
        _close_step(step, clock)
        if event.cost_usd is None:
            run.unknown_cost_calls += 1
        else:
            run.spent_usd += event.cost_usd
        run.status = RUNNING
        return
    if isinstance(event, ToolCallEvent):
        if event.name == PROGRESS_NOTE_TOOL_NAME:
            # A note is the agent saying what it is doing, so it belongs on the timeline
            # the moment it is said — not when the call returns. It is opened and closed
            # on the same clock because a sentence has no duration worth reading, and it
            # carries no ok flag because it cannot fail.
            step = {"kind": "note", "text": note_text(event.arguments)}
            _open_step(run, step, clock)
            _close_step(step, clock)
            return
        _open_step(
            run,
            {
                "kind": "tool",
                "name": event.name,
                "tool_call_id": event.tool_call_id,
                "arguments": argument_preview(event.arguments),
                "ok": None,
            },
            clock,
        )
        return
    if isinstance(event, ToolResultEvent):
        if event.name == PROGRESS_NOTE_TOOL_NAME:
            # The note step was already written and closed by the call. Falling through
            # would find no open tool step for this id and open a second, empty one.
            return
        step = _find_tool_step(run, event.tool_call_id)
        if step is None:
            _open_step(run, {"kind": "tool", "name": event.name, "ok": None}, clock)
            step = run.steps[-1]
        step["ok"] = event.ok
        step["output"] = preview(event.output)
        if event.shaped_kind != "none":
            step["shaped"] = {"kind": event.shaped_kind, "original_chars": event.original_chars}
        _close_step(step, clock)
        return
    if isinstance(event, ApprovalRequiredEvent):
        run.status = AWAITING
        # A question is summarised by what it asked. "ask_user" on the card would tell the
        # person a tool is waiting, when what is waiting is a sentence only they can finish.
        asked = str(event.arguments.get("question", "")) if event.kind == QUESTION else ""
        if asked:
            # The step stays open: a timeline that showed no pause would make the gap
            # before the answer look like the agent thinking for an hour.
            _open_step(run, {"kind": "question", "question": preview(asked)}, clock)
            run.summary = asked
            return
        # The reason says why an autonomous run stopped anyway; without it the card only
        # says "shell_run" and reads like a misconfiguration.
        run.summary = f"{event.name} ({event.reason})" if event.reason else event.name
        return
    if isinstance(event, DoneEvent):
        run.status = DONE
        run.summary = run.steps[-1].get("preview", "") if run.steps else ""
        return
    if isinstance(event, HaltedEvent):
        run.status = HALTED
        run.summary = event.reason
        return
    if isinstance(event, ErrorEvent):
        run.status = FAILED
        run.summary = event.message
        return
    if isinstance(event, RouteFallbackEvent):
        step = {
            "kind": "fallback",
            "provider": event.provider,
            "model": event.model,
            "error": preview(event.error),
        }
        _open_step(run, step, clock)
        _close_step(step, clock)


def _pending_model_step(run: RunRecord) -> dict[str, Any] | None:
    if run.steps and run.steps[-1].get("kind") == "model" and CLOCK_KEY in run.steps[-1]:
        return run.steps[-1]
    return None


def _find_tool_step(run: RunRecord, tool_call_id: str) -> dict[str, Any] | None:
    for step in reversed(run.steps):
        if step.get("kind") == "tool" and step.get("tool_call_id") == tool_call_id:
            return step
    return None
