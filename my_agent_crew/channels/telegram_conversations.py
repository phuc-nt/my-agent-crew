"""What a Telegram chat maps to in the store: one conversation per agent per day on the
channel `telegram:<chat_id>`, and, when several agents share a bot, the "current" agent
(the one last picked with `@id`, remembered per channel). Also turns an agent turn's
event stream into the text the chat should read."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from datetime import datetime
from typing import Any

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    AssistantMessageEvent,
    ErrorEvent,
    Event,
    HaltedEvent,
)
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.channels.telegram_outbound import TelegramOutbound
from my_agent_crew.store import Conversation, Store

SOURCE = "telegram"


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


def today_conversation(
    deps: AgentDeps,
    chat_id: int,
    clock: Any,
    on_replaced: Callable[[AgentDeps, str], None] | None = None,
) -> Conversation:
    """Today's conversation of the agent on this chat, opened on first use each day."""
    latest = deps.store.latest_for_channel(deps.agent.id, channel_key(chat_id))
    today = clock().date()
    if latest is None or datetime.fromisoformat(latest.created_at).astimezone().date() != today:
        return open_conversation(deps, chat_id, clock, on_replaced)
    return latest


def open_conversation(
    deps: AgentDeps,
    chat_id: int,
    clock: Any,
    on_replaced: Callable[[AgentDeps, str], None] | None = None,
) -> Conversation:
    """Opens a new conversation; the one it replaces is handed to `on_replaced` so the
    caller can summarise it without this module importing the memory package."""
    previous = deps.store.latest_for_channel(deps.agent.id, channel_key(chat_id))
    conv = deps.store.create(
        title=texts.TELEGRAM_CONVERSATION_TITLE.format(date=clock().date().isoformat()),
        autonomous=deps.settings.autonomous_default,
        cost_cap_usd=deps.settings.cost_cap_usd,
        agent_id=deps.agent.id,
        channel=channel_key(chat_id),
    )
    if previous is not None and on_replaced is not None:
        on_replaced(deps, previous.id)
    return conv


async def collect_turn(
    hub: ActivityHub,
    outbound: TelegramOutbound,
    agent_id: str,
    conv: Conversation,
    events: AsyncIterator[Event],
) -> str:
    """Runs a turn's events with "typing…" showing and returns what the user should read:
    every piece of assistant text, including text written next to a tool call (models
    often put the answer there and finish with a bare `MEDIA:` line), plus the
    halt/error/approval notices."""
    parts: list[str] = []
    async with outbound.typing():
        async for event in tracked(hub, events, agent_id, SOURCE, conv.title, conv.id):
            if isinstance(event, AssistantMessageEvent):
                parts.append(event.content.strip())
            elif isinstance(event, HaltedEvent):
                parts.append(
                    texts.TELEGRAM_HALTED.format(reason=event.reason, spent=event.spent_usd)
                )
            elif isinstance(event, ErrorEvent):
                parts.append(texts.TELEGRAM_ERROR.format(message=event.message))
            elif isinstance(event, ApprovalRequiredEvent):
                parts.append(texts.TELEGRAM_APPROVAL.format(name=event.name))
    return "\n\n".join(part for part in parts if part)
