"""How loop events become steps on a run: a model call is one step, a tool call opens a
step that its result closes with a duration, and the terminal events set the status."""

from __future__ import annotations

from typing import Any

from my_agent_crew.activity.route_steps import apply_route_event
from my_agent_crew.activity.step_clock import close_step, instant, open_model_step, open_step
from my_agent_crew.activity.step_lookup import (
    CLOCK_KEY,
    pending_model_step,
    unsent_after_fallback,
)
from my_agent_crew.activity.step_previews import preview
from my_agent_crew.activity.tool_steps import apply_tool_event, bill
from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    EscalatedEvent,
    Event,
    HaltedEvent,
    ModelCallEvent,
    NestedCallEvent,
    RouteFallbackEvent,
    SteerEvent,
    TextDeltaEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from my_agent_crew.store.models import QUESTION
from my_agent_crew.store.runs import AWAITING, DONE, FAILED, HALTED, RUNNING, RunRecord
from my_agent_crew.tools.progress_note import note_text


def _model_step(run: RunRecord, clock: float) -> dict[str, Any]:
    """The open model step, opened now when the call sent no event before this one."""
    pending = pending_model_step(run)
    if pending is None:
        open_model_step(run, clock)
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
        close_step(step, clock)
        bill(run, event.cost_usd)
        run.status = RUNNING
        return
    if isinstance(event, ToolCallEvent | NestedCallEvent | ToolResultEvent):
        apply_tool_event(run, event, clock)
        return
    if isinstance(event, SteerEvent):
        # What the person handed the running turn, shown in one line the way a note is.
        instant(run, {"kind": "steer", "text": note_text({"text": event.text})}, clock)
        return
    if isinstance(event, ApprovalRequiredEvent):
        run.status = AWAITING
        # A question is summarised by what it asked. "ask_user" on the card would tell the
        # person a tool is waiting, when what is waiting is a sentence only they can finish.
        asked = str(event.arguments.get("question", "")) if event.kind == QUESTION else ""
        if asked:
            # The step stays open: a timeline that showed no pause would make the gap
            # before the answer look like the agent thinking for an hour.
            open_step(run, {"kind": "question", "question": preview(asked)}, clock)
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
    if isinstance(event, RouteFallbackEvent | EscalatedEvent):
        apply_route_event(run, event, clock)
