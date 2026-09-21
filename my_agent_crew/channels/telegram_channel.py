"""One Telegram bot's channel: messages from the configured chat become turns of the
master's per-day conversation, run through the same `Inbound` gate as the web UI, so the
chat and the web are the same mechanism — talk to the master, which delegates. Every agent
is known to the channel so `deliver` can push a crew member's scheduled brief to the chat
under that member's name. `telegram_inbound` reads each update (slash commands,
attachments). Only one process may poll a bot: a 409 means another is."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.events import Event
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agent.turn_context import TELEGRAM
from my_agent_crew.channels.telegram_albums import complete_album, group_updates
from my_agent_crew.channels.telegram_api import CONFLICT_STATUS, TelegramApi, TelegramError
from my_agent_crew.channels.telegram_commands import menu_for
from my_agent_crew.channels.telegram_inbound import handle_updates
from my_agent_crew.channels.telegram_offset import read_offset, write_offset
from my_agent_crew.channels.telegram_outbound import TelegramOutbound
from my_agent_crew.inbound import Inbound, InboundBusy, collect_reply
from my_agent_crew.store import Conversation, Store

logger = logging.getLogger(__name__)
RETRY_SECONDS = 5
TITLE = texts.TELEGRAM_CONVERSATION_TITLE


def channel_key(chat_id: int) -> str:
    """The `conversations.channel` value of the chat, shared by every conversation it opens."""
    return f"telegram:{chat_id}"


class TelegramChannel:
    def __init__(
        self,
        agents: Mapping[str, AgentDeps],
        agent_id: str,
        hub: ActivityHub,
        api: TelegramApi,
        chat_id: int,
        offset_path: Path,
        clock: Any = datetime.now,
    ):
        """`agent_id` is the agent the chat talks to; `agents` is everyone whose
        conversations may be delivered here."""
        if agent_id not in agents:
            raise ValueError(f"telegram channel: agent {agent_id!r} is not among the agents")
        self.agents: dict[str, AgentDeps] = dict(agents)
        self.agent_id = agent_id
        self.hub, self.inbound = hub, Inbound(self.agents, hub)
        self._api, self.chat_id = api, chat_id
        self._offset_path, self._clock = offset_path, clock
        self._outbound: dict[str, TelegramOutbound] = {}
        self._offset = read_offset(offset_path)
        self._menu_registered = False
        self._task: asyncio.Task[None] | None = None

    def set_on_replaced(self, callback: Callable[[AgentDeps, str], None]) -> None:
        """Set after construction: the scheduler that recaps is built after the channel."""
        self.inbound.on_replaced = callback

    @property
    def deps(self) -> AgentDeps:
        return self.agents[self.agent_id]

    @property
    def store(self) -> Store:
        return self.deps.store

    @property
    def channel_key(self) -> str:
        return channel_key(self.chat_id)

    @property
    def api(self) -> TelegramApi:
        return self._api

    def now(self) -> datetime:
        return self._clock()

    def outbound(self, agent_id: str | None = None) -> TelegramOutbound:
        """The sender for an agent's text, built on first use. The master speaks as the bot;
        anyone else's brief opens with `[Name]`, so a delivered morning brief reads as the
        member's, not as an answer from the master."""
        agent_id = agent_id or self.agent_id
        if agent_id not in self._outbound:
            deps = self.agents[agent_id]
            prefix = ""
            if agent_id != self.agent_id:
                prefix = texts.TELEGRAM_AGENT_PREFIX.format(name=deps.agent.name)
            self._outbound[agent_id] = TelegramOutbound(deps, self._api, self.chat_id, prefix)
        return self._outbound[agent_id]

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while True:
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
        for group in group_updates(updates):
            self._offset = int(group[-1]["update_id"]) + 1
            write_offset(self._offset_path, self._offset)
            await handle_updates(self, group)
        return len(updates)

    async def handle(self, update: dict[str, Any]) -> None:
        await handle_updates(self, [update])

    async def chat(self, text: str) -> None:
        conv = self.conversation()
        try:
            events = self.inbound.stream(conv.id, text, source=TELEGRAM)
        except InboundBusy:
            return await self.say(texts.TELEGRAM_BUSY)
        await self.outbound().send(await self.answer(events))

    async def answer(self, events: AsyncIterator[Event]) -> str:
        """The turn as one message, read with "typing…" showing."""
        async with self.outbound().typing():
            reply = await collect_reply(events, texts.TELEGRAM_APPROVAL_HOW)
        return reply.text

    async def say(self, text: str) -> None:
        """A message from the bot itself, not from an agent."""
        await self._api.send_message(self.chat_id, text)

    def conversation(self) -> Conversation:
        return self.inbound.conversation_for(self.agent_id, self.channel_key, self._clock, TITLE)

    def open_conversation(self) -> Conversation:
        return self.inbound.open_conversation(self.agent_id, self.channel_key, self._clock, TITLE)

    async def deliver(self, conv_id: str) -> bool:
        """A conversation's last reply to the chat, under its agent's name when that is not
        the master; False when the conversation belongs to an agent this runtime lacks."""
        agent_id = self.store.get(conv_id).agent_id
        if agent_id not in self.agents:
            logger.warning(
                "telegram: conversation %s belongs to unknown agent %s", conv_id, agent_id
            )
            return False
        return await self.outbound(agent_id).deliver(conv_id)
