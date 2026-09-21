"""What a Telegram chat maps to in the store: the channel key `telegram:<chat_id>` the
per-day conversations of every agent on the bot are filed under (opened by `Inbound`),
and, when several agents share a bot, the "current" agent (the one last picked with
`@id`, remembered per channel)."""

from __future__ import annotations

from collections.abc import Mapping

from my_agent_crew import texts
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.store import Store


def channel_key(chat_id: int) -> str:
    return f"telegram:{chat_id}"


def current_agent(store: Store, agents: Mapping[str, AgentDeps], chat_id: int) -> str:
    """The agent a message without a mention goes to: the one last picked with `@id`,
    the first configured one before any pick (or when the picked one left the bot)."""
    first = next(iter(agents))
    if len(agents) == 1:
        return first
    picked = store.channels.current_agent(channel_key(chat_id))
    return picked if picked in agents else first


def agents_text(agents: Mapping[str, AgentDeps], current: str) -> str:
    lines = [
        texts.TELEGRAM_AGENT_LINE.format(
            mark=texts.TELEGRAM_AGENT_CURRENT
            if agent_id == current
            else texts.TELEGRAM_AGENT_OTHER,
            agent_id=agent_id,
            name=deps.agent.name,
        )
        for agent_id, deps in agents.items()
    ]
    return texts.TELEGRAM_AGENTS.format(agents="\n".join(lines))
