"""A stuck turn's one move to another model.

An agent may name one `escalation_route` in its `agent.yaml`. A turn asks the agent's usual
routes until it is stuck in one of two ways: the loop guard is about to halt it for making
the same tool calls over and over, or a model call failed on every route the chain had, its
own retry included, with nothing of that call put in front of a reader. Then the turn moves
to the escalation route, once, and stays on it to its end. The next turn starts on the usual
routes again, and so does a turn carried on after a pause or a restart.

Nothing else moves a turn. The step limit and the cost cap end it on whichever route it is
on, and a turn with no model call left is not moved: it ends the way it would have, so the
reason it ended is the real one.

Off unless the agent names a route. It is a way out for a turn that is stuck, not a way to
send some kinds of work to some models: which model answers is still one list per agent.
"""

from __future__ import annotations

from dataclasses import dataclass

from my_agent_crew.agent.events import (
    EscalatedEvent,
    Event,
    ModelCallEvent,
    TextDeltaEvent,
    ToolCallDeltaEvent,
)
from my_agent_crew.llm.provider import ProviderChain

LOOP, ERROR = "loop", "error"


@dataclass
class Escalation:
    """Which chain a turn asks, and whether it has moved."""

    usual: ProviderChain
    spare: ProviderChain | None = None
    moved: bool = False
    # What the model call under way has put in front of a reader: words of an answer, which
    # cannot be taken back, and pieces of a canvas being written, which an attempt the chain
    # gave up calls off. A call that showed either is not asked again somewhere else: the
    # reader would see the seam.
    _text: bool = False
    _draft: bool = False

    @property
    def chain(self) -> ProviderChain:
        return self.spare if self.moved and self.spare is not None else self.usual

    def watch(self, event: Event) -> None:
        if isinstance(event, ModelCallEvent) and event.stage == "sent":
            self._text = self._draft = False
        elif isinstance(event, TextDeltaEvent):
            self._text = True
        elif isinstance(event, ToolCallDeltaEvent):
            self._draft = bool(event.name)  # an event with no name drops what was drawn

    def move(self, reason: str, calls_left: int, error: str = "") -> EscalatedEvent | None:
        """Moves the turn and returns the event that says so, or None when it stays where it
        is: the agent names no route, the turn has moved already, it has no model call left
        to make there, or the call that failed had begun to show."""
        if self.spare is None or self.moved or calls_left < 1:
            return None
        if reason == ERROR and (self._text or self._draft):
            return None
        self.moved = True
        route = self.spare.routes[0]
        return EscalatedEvent(
            reason=reason, provider=route.provider, model=route.model, error=error
        )
