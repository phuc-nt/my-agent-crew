"""Turns the server reads to their end, whoever is watching.

A turn is a generator: it advances only while someone reads it. The web used to be that
reader, so closing the tab, switching conversation or losing the connection ended the turn
halfway. Here the server is the reader, in a task of its own, and the tab that sent the
message is only the first to watch (`activity/turn_watch.py`). Telegram, jobs and the queue
drain already read their turns on the server and do not come through here."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from my_agent_crew.activity.turn_watch import Frame, Turn, TurnWatch
from my_agent_crew.agent.events import Event

logger = logging.getLogger(__name__)


class TurnHost:
    def __init__(self, turns: TurnWatch):
        self._turns = turns
        self._tasks: set[asyncio.Task[None]] = set()
        # The turn being read for each conversation, for `cancel` to reach.
        self._reading: dict[str, asyncio.Task[None]] = {}

    def run(self, conv_id: str, events: AsyncIterator[Event]) -> AsyncIterator[Frame]:
        """Starts reading the turn and returns its sender's view of it: every event from
        the first, since the sender is registered before the turn takes a step. Not reading
        that view to its end stops the watching and nothing else."""
        turn = self._turns.open(conv_id)
        frames = turn.join(behind=False)
        task = asyncio.get_running_loop().create_task(self._read(conv_id, turn, events))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        self._reading[conv_id] = task
        return frames

    async def _read(self, conv_id: str, turn: Turn, events: AsyncIterator[Event]) -> None:
        try:
            async for _ in events:
                pass
        except Exception:
            logger.exception("turn of %s: failed while the server was reading it", conv_id)
        finally:
            if self._reading.get(conv_id) is asyncio.current_task():
                del self._reading[conv_id]
            # A turn cut off before its first read began nothing, so nothing else ends it.
            self._turns.end(conv_id, turn)

    def cancel(self, conv_id: str) -> bool:
        """Stops the turn being read for the conversation, which leaves its run marked as
        interrupted. False when there is none."""
        task = self._reading.pop(conv_id, None)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def stop(self) -> None:
        """Ends every turn in flight, for a server that is shutting down."""
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._reading.clear()
