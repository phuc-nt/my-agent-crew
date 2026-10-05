"""Steps of a model call that changed route: a route that failed before answering with the
next one tried, and a stuck turn moved to its agent's escalation route."""

from __future__ import annotations

from typing import Any

from my_agent_crew.activity.step_clock import close_step, open_model_step, open_step
from my_agent_crew.activity.step_lookup import CLOCK_KEY, pending_model_step
from my_agent_crew.activity.step_previews import preview
from my_agent_crew.agent.events import EscalatedEvent, RouteFallbackEvent
from my_agent_crew.store.runs import RunRecord


def apply_route_event(
    run: RunRecord, event: RouteFallbackEvent | EscalatedEvent, clock: float
) -> None:
    # The request's model step was timing a route that will not answer. That wait belongs
    # to the step that says so, which takes the model step's place and its clock.
    pending = pending_model_step(run)
    if pending is not None:
        run.steps.pop()
    step: dict[str, Any]
    if isinstance(event, RouteFallbackEvent):
        step = {"kind": "fallback", "provider": event.provider, "model": event.model}
        step["error"] = preview(event.error)
    else:
        step = {"kind": "escalation", "reason": event.reason}
        step |= {"provider": event.provider, "model": event.model}
        if event.error:
            step["error"] = preview(event.error)
    open_step(run, step, pending[CLOCK_KEY] if pending is not None else clock)
    close_step(step, clock)
    # After a fallback the same call goes on to the next route, so the model step moves
    # behind it to time that one: a run that recovered keeps one model step per call and
    # none of them left open. A turn that moved makes a new call, which opens its own.
    if pending is not None and isinstance(event, RouteFallbackEvent):
        open_model_step(run, clock)
