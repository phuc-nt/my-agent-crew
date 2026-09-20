"""Outbound half of a Telegram channel: replies and `MEDIA:` photos to the one allowed
chat, plus the "typing…" indicator shown while a turn runs. Telegram drops the indicator
after about five seconds, so it is re-sent on an interval until the reply goes out."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from my_agent_crew import texts
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.channels.telegram_api import TelegramApi, TelegramError, split_reply
from my_agent_crew.store.runs import DONE, FAILED, HALTED
from my_agent_crew.tools.registry import ToolError
from my_agent_crew.tools.workspace import resolve_inside

logger = logging.getLogger(__name__)
TYPING_INTERVAL_SECONDS = 4


class TelegramOutbound:
    def __init__(self, deps: AgentDeps, api: TelegramApi, chat_id: int, prefix: str = ""):
        """`prefix` is a first line naming the agent, used when several share the bot."""
        self._deps = deps
        self._api = api
        self._chat_id = chat_id
        self._prefix = prefix

    @property
    def agent_id(self) -> str:
        return self._deps.agent.id

    async def deliver(self, conv_id: str) -> bool:
        """Sends every assistant text of the conversation's last turn (the messages after
        the last user message, in order); False when there is none yet. Text written next
        to a tool call counts: a brief often ends with a bare `MEDIA:` message."""
        parts: list[str] = []
        for stored in reversed(self._deps.store.history(conv_id)):
            message = stored.message
            if message.role == "user":
                break
            if message.role == "assistant" and message.content.strip():
                parts.append(message.content.strip())
        run = self._deps.store.runs.latest_for_conversation(conv_id)
        if parts:
            await self.send("\n\n".join(reversed(parts)))
            # A run out of steps or budget still leaves text behind; without this the
            # half-finished answer reads like a complete one.
            if run is not None and run.status in (HALTED, FAILED):
                await self.send(
                    texts.TELEGRAM_RUN_CUT_SHORT.format(
                        reason=run.summary or run.status, spent=run.spent_usd
                    )
                )
            return True
        if run is None:
            logger.info("telegram %s: nothing to deliver for %s", self.agent_id, conv_id)
            return False
        if run.status == DONE:
            # The job ran to the end and produced no text. Saying so beats a brief that
            # simply never arrives, which looks the same as a broken schedule.
            logger.info("telegram %s: run for %s finished empty", self.agent_id, conv_id)
            await self.send(texts.TELEGRAM_TURN_EMPTY.format(steps=len(run.steps)))
            return True
        await self.send(texts.TELEGRAM_RUN_UNFINISHED.format(reason=run.summary or run.status))
        return True

    async def send(self, text: str) -> None:
        prose, media = split_reply(text)
        if prose:
            if self._prefix:
                prose = f"{self._prefix}\n{prose}"
            await self._api.send_message(self._chat_id, prose)
            logger.info("telegram %s: sent %d chars", self.agent_id, len(prose))
        for relative in media:
            try:
                path = resolve_inside(self._deps.agent.workspace, relative)
                if not path.is_file():
                    raise ToolError(texts.WORKSPACE_NOT_FOUND.format(path=relative))
                await self._api.send_photo(self._chat_id, path)
                logger.info("telegram %s: sent photo %s", self.agent_id, relative)
            except (ToolError, OSError, TelegramError) as exc:
                logger.warning("telegram %s: photo %s: %s", self.agent_id, relative, exc)
                await self._api.send_message(
                    self._chat_id, texts.TELEGRAM_MEDIA_MISSING.format(path=relative)
                )

    @asynccontextmanager
    async def typing(self, interval: float = TYPING_INTERVAL_SECONDS) -> AsyncIterator[None]:
        """Shows the typing indicator at once and keeps it alive for the duration of the
        block; a failed `sendChatAction` is only logged, it never breaks the turn."""
        await self._show_typing()
        task = asyncio.create_task(self._keep_typing(interval))
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _keep_typing(self, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            await self._show_typing()

    async def _show_typing(self) -> None:
        try:
            await self._api.send_chat_action(self._chat_id)
        except TelegramError as exc:
            logger.warning("telegram %s: typing indicator: %s", self.agent_id, exc)
