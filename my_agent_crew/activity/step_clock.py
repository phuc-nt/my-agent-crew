"""Timing a step on a run: it is opened on the clock, which it keeps until it is closed with
the time that passed."""

from __future__ import annotations

from typing import Any

from my_agent_crew.activity.step_lookup import CLOCK_KEY
from my_agent_crew.store.runs import RunRecord


def open_step(run: RunRecord, step: dict[str, Any], clock: float) -> None:
    step[CLOCK_KEY] = clock
    step["duration_ms"] = None
    run.steps.append(step)


def close_step(step: dict[str, Any], clock: float) -> None:
    started = step.pop(CLOCK_KEY, clock)
    # A paused run outlives its process, and a reboot restarts the clock it was timed on.
    step["duration_ms"] = max(0, int((clock - started) * 1000))


def instant(run: RunRecord, step: dict[str, Any], clock: float) -> None:
    """A step with no duration worth reading, opened and closed on the same clock."""
    open_step(run, step, clock)
    close_step(step, clock)


def open_model_step(run: RunRecord, clock: float) -> None:
    open_step(run, {"kind": "model", "chars": 0, "first_token_ms": None}, clock)
