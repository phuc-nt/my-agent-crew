"""The turns a Telegram channel runs in the background. The poll loop does not wait for a
turn to end before it reads the next update: `/status` answers while a turn runs, and a
second message waits its turn or steers the running one instead of lying unread. The channel
keeps every turn it starts, so a stop can wait for them and cut off what outlives the wait."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)


class TelegramTurns:
    agent_id: str
    _turns: set[asyncio.Task[None]] | None = None
    # Set by the poll loop while it hands a message over: its offset is already written, so
    # a stop that cut it off would lose the message.
    _handling: bool = False

    @property
    def turns(self) -> set[asyncio.Task[None]]:
        if self._turns is None:
            self._turns = set()
        return self._turns

    def spawn(self, turn: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        task = asyncio.create_task(turn)
        self.turns.add(task)
        task.add_done_callback(self._turn_done)
        return task

    def _turn_done(self, task: asyncio.Task[None]) -> None:
        self.turns.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("telegram %s: a turn failed", self.agent_id, exc_info=task.exception())

    async def wait_for_turns(self, poll: asyncio.Task[None], grace: float) -> bool:
        """Waits up to `grace` seconds for every turn, and for the poll loop while it hands
        a message over; a turn that message starts is waited on too. True when something
        was still running at the deadline."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + grace
        while True:
            running = {task for task in self.turns if not task.done()}
            if self._handling and not poll.done():
                running.add(poll)
            left = deadline - loop.time()
            if not running or left <= 0:
                return bool(running)
            await asyncio.wait(running, timeout=left, return_when=asyncio.FIRST_COMPLETED)

    async def cancel_turns(self) -> None:
        running = [task for task in self.turns if not task.done()]
        for task in running:
            task.cancel()
        await asyncio.gather(*running, return_exceptions=True)
