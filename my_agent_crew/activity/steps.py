"""How loop events become steps on a run: a model call is one step, a tool call opens a
step that its result closes with a duration, and the terminal events set the status."""

from __future__ import annotations

from typing import Any

from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    HaltedEvent,
    RouteFallbackEvent,
    TextDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from my_agent_crew.store.runs import AWAITING, DONE, FAILED, HALTED, RUNNING, RunRecord

PREVIEW_CHARS = 160
CLOCK_KEY = "_clock"


def _preview(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= PREVIEW_CHARS else text[:PREVIEW_CHARS] + "…"


def _argument_preview(arguments: dict[str, Any]) -> dict[str, Any]:
    """Tool arguments kept as the mapping they are, with only long text cut down.

    Stringifying the whole mapping would have been shorter to write, but the web reads
    these as a mapping of name to value: given a string it walks the characters and shows
    one row per character. Keeping the shape means a run read back from the store renders
    the same way as one watched live.
    """
    return {
        key: _preview(value) if isinstance(value, str) else value
        for key, value in arguments.items()
    }


def _open_step(run: RunRecord, step: dict[str, Any], clock: float) -> None:
    step[CLOCK_KEY] = clock
    step["duration_ms"] = None
    run.steps.append(step)


def _close_step(step: dict[str, Any], clock: float) -> None:
    started = step.pop(CLOCK_KEY, clock)
    step["duration_ms"] = int((clock - started) * 1000)


def apply_event(run: RunRecord, event: Event, clock: float) -> None:
    if isinstance(event, TextDeltaEvent):
        pending = _pending_model_step(run)
        if pending is None:
            _open_step(run, {"kind": "model", "chars": 0}, clock)
            pending = run.steps[-1]
        pending["chars"] = int(pending.get("chars", 0)) + len(event.text)
        return
    if isinstance(event, AssistantMessageEvent):
        step = _pending_model_step(run)
        if step is None:
            _open_step(run, {"kind": "model", "chars": len(event.content)}, clock)
            step = run.steps[-1]
        step.update(
            provider=event.provider,
            model=event.model,
            cost_usd=event.cost_usd,
            tool_calls=[tc["name"] for tc in event.tool_calls],
            preview=_preview(event.content),
        )
        _close_step(step, clock)
        if event.cost_usd is None:
            run.unknown_cost_calls += 1
        else:
            run.spent_usd += event.cost_usd
        run.status = RUNNING
        return
    if isinstance(event, ToolCallEvent):
        _open_step(
            run,
            {
                "kind": "tool",
                "name": event.name,
                "tool_call_id": event.tool_call_id,
                "arguments": _argument_preview(event.arguments),
                "ok": None,
            },
            clock,
        )
        return
    if isinstance(event, ToolResultEvent):
        step = _find_tool_step(run, event.tool_call_id)
        if step is None:
            _open_step(run, {"kind": "tool", "name": event.name, "ok": None}, clock)
            step = run.steps[-1]
        step["ok"] = event.ok
        step["output"] = _preview(event.output)
        _close_step(step, clock)
        return
    if isinstance(event, ApprovalRequiredEvent):
        run.status = AWAITING
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
            "error": _preview(event.error),
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
