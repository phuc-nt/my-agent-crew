"""Events of a model call that changed route, defined apart from `events` so that file
stays inside its budget. Import them from `my_agent_crew.agent.events`."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouteFallbackEvent:
    """One route failed before answering and the next one is being tried."""

    provider: str
    model: str
    error: str


@dataclass(frozen=True)
class EscalatedEvent:
    """A stuck turn moved to its agent's escalation route, named here, and stays on it to
    its end (`agent/escalation.py`)."""

    reason: str  # "loop" (the same tool calls over and over) | "error" (every route failed)
    provider: str
    model: str
    # What the routes the turn was on answered with, when it moved for an error.
    error: str = ""
