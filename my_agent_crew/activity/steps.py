"""How loop events become steps on a run: a model call is one step, a tool call opens a
step that its result closes with a duration, and the terminal events set the status."""

from __future__ import annotations

from typing import Any

from my_agent_crew.activity.step_lookup import (
    CLOCK_KEY,
    find_tool_step,
    pending_model_step,
    unanswered_tool_step,
    unsent_after_fallback,
)
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
    SteerEvent,
    TextDeltaEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from my_agent_crew.store.models import QUESTION
from my_agent_crew.store.runs import AWAITING, DONE, FAILED, HALTED, RUNNING, RunRecord
from my_agent_crew.tools.progress_note import PROGRESS_NOTE_TOOL_NAME, note_text


def _open_step(run: RunRecord, step: dict[str, Any], clock: float) -> None:
    step[CLOCK_KEY] = clock
    step["duration_ms"] = None
    run.steps.append(step)


def _close_step(step: dict[str, Any], clock: float) -> None:
    started = step.pop(CLOCK_KEY, clock)
    # A paused run outlives its process, and a reboot restarts the clock it was timed on.
    step["duration_ms"] = max(0, int((clock - started) * 1000))


def _instant(run: RunRecord, step: dict[str, Any], clock: float) -> None:
    """A step with no duration worth reading, opened and closed on the same clock."""
    _open_step(run, step, clock)
    _close_step(step, clock)


def _model_step(run: RunRecord, clock: float) -> dict[str, Any]:
    """The open model step, opened now when the call sent no event before this one."""
    pending = pending_model_step(run)
    if pending is None:
        _open_step(run, {"kind": "model", "chars": 0, "first_token_ms": None}, clock)
        pending = run.steps[-1]
    return pending


def _bill(run: RunRecord, cost_usd: float | None) -> None:
    """A call the provider put no price on is counted apart instead of guessed at."""
    if cost_usd is None:
        run.unknown_cost_calls += 1
    else:
        run.spent_usd += cost_usd


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
        if event.provider is None:
            # A child's answer handed on as this reply: no model spoke, so there is no
            # step to time or bill. The delegate tool step already shows the answer.
            run.status = RUNNING
            return
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
        _bill(run, event.cost_usd)
        run.status = RUNNING
        return
    if isinstance(event, ToolCallEvent):
        if event.name == PROGRESS_NOTE_TOOL_NAME:
            # A note is the agent saying what it is doing, so it belongs on the timeline
            # the moment it is said — not when the call returns. It carries no ok flag
            # because it cannot fail.
            _instant(run, {"kind": "note", "text": note_text(event.arguments)}, clock)
            return
        again = unanswered_tool_step(run, event.tool_call_id)
        if again is not None:
            again[CLOCK_KEY] = clock  # made again after a restart: timed from here
            return
        step = {"kind": "tool", "name": event.name, "tool_call_id": event.tool_call_id}
        shown = argument_preview(event.arguments)
        _open_step(run, step | {"arguments": shown, "ok": None}, clock)
        return
    if isinstance(event, ToolResultEvent):
        if event.name == PROGRESS_NOTE_TOOL_NAME:
            # The note step was already written and closed by the call. Falling through
            # would find no open tool step for this id and open a second, empty one.
            return
        step = find_tool_step(run, event.tool_call_id)
        if step is None:
            _open_step(run, {"kind": "tool", "name": event.name, "ok": None}, clock)
            step = run.steps[-1]
        step["ok"] = event.ok
        step["output"] = preview(event.output)
        if event.shaped_kind != "none":
            step["shaped"] = {"kind": event.shaped_kind, "original_chars": event.original_chars}
        if event.metered:  # a tool that paid a model is billed with the run, like a completion
            step["cost_usd"] = event.cost_usd
            _bill(run, event.cost_usd)
        _close_step(step, clock)
        return
    if isinstance(event, SteerEvent):
        # What the person handed the running turn, shown in one line the way a note is.
        _instant(run, {"kind": "steer", "text": note_text({"text": event.text})}, clock)
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
        if unsent_after_fallback(run):
            # The last route failed too: the step moved there for "the next route" waits
            # on nothing, and left open it would read as a model that never answered.
            run.steps.pop()
        run.status = FAILED
        run.summary = event.message
        return
    if isinstance(event, RouteFallbackEvent):
        # The request's model step was timing the route that just failed. That wait is the
        # fallback's, and the step moves after it to time the next route, so a run that
        # recovered keeps one model step per call and none of them left open.
        pending = pending_model_step(run)
        if pending is not None:
            run.steps.pop()
        step = {"kind": "fallback", "provider": event.provider, "model": event.model}
        step["error"] = preview(event.error)
        _open_step(run, step, pending[CLOCK_KEY] if pending is not None else clock)
        _close_step(step, clock)
        if pending is not None:
            _open_step(run, {"kind": "model", "chars": 0, "first_token_ms": None}, clock)
