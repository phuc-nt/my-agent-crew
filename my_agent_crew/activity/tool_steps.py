"""How a tool call becomes a step on a run: the call opens it, each call a script makes
inside it is listed and billed as it ends, and the result closes it with a duration."""

from __future__ import annotations

from typing import Any

from my_agent_crew.activity.step_clock import close_step, instant, open_step
from my_agent_crew.activity.step_lookup import CLOCK_KEY, find_tool_step, unanswered_tool_step
from my_agent_crew.activity.step_previews import argument_preview, outcome_preview
from my_agent_crew.agent.tool_events import NestedCallEvent, ToolCallEvent, ToolResultEvent
from my_agent_crew.store.runs import RunRecord
from my_agent_crew.tools.progress_note import PROGRESS_NOTE_TOOL_NAME, note_text


def bill(run: RunRecord, cost_usd: float | None) -> None:
    """A call the provider put no price on is counted apart instead of guessed at."""
    if cost_usd is None:
        run.unknown_cost_calls += 1
    else:
        run.spent_usd += cost_usd


def _bill_nested(run: RunRecord, calls: list[dict[str, Any]]) -> None:
    for nested in calls:
        if nested["metered"]:
            bill(run, nested["cost_usd"])


def _not_yet_listed(step: dict[str, Any], calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The calls of a script's result that no event listed while it ran. Those were billed
    as they ended, and the result names them again in another order."""
    left = list(calls)
    for seen in step.get("calls", []):
        if seen in left:
            left.remove(seen)
    return left


def _open(run: RunRecord, event: ToolCallEvent, clock: float) -> None:
    if event.name == PROGRESS_NOTE_TOOL_NAME:
        # A note is the agent saying what it is doing, so it belongs on the timeline
        # the moment it is said — not when the call returns. It carries no ok flag
        # because it cannot fail.
        instant(run, {"kind": "note", "text": note_text(event.arguments)}, clock)
        return
    again = unanswered_tool_step(run, event.tool_call_id)
    if again is not None:
        again[CLOCK_KEY] = clock  # made again after a restart: timed from here
        # What a script called before the restart is not what it calls now. Those calls
        # stay billed, since they were paid for, and leave the list.
        again.pop("calls", None)
        return
    step = {"kind": "tool", "name": event.name, "tool_call_id": event.tool_call_id}
    shown = argument_preview(event.arguments)
    open_step(run, step | {"arguments": shown, "ok": None}, clock)


def _list_nested(run: RunRecord, event: NestedCallEvent) -> None:
    step = find_tool_step(run, event.tool_call_id)
    if step is None:
        return
    calls = step.setdefault("calls", [])
    if event.index < len(calls):
        calls[event.index] = event.call  # heard twice: kept once, billed once
        return
    calls.append(event.call)
    _bill_nested(run, [event.call])


def _close(run: RunRecord, event: ToolResultEvent, clock: float) -> None:
    if event.name == PROGRESS_NOTE_TOOL_NAME:
        # The note step was already written and closed by the call. Falling through
        # would find no open tool step for this id and open a second, empty one.
        return
    step = find_tool_step(run, event.tool_call_id)
    if step is None:
        open_step(run, {"kind": "tool", "name": event.name, "ok": None}, clock)
        step = run.steps[-1]
    step["ok"] = event.ok
    step["output"] = outcome_preview(event.output, event.ok)
    if event.shaped_kind != "none":
        step["shaped"] = {"kind": event.shaped_kind, "original_chars": event.original_chars}
    if event.metered:  # a tool that paid a model is billed with the run, like a completion
        step["cost_usd"] = event.cost_usd
        bill(run, event.cost_usd)
    if event.calls:  # what a script called on its own, which no other step shows
        _bill_nested(run, _not_yet_listed(step, event.calls))
        step["calls"] = event.calls  # as the script wrote them, whichever ended first
    # Kept only where a script set them: a step written before these existed has none,
    # and the card says nothing of what it cannot know.
    if event.received_chars is not None:
        step["received_chars"] = event.received_chars
    if event.printed_chars is not None:
        step["printed_chars"] = event.printed_chars
    close_step(step, clock)


def apply_tool_event(
    run: RunRecord, event: ToolCallEvent | NestedCallEvent | ToolResultEvent, clock: float
) -> None:
    if isinstance(event, ToolCallEvent):
        _open(run, event, clock)
    elif isinstance(event, NestedCallEvent):
        _list_nested(run, event)
    else:
        _close(run, event, clock)
