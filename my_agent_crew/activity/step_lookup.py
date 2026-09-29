"""Finding a step on a run: the model step still open, the tool step a result closes, and
whether an open model step is still waiting on a route that took over after a fallback."""

from __future__ import annotations

from typing import Any

from my_agent_crew.store.runs import RunRecord

# The clock reading a step opened at, kept on the step until it closes.
CLOCK_KEY = "_clock"


def pending_model_step(run: RunRecord) -> dict[str, Any] | None:
    if run.steps and run.steps[-1].get("kind") == "model" and CLOCK_KEY in run.steps[-1]:
        return run.steps[-1]
    return None


def unsent_after_fallback(run: RunRecord) -> bool:
    pending = pending_model_step(run)
    if pending is None or len(run.steps) < 2 or run.steps[-2].get("kind") != "fallback":
        return False
    return pending.get("first_token_ms") is None and not pending.get("thinking")


def find_tool_step(run: RunRecord, tool_call_id: str) -> dict[str, Any] | None:
    for step in reversed(run.steps):
        if step.get("kind") == "tool" and step.get("tool_call_id") == tool_call_id:
            return step
    return None
