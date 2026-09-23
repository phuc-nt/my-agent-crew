"""One Telegram bot's channel: messages from the configured chat become turns of the
master's per-day conversation, run through the same `Inbound` gate as the web UI, so the
chat and the web are the same mechanism — talk to the master, which delegates. Every agent
is known to the channel so `deliver` can push a crew member's scheduled brief to the chat
under that member's name. `telegram_inbound` reads each update (slash commands,
attachments). Only one process may poll a bot: a 409 means another is."""

from __future__ import annotations

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
from my_agent_crew.channels.telegram_answers import answer_text
from my_agent_crew.channels.telegram_api import TelegramApi
from my_agent_crew.channels.telegram_offset import read_offset
from my_agent_crew.channels.telegram_outbound import TelegramOutbound
from my_agent_crew.channels.telegram_polling import TelegramPolling
from my_agent_crew.inbound import Inbound, InboundBusy, collect_reply
from my_agent_crew.store import Conversation, Store

logger = logging.getLogger(__name__)
TITLE = texts.TELEGRAM_CONVERSATION_TITLE


def channel_key(chat_id: int) -> str:
    """The `conversations.channel` value of the chat, shared by every conversation it opens."""
    return f"telegram:{chat_id}"


class TelegramChannel(TelegramPolling):
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

    def use_agents(self, agents: Mapping[str, AgentDeps]) -> None:
        """Take the crew as it is after agents were rebuilt, keeping the bot as it is: a
        new key reaches the chat without the poll being interrupted. Senders are made
        again on next use, since each holds the deps it was made for."""
        self.agents.clear()
        self.agents.update(agents)
        self._outbound.clear()

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

    async def chat(self, text: str) -> None:
        conv = self.conversation()
        question = self.store.approvals.pending_question(conv.id)
        # A slash command is a new instruction, never an answer. Someone who types `/brief`
        # while a question is open wants the brief, and storing "/brief" as the answer would
        # both lose the command and close the question with a word the agent cannot use.
        if question is not None and not text.startswith("/"):
            # The agent asked something and this is the reply. In a chat there is nowhere
            # else to put it: telling the person the conversation is busy when it is busy
            # waiting on them is the one answer that cannot be right.
            events = self.inbound.answer(conv.id, question.id, answer_text(text, question))
            return await self.outbound().send(await self.answer(events))
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
