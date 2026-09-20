"""One Telegram bot's channel: messages from the configured chat become turns of a
per-day conversation of one agent (`telegram_conversations`). A bot may serve several
agents: `@<agent id>` picks the agent for that message and the ones after it; a bare
`@id` only switches. Slash commands are answered by `telegram_commands` without a model
call. `deliver` pushes a conversation's last reply (a scheduled brief) to the chat. Only
one process may poll a bot: a 409 means another poller is alive."""

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
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.channels import telegram_conversations as conversations
from my_agent_crew.channels.telegram_api import CONFLICT_STATUS, TelegramApi, TelegramError
from my_agent_crew.channels.telegram_commands import (
    CHANNEL_COMMANDS,
    MENU,
    answer_command,
    parse_command,
    route_mention,
)
from my_agent_crew.channels.telegram_offset import read_offset, write_offset
from my_agent_crew.channels.telegram_outbound import TelegramOutbound
from my_agent_crew.store import Conversation, Store
from my_agent_crew.store.models import AWAITING_APPROVAL

logger = logging.getLogger(__name__)
RETRY_SECONDS = 5


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
        self.hub = hub
        self._api = api
        self.chat_id = chat_id
        self._offset_path = offset_path
        self._clock = clock
        self._on_replaced: Callable[[AgentDeps, str], None] | None = None
        self._outbound = {
            agent_id: TelegramOutbound(deps, api, chat_id, prefix=self._prefix(deps))
            for agent_id, deps in self.agents.items()
        }
        self._offset = read_offset(offset_path)
        self._menu_registered = False
        self._task: asyncio.Task[None] | None = None

    def set_on_replaced(self, callback: Callable[[AgentDeps, str], None]) -> None:
        """Hands a replaced conversation to the runtime to summarise. Set after
        construction: the scheduler holding that task is built after the channels."""
        self._on_replaced = callback

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
    def agent_id(self) -> str:  # the agent a message without a mention goes to
        return self.current_agent()

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
        agent_id, text = await route_mention(self, text)
        if agent_id is None:
            return
        command = parse_command(text)
        if command in CHANNEL_COMMANDS:
            await self.say(await answer_command(self, agent_id, command))
        elif command is not None:
            await self._outbound[agent_id].send(await answer_command(self, agent_id, command))
        else:
            await self.chat(agent_id, text)

    async def chat(self, agent_id: str, text: str) -> None:
        conv = self.conversation(agent_id)
        if conv.status == AWAITING_APPROVAL:
            await self.say(texts.TELEGRAM_BUSY)
            return
        events = run_turn(self.agents[agent_id], conv.id, text)
        await self._outbound[agent_id].send(await self.turn(agent_id, conv, events))

    async def say(self, text: str) -> None:
        """A message from the bot itself, not from an agent: no agent prefix."""
        await self._api.send_message(self.chat_id, text)

    def current_agent(self) -> str:
        return conversations.current_agent(self.store, self.agents, self.chat_id)

    def remember_agent(self, agent_id: str) -> None:
        """The agent an `@id` picked, for the messages that follow it."""
        self.store.set_current_agent(conversations.channel_key(self.chat_id), agent_id)

    def agents_text(self) -> str:
        return conversations.agents_text(self.agents, self.current_agent())

    def conversation(self, agent_id: str | None = None) -> Conversation:
        deps = self.agents[agent_id or self.current_agent()]
        return conversations.today_conversation(deps, self.chat_id, self._clock, self._on_replaced)

    def open_conversation(self, agent_id: str | None = None) -> Conversation:
        deps = self.agents[agent_id or self.current_agent()]
        return conversations.open_conversation(deps, self.chat_id, self._clock, self._on_replaced)

    async def turn(self, agent_id: str, conv: Conversation, events: AsyncIterator[Event]) -> str:
        outbound = self._outbound[agent_id]
        return await conversations.collect_turn(self.hub, outbound, agent_id, conv, events)

    async def deliver(self, conv_id: str) -> bool:
        """Sends a conversation's last reply through its agent's outbound; False when
        there is none or the agent is not on this bot."""
        outbound = self._outbound.get(self.store.get(conv_id).agent_id)
        if outbound is None:
            logger.warning("telegram %s: conversation %s is another agent's", self.label, conv_id)
            return False
        return await outbound.deliver(conv_id)
