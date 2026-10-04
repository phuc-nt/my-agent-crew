"""Outbound half of a Telegram channel: replies, `MEDIA:` photos and `FILE:` documents to
the one allowed chat, plus the "typing…" indicator shown while a turn runs. Telegram drops
the indicator after about five seconds, so it is re-sent on an interval until the reply
goes out. The files themselves are sent by `telegram_files`, and the canvases a line names
in place of a file by `telegram_canvas_file`."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from my_agent_crew import texts
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.channels.telegram_api import TelegramApi, TelegramError, split_reply
from my_agent_crew.channels.telegram_canvas_file import send_canvases
from my_agent_crew.channels.telegram_files import TelegramFiles
from my_agent_crew.reply_attachments import artifact_ref
from my_agent_crew.store.runs import DONE, FAILED, HALTED, RunRecord

logger = logging.getLogger(__name__)
TYPING_INTERVAL_SECONDS = 4
# How long the first "typing…" may hold up the turn; one Telegram does not answer is
# given up so the turn still runs.
TYPING_FIRST_TIMEOUT_SECONDS = 3.0


def _ending(run: RunRecord) -> str:
    """Why a run ended, in words: a halted run's summary is the loop's code for it, a
    failed one's is already the error message."""
    if run.status == HALTED:
        return texts.HALT_REASONS.get(run.summary, run.summary or run.status)
    return run.summary or run.status


class TelegramOutbound:
    def __init__(self, deps: AgentDeps, api: TelegramApi, chat_id: int, prefix: str = ""):
        """`prefix` is a first line naming the agent, used when several share the bot."""
        self._deps = deps
        self._api = api
        self._chat_id = chat_id
        self._prefix = prefix
        self._files = TelegramFiles(deps, api, chat_id)

    @property
    def agent_id(self) -> str:
        return self._deps.agent.id

    async def deliver(self, conv_id: str) -> bool:
        """Sends every assistant text of the conversation's last turn (the messages after
        the last user message, in order); False when there is none yet. Text written next
        to a tool call counts: a brief often ends with a bare `MEDIA:` message."""
        parts: list[str] = []
        expired: list[str] = []
        for stored in reversed(self._deps.store.history(conv_id)):
            message = stored.message
            if message.role == "user":
                break
            if message.role == "assistant" and message.content.strip():
                parts.append(message.content.strip())
            elif message.role == "tool" and message.content == texts.EXPIRED_TOOL:
                expired.append(message.name or "")
        run = self._deps.store.runs.latest_for_conversation(conv_id)
        # A refusal nobody chose deserves a line of its own: the answer below was shaped
        # by a guard that timed out, not by the person.
        for name in reversed(expired):
            await self.send(texts.TELEGRAM_APPROVAL_EXPIRED.format(name=name))
        if parts:
            await self.send("\n\n".join(reversed(parts)))
            # A run out of steps or budget still leaves text behind; without this the
            # half-finished answer reads like a complete one.
            if run is not None and run.status in (HALTED, FAILED):
                await self.send(
                    texts.TELEGRAM_RUN_CUT_SHORT.format(reason=_ending(run), spent=run.spent_usd)
                )
            return True
        if run is None:
            logger.info("telegram %s: nothing to deliver for %s", self.agent_id, conv_id)
            return False
        if run.status == DONE:
            # The job ran to the end and produced no text. Saying so beats a brief that
            # simply never arrives, which looks the same as a broken schedule.
            logger.info("telegram %s: run for %s finished empty", self.agent_id, conv_id)
            await self.send(texts.REPLY_EMPTY.format(steps=len(run.steps)))
            return True
        await self.send(texts.TELEGRAM_RUN_UNFINISHED.format(reason=_ending(run)))
        return True

    async def send(self, text: str, conv_id: str | None = None) -> None:
        """The prose, then the workspace files its lines name, then the canvases they name.
        `conv_id` is the conversation the reply belongs to, which decides the canvases it may
        send. It comes with each call: one sender serves an agent's every turn."""
        prose, media, files = split_reply(text)
        if prose:
            await self._say(prose)
        for relative in media:
            if artifact_ref(relative) is None:
                await self._files.photo(relative)
        for relative in files:
            if artifact_ref(relative) is None:
                await self._files.document(relative)
        refs = [ref for ref in map(artifact_ref, (*media, *files)) if ref is not None]
        await send_canvases(self._deps, self._api, self._chat_id, refs, conv_id)

    async def _say(self, prose: str) -> None:
        if self._prefix:
            prose = f"{self._prefix}\n{prose}"
        await self._api.send_message(self._chat_id, prose)
        logger.info("telegram %s: sent %d chars", self.agent_id, len(prose))

    @asynccontextmanager
    async def typing(self, interval: float = TYPING_INTERVAL_SECONDS) -> AsyncIterator[None]:
        """Shows the typing indicator at once and keeps it alive for the duration of the
        block; a failed `sendChatAction` is only logged, it never breaks the turn, and a
        first one that hangs is given up after a while."""
        try:
            await asyncio.wait_for(self._show_typing(), TYPING_FIRST_TIMEOUT_SECONDS)
        except TimeoutError:
            logger.warning("telegram %s: typing indicator did not answer", self.agent_id)
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
