"""Watching a turn while it runs. Every tracked turn passes its events on here, by
conversation, so whoever opens the conversation late sees the turn that is under way and
not only what it has stored so far.

What a turn has stored is in the conversation. What it has not is the answer being written:
the words streamed since the last stored message, whether the model is thinking, the canvas
it is drafting. That is kept here, in memory, for as long as the turn runs, and nowhere else:
a restart loses it, and the stored conversation is the whole truth again.

A watcher reads frames: the turn's events, and a `Resync` wherever it must first rebuild its
view from the stored conversation. One that joins late starts with a `Resync`. One that falls
too far behind is handed a `Resync` in place of the events it could not keep up with, so a
stalled tab holds a bounded number of events and is never cut off. A `Resync` says whether
the turn is still under way: the events it stands in for may have been the turn's last."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass

from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    HaltedEvent,
    ModelCallEvent,
    TextDeltaEvent,
    ThinkingEvent,
    ToolCallDeltaEvent,
)

# How many events a watcher may leave unread before it is resynced instead.
WATCH_BACKLOG = 256
# After these nothing is being written: the answer is stored, or the turn gave it up.
_SETTLED = (AssistantMessageEvent, DoneEvent, HaltedEvent, ErrorEvent, ApprovalRequiredEvent)


@dataclass(frozen=True)
class Resync:
    """Read the conversation as it is stored now, then apply `replay`, then go on with the
    frames that follow. It is built as it is handed over: whoever receives it must read the
    stored conversation before it awaits anything, or events could fall between the two."""

    replay: tuple[Event, ...]
    under_way: bool = True


Frame = Event | Resync


class _Watcher:
    def __init__(self, behind: bool):
        self.events: deque[Event] = deque()
        self.behind = behind
        self.wake = asyncio.Event()


class Turn:
    """One turn being watched: what it is writing now, and who reads along."""

    def __init__(self) -> None:
        self.begun = False
        self._ended = False
        self._watchers: set[_Watcher] = set()
        self._text = ""
        self._thinking = False
        # A canvas being drafted, by its place in the answer: (name, arguments so far, attempt).
        self._drafts: dict[int, tuple[str, str, int]] = {}

    def reset(self) -> None:
        self._text, self._thinking = "", False
        self._drafts.clear()

    def publish(self, event: Event) -> None:
        self._note(event)
        for watcher in self._watchers:
            if watcher.behind:
                continue  # it rebuilds from what is stored; nothing to hold for it
            if len(watcher.events) >= WATCH_BACKLOG:
                watcher.events.clear()
                watcher.behind = True
            else:
                watcher.events.append(event)
            watcher.wake.set()

    def _note(self, event: Event) -> None:
        """Keeps what the answer being written looks like, the way a tab reading every
        event would: a stored message or the turn's end ends it, and anything the model
        does next ends its thinking."""
        if isinstance(event, _SETTLED):
            self.reset()
        elif isinstance(event, ThinkingEvent):
            self._thinking = True
        elif isinstance(event, ToolCallDeltaEvent):
            if any(attempt != event.attempt for _, _, attempt in self._drafts.values()):
                self._drafts.clear()  # the answer was started over
            if event.name:
                _, written, _ = self._drafts.get(event.index, ("", "", 0))
                self._drafts[event.index] = (event.name, written + event.chunk, event.attempt)
        elif not isinstance(event, ModelCallEvent):
            self._thinking = False
            if isinstance(event, TextDeltaEvent):
                self._text += event.text

    def replay(self) -> tuple[Event, ...]:
        """The answer being written, as the fewest events that draw it again."""
        events: list[Event] = []
        if self._text:
            events.append(TextDeltaEvent(text=self._text))
        if self._thinking:
            events.append(ThinkingEvent())
        for index, (name, written, attempt) in sorted(self._drafts.items()):
            events.append(
                ToolCallDeltaEvent(index=index, name=name, chunk=written, attempt=attempt)
            )
        return tuple(events)

    def join(self, behind: bool) -> AsyncIterator[Frame]:
        """A watcher registered now, whenever its frames are first read. `behind` is for one
        who was not there from the turn's first event: its first frame is a `Resync`."""
        watcher = _Watcher(behind)
        self._watchers.add(watcher)
        return self._frames(watcher)

    async def _frames(self, watcher: _Watcher) -> AsyncIterator[Frame]:
        try:
            while True:
                if watcher.behind:
                    watcher.behind = False
                    yield Resync(self.replay(), under_way=not self._ended)
                elif watcher.events:
                    yield watcher.events.popleft()
                elif self._ended:
                    return
                else:
                    watcher.wake.clear()
                    await watcher.wake.wait()
        finally:
            self._watchers.discard(watcher)

    def close(self) -> None:
        """No more events will come: each watcher reads what it still holds, then stops."""
        self._ended = True
        for watcher in self._watchers:
            watcher.wake.set()


class TurnWatch:
    def __init__(self) -> None:
        self._turns: dict[str, Turn] = {}

    def open(self, conversation_id: str) -> Turn:
        """A turn about to start, for whoever must watch it from its first event."""
        self.end(conversation_id)  # nothing of an earlier turn is left to watch
        turn = self._turns[conversation_id] = Turn()
        return turn

    def begin(self, conversation_id: str) -> Turn:
        """The turn that starts now: the one opened for it, or a new one."""
        turn = self._turns.get(conversation_id)
        if turn is None or turn.begun:
            turn = self.open(conversation_id)
        turn.begun = True
        return turn

    def end(self, conversation_id: str, turn: Turn | None = None) -> None:
        """Lets the turn's watchers go. Given a turn, ends that one only: a later turn of
        the conversation is not the caller's to end."""
        current = self._turns.get(conversation_id)
        if current is None or (turn is not None and current is not turn):
            return
        del self._turns[conversation_id]
        current.close()

    def join(self, conversation_id: str) -> AsyncIterator[Frame] | None:
        """Frames of the turn under way, for one who arrives late. None when the
        conversation has no turn to watch."""
        turn = self._turns.get(conversation_id)
        return None if turn is None else turn.join(behind=True)
