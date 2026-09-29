"""The half of the inbound door that knows nothing about turns: which agent a message is
for and which conversation it lands in. `Inbound` inherits it."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime

from my_agent_crew import texts
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agent.turn_context import CHAT, TELEGRAM
from my_agent_crew.agents import DEFAULT_AGENT_ID
from my_agent_crew.store import Conversation

OnReplaced = Callable[[AgentDeps, str], None]


def channel_label(channel: str) -> str:
    """`telegram:42` → `telegram`; a bare channel name is its own label."""
    return channel.split(":", 1)[0] or CHAT


class ConversationOpening:
    agents: Mapping[str, AgentDeps]
    on_replaced: OnReplaced | None

    def deps_for(self, agent_id: str) -> AgentDeps:
        try:
            return self.agents[agent_id]
        except KeyError as exc:
            raise KeyError(texts.AGENT_UNKNOWN.format(agent_id=agent_id)) from exc

    def deps_for_conversation(self, conv_id: str) -> AgentDeps:
        """KeyError for an unknown conversation; one whose agent left the crew runs as
        the master rather than being lost."""
        conv = next(iter(self.agents.values())).store.get(conv_id)
        deps = self.agents.get(conv.agent_id) or self.agents.get(DEFAULT_AGENT_ID)
        if deps is None:
            raise KeyError(texts.AGENT_UNKNOWN.format(agent_id=conv.agent_id))
        return deps

    def conversation_for(
        self,
        agent_id: str,
        channel: str,
        clock: Callable[[], datetime] = datetime.now,
        title: str = texts.INBOUND_CONVERSATION_TITLE,
    ) -> Conversation:
        """Today's conversation of the agent on this channel, opened on first use each
        day. A chat window is one thread; a day is a natural place to cut it."""
        deps = self.deps_for(agent_id)
        latest = deps.store.latest_for_channel(agent_id, channel)
        now = clock()  # the stored stamp is UTC; the day is read in the clock's own zone
        if latest is None:
            return self.open_conversation(agent_id, channel, clock, title)
        opened = datetime.fromisoformat(latest.created_at).astimezone(now.tzinfo)
        if opened.date() != now.date():
            return self.open_conversation(agent_id, channel, clock, title)
        return latest

    def open_conversation(
        self,
        agent_id: str,
        channel: str,
        clock: Callable[[], datetime] = datetime.now,
        title: str = texts.INBOUND_CONVERSATION_TITLE,
    ) -> Conversation:
        """Opens a new conversation on the channel; the one it replaces is handed to
        `on_replaced` so the caller can recap it in the background."""
        deps = self.deps_for(agent_id)
        previous = deps.store.latest_for_channel(agent_id, channel)
        telegram = deps.agent.telegram if channel_label(channel) == TELEGRAM else None
        conv = deps.store.create(
            title=title.format(channel=channel_label(channel), date=clock().date().isoformat()),
            autonomous=deps.settings.autonomous_default,
            cost_cap_usd=deps.settings.cost_cap_usd,
            agent_id=agent_id,
            channel=channel,
            approval_ttl_seconds=telegram.approval_ttl_seconds if telegram else None,
        )
        if previous is not None and self.on_replaced is not None:
            self.on_replaced(deps, previous.id)
        return conv
