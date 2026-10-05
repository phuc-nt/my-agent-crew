"""Which pieces of a tool call being written a turn shows, and how often. A canvas write is
one long argument that nobody could see until the model had finished it; here its pieces
become events for the tab that is waiting. Only the two tools that write a whole document are
let through, so no other call's arguments go out piece by piece while they are written."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from my_agent_crew.agent.events import ToolCallDeltaEvent
from my_agent_crew.llm.types import ToolCallDelta

DRAFT_TOOLS = frozenset({"artifact_create", "artifact_rewrite"})
# How long a call's pieces are gathered between two events. A stream sends a piece every few
# words; the pane that draws them parses and lays out the whole document each time.
DRAFT_INTERVAL_S = 3.0


@dataclass
class _Slot:
    """One call of the answer being written: what gathered since its last event, when that
    event went out (None before the first), and whether the call was left alone for good."""

    held: str = ""
    last_emit: float | None = None
    dropped: bool = False


class DraftPreview:
    """Turns the pieces of one model call into preview events. `emitted` says whether any went
    out since the last `reset`. What is still held when the call ends is never sent: the
    whole call arrives with the answer."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._slots: dict[int, _Slot] = {}
        self.emitted = False

    def feed(self, item: ToolCallDelta, attempt: int) -> ToolCallDeltaEvent | None:
        """The event this piece brings out, if one is due. A call's first piece goes out as
        soon as the call is named, later ones once per interval with all that gathered. A
        call named as any other tool is dropped, and stays dropped if the name changes."""
        slot = self._slots.setdefault(item.index, _Slot())
        if slot.dropped:
            return None
        slot.held += item.chunk
        if not item.name:  # a stream may send arguments ahead of the name
            return None
        if item.name not in DRAFT_TOOLS:
            slot.dropped = True
            return None
        now = self._clock()
        if slot.last_emit is not None and now - slot.last_emit < DRAFT_INTERVAL_S:
            return None
        chunk, slot.held, slot.last_emit = slot.held, "", now
        self.emitted = True
        return ToolCallDeltaEvent(index=item.index, name=item.name, chunk=chunk, attempt=attempt)

    def reset(self) -> None:
        """Forgets every call: the next piece belongs to a new attempt at the answer."""
        self._slots.clear()
        self.emitted = False
