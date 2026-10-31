"""The decisions a Telegram chat may take: what its own conversations wait on, and what the
conversations they delegated to wait on.

A delegated child (the master handing a task to another agent) pauses in a conversation of
its own while the chat's turn waits on it, so the chat could neither see nor settle the
child's request: the web's approvals page was the only way. Now the chat hears of it the
moment it is made (`watch_children`), with the buttons that settle it, and `/approve`,
`/deny` and a typed answer reach it too.

A decision on the chat's own conversation resumes a turn whose answer the chat is owed, so
it is read like a message's (`reply_to`). A child's resumed turn answers its parent's tool
call instead: it is read to its end in silence, and the parent's turn, still running under
the chat's message, says what came of it."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import fields
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts
from my_agent_crew.agent.events import ApprovalRequiredEvent, Event, kind_of
from my_agent_crew.channels.telegram_api import TelegramError
from my_agent_crew.channels.telegram_buttons import buttons_for, call_line
from my_agent_crew.store.models import QUESTION, Approval, Conversation
from my_agent_crew.turn_reply import question_notice

if TYPE_CHECKING:
    from my_agent_crew.channels.telegram_channel import TelegramChannel

logger = logging.getLogger(__name__)
# A watcher cut off for falling behind watches again after this.
REWATCH_SECONDS = 1.0
_EVENT_FIELDS = {f.name for f in fields(ApprovalRequiredEvent)}
APPROVAL_REQUIRED = kind_of(ApprovalRequiredEvent("", "", "", {}))


def in_chat(channel: TelegramChannel, conv: Conversation) -> bool:
    """Whether the chat may decide for this conversation: one of its own, or one delegated
    from one of its own, however deep."""
    if not conv.root_id:
        return conv.channel == channel.channel_key and not conv.parent_call_id
    try:
        return channel.store.get(conv.root_id).channel == channel.channel_key
    except KeyError:
        return False


def open_question(
    channel: TelegramChannel, conv: Conversation
) -> tuple[Conversation, Approval] | None:
    """The question the chat's next message answers: the conversation's own, else one a
    child of it asks while the conversation waits on that child. One being answered already
    (its conversation busy) is no one's to answer again."""
    busy = channel.hub.busy.busy
    question = channel.store.approvals.pending_question(conv.id)
    if question is not None:
        return None if busy(conv.id) else (conv, question)
    for waiting in channel.store.awaiting_for_channel(channel.agent_id, channel.channel_key):
        if waiting.root_id != conv.id or busy(waiting.id):
            continue
        question = channel.store.approvals.pending_question(waiting.id)
        if question is not None:
            return waiting, question
    return None


def resume(channel: TelegramChannel, conv: Conversation, events: AsyncIterator[Event]) -> None:
    """Reads the rest of a turn a decision resumed, in the background: the chat's own with
    its answer sent to the chat, a child's in silence."""
    if conv.root_id:
        channel.spawn(_read_through(events))
    else:
        channel.spawn(channel.reply_to(events, conv.id))


async def _read_through(events: AsyncIterator[Event]) -> None:
    async for _ in events:
        pass


def request_text(event: ApprovalRequiredEvent) -> str:
    """A request as the chat reads it: a question as itself, a tool call with what it runs."""
    if event.kind == QUESTION:
        return question_notice(event)
    reason = f" ({event.reason})" if event.reason else ""
    how = texts.TELEGRAM_APPROVAL_HOW
    asked = texts.REPLY_APPROVAL.format(name=event.name, reason=reason, how=how)
    return f"{asked}\n\n{call_line(event)}"


def child_request(
    channel: TelegramChannel, payload: dict[str, Any]
) -> tuple[Conversation, ApprovalRequiredEvent] | None:
    """The request an activity payload announces, when a child of the chat's conversations
    made it. The chat's own conversation says its requests in its reply, so those are not
    told twice."""
    event = payload.get("event") or {}
    if payload.get("type") != "event" or event.get("type") != APPROVAL_REQUIRED:
        return None
    try:
        conv = channel.store.get(str(payload.get("conversation_id") or ""))
    except KeyError:
        return None
    if not conv.root_id or not in_chat(channel, conv):
        return None
    return conv, ApprovalRequiredEvent(**{k: v for k, v in event.items() if k in _EVENT_FIELDS})


async def tell_request(
    channel: TelegramChannel, conv: Conversation, event: ApprovalRequiredEvent
) -> None:
    """The request said in the chat under the asking agent's name, with its buttons. One the
    chat cannot be told of is logged: the web's approvals page still has it."""
    text, buttons = request_text(event), buttons_for(event)
    try:
        if conv.agent_id in channel.agents:
            await channel.outbound(conv.agent_id).ask(text, buttons)
        else:
            await channel.api.send_message(channel.chat_id, text, buttons)
    except TelegramError as exc:
        logger.warning("telegram %s: a delegated request was not told: %s", channel.agent_id, exc)


async def watch_children(channel: TelegramChannel) -> None:
    """Runs while the channel does: every request a child of the chat's conversations makes
    is told to the chat as it is made."""
    while True:
        async for payload in channel.hub.subscribe():
            found = child_request(channel, payload)
            if found is not None:
                channel.spawn(tell_request(channel, *found))
        await asyncio.sleep(REWATCH_SECONDS)
