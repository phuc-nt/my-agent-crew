"""One Telegram bot's channel: messages from the configured chat become turns of a
per-day conversation, run through the same `Inbound` gate as the web UI. A bot may serve
several agents: `@<agent id>` picks the agent for that message and the ones after it.
Slash commands are answered by `telegram_commands` without a model call. `deliver` pushes
a scheduled brief to the chat. Only one process may poll a bot: a 409 means another is."""

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
from my_agent_crew.channels import telegram_conversations as conversations
from my_agent_crew.channels.telegram_api import CONFLICT_STATUS, TelegramApi, TelegramError
from my_agent_crew.channels.telegram_commands import (
    MENU,
    answer_command,
    bot_answers,
    parse_command,
    route_mention,
)
from my_agent_crew.channels.telegram_offset import read_offset, write_offset
from my_agent_crew.channels.telegram_outbound import TelegramOutbound
from my_agent_crew.inbound import Inbound, InboundBusy, collect_reply
from my_agent_crew.store import Conversation, Store

logger = logging.getLogger(__name__)
RETRY_SECONDS = 5
TITLE = texts.TELEGRAM_CONVERSATION_TITLE


class TelegramChannel:
    def __init__(
        self,
        agents: Mapping[str, AgentDeps],
        hub: ActivityHub,
        api: TelegramApi,
        chat_id: int,
        offset_path: Path,
        clock: Any = datetime.now,
    ):
        if not agents:
            raise ValueError("a telegram channel needs at least one agent")
        self.agents: dict[str, AgentDeps] = dict(agents)
        self.hub, self.inbound = hub, Inbound(self.agents, hub)
        self._api, self.chat_id = api, chat_id
        self._offset_path, self._clock = offset_path, clock
        self._outbound = {
            agent_id: TelegramOutbound(deps, api, chat_id, prefix=self._prefix(deps))
            for agent_id, deps in self.agents.items()
        }
        self._offset = read_offset(offset_path)
        self._menu_registered = False
        self._task: asyncio.Task[None] | None = None

    def set_on_replaced(self, callback: Callable[[AgentDeps, str], None]) -> None:
        """Set after construction: the scheduler that recaps is built after the channels."""
        self.inbound.on_replaced = callback

    @property
    def shared(self) -> bool:
        return len(self.agents) > 1

    @property
    def label(self) -> str:
        return "+".join(self.agents)

    @property
    def store(self) -> Store:
        return next(iter(self.agents.values())).store

    @property
    def channel_key(self) -> str:
        return conversations.channel_key(self.chat_id)

    @property
    def agent_id(self) -> str:  # the agent a message without a mention goes to
        return conversations.current_agent(self.store, self.agents, self.chat_id)

    @property
    def deps(self) -> AgentDeps:
        return self.agents[self.agent_id]

    def _prefix(self, deps: AgentDeps) -> str:
        return texts.TELEGRAM_AGENT_PREFIX.format(name=deps.agent.name) if self.shared else ""

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
                    logger.warning("telegram %s: another poller holds this bot", self.label)
                else:
                    logger.warning("telegram %s: %s", self.label, exc)
            except Exception:
                logger.exception("telegram %s: update failed", self.label)
            await asyncio.sleep(RETRY_SECONDS)

    async def register_menu(self) -> None:
        """Publishes the slash-command menu once per process; retried with the poll loop."""
        if not self._menu_registered:
            await self._api.set_my_commands(list(MENU))
            self._menu_registered = True
            logger.info("telegram %s: command menu registered", self.label)

    async def poll_once(self) -> int:
        """Fetches pending updates and handles each; the offset moves before handling so a
        message that crashes the handler is not replayed forever."""
        updates = await self._api.get_updates(self._offset)
        for update in updates:
            self._offset = int(update["update_id"]) + 1
            write_offset(self._offset_path, self._offset)
            await self.handle(update)
        return len(updates)

    async def handle(self, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        text = message.get("text")
        if chat_id != self.chat_id or not text:
            logger.info("telegram %s: ignored update from chat %s", self.label, chat_id)
            return
        logger.info("telegram %s: message of %d chars", self.label, len(text))
        agent_id, text, addressed = await route_mention(self, text)
        if agent_id is None:
            return
        command = parse_command(text)
        if command is None:
            await self.chat(agent_id, text)
            return
        answer = await answer_command(self, agent_id, command, addressed)
        if bot_answers(self, command, addressed):
            await self.say(answer)
        else:
            await self._outbound[agent_id].send(answer)

    async def chat(self, agent_id: str, text: str) -> None:
        conv = self.conversation(agent_id)
        try:
            events = self.inbound.stream(conv.id, text, source=TELEGRAM)
        except InboundBusy:
            return await self.say(texts.TELEGRAM_BUSY)
        await self._outbound[agent_id].send(await self.answer(agent_id, events))

    async def answer(self, agent_id: str, events: AsyncIterator[Event]) -> str:
        """The turn as one message, read with "typing…" showing."""
        async with self._outbound[agent_id].typing():
            reply = await collect_reply(events, texts.TELEGRAM_APPROVAL_HOW)
        return reply.text

    async def say(self, text: str) -> None:
        """A message from the bot itself, not from an agent: no agent prefix."""
        await self._api.send_message(self.chat_id, text)

    def current_agent(self) -> str:
        return self.agent_id

    def remember_agent(self, agent_id: str) -> None:  # the agent an `@id` picked
        self.store.set_current_agent(self.channel_key, agent_id)

    def agents_text(self) -> str:
        return conversations.agents_text(self.agents, self.current_agent())

    def conversation(self, agent_id: str | None = None) -> Conversation:
        key, clock = self.channel_key, self._clock
        return self.inbound.conversation_for(agent_id or self.agent_id, key, clock, TITLE)

    def open_conversation(self, agent_id: str | None = None) -> Conversation:
        key, clock = self.channel_key, self._clock
        return self.inbound.open_conversation(agent_id or self.agent_id, key, clock, TITLE)

    async def deliver(self, conv_id: str) -> bool:
        """A conversation's last reply to the chat; False when the agent is not on this bot."""
        outbound = self._outbound.get(self.store.get(conv_id).agent_id)
        if outbound is None:
            logger.warning("telegram %s: conversation %s is another agent's", self.label, conv_id)
            return False
        return await outbound.deliver(conv_id)
