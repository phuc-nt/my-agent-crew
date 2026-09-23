"""The polling half of a Telegram channel: the long-poll loop, its start and its stop.

Stopping is careful because a channel is now stopped while the server runs, whenever the
bot's token or chat is changed from the web. The offset of a message is written before
the message is handled, so a stop that cut a turn off would lose that message for good;
and a successor that began polling before this loop ended would share the bot with it,
which Telegram answers with a 409 on both. So a stop lets the message in hand finish
(for a while — a turn is not waited on forever) and returns only once the loop is over.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from my_agent_crew.channels.telegram_albums import complete_album, group_updates
from my_agent_crew.channels.telegram_api import CONFLICT_STATUS, TelegramApi, TelegramError
from my_agent_crew.channels.telegram_commands import menu_for
from my_agent_crew.channels.telegram_inbound import handle_updates
from my_agent_crew.channels.telegram_offset import write_offset

if TYPE_CHECKING:
    from my_agent_crew.agent.loop import AgentDeps

logger = logging.getLogger(__name__)
RETRY_SECONDS = 5
# How long a stop waits for a message being handled before cutting it off.
STOP_GRACE_SECONDS = 30.0


class TelegramPolling:
    agent_id: str
    _api: TelegramApi
    _offset: int
    _offset_path: Path
    _menu_registered: bool = False
    _task: asyncio.Task[None] | None = None
    _stopping: bool = False
    _handling: bool = False

    @property
    def deps(self) -> AgentDeps:
        raise NotImplementedError

    def start(self) -> None:
        if self._task is None:
            self._stopping = False
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        self._stopping = True
        if self._handling:
            await asyncio.wait({task}, timeout=STOP_GRACE_SECONDS)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise  # the stop itself was cancelled, not only the loop

    async def _loop(self) -> None:
        while not self._stopping:
            try:
                await self.register_menu()
                await self.poll_once()
                continue
            except TelegramError as exc:
                if exc.status == CONFLICT_STATUS:
                    logger.warning("telegram %s: another poller holds this bot", self.agent_id)
                else:
                    logger.warning("telegram %s: %s", self.agent_id, exc)
            except Exception:
                logger.exception("telegram %s: update failed", self.agent_id)
            await asyncio.sleep(RETRY_SECONDS)

    async def register_menu(self) -> None:
        """Publishes the slash-command menu once per process; retried with the poll loop."""
        if not self._menu_registered:
            await self._api.set_my_commands(menu_for(self.deps.agent.commands))
            self._menu_registered = True
            logger.info("telegram %s: command menu registered", self.agent_id)

    async def poll_once(self) -> int:
        """Fetches pending updates and handles them, an album of photos as one message;
        the offset moves before handling so a message that crashes the handler is not
        replayed forever."""
        updates = await complete_album(self._api, await self._api.get_updates(self._offset))
        self._handling = True
        try:
            for group in group_updates(updates):
                if self._stopping:
                    break  # left unconfirmed, so the next poller gets it
                self._offset = int(group[-1]["update_id"]) + 1
                write_offset(self._offset_path, self._offset, self._api.bot)
                await handle_updates(self, group)  # type: ignore[arg-type]
        finally:
            self._handling = False
        return len(updates)

    async def handle(self, update: dict[str, Any]) -> None:
        await handle_updates(self, [update])  # type: ignore[arg-type]
