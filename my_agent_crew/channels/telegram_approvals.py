"""The decisions a Telegram chat may take: what its own conversations wait on, what the
conversations they delegated to wait on, and what nobody else is watching for.

The chat is the crew's default place to decide. Besides its own requests it hears of every
request a delegated child makes, wherever its chain began (a child pauses in a conversation
of its own, out of sight of the page or the chat that started it), and of every request a
scheduled job makes, since nobody reads a job's conversation as it runs. A child's is told
the moment it is made (`watch_children`), a job's when the job is delivered while it waits
(`telegram_pending`), each with the buttons that settle it. `/approve`, `/deny` and a typed
answer still reach only the chat's own and their children.

A decision on the chat's own conversation resumes a turn whose answer the chat is owed, so
it is read like a message's (`reply_to`). A job's resumed turn is read to its end and its
answer delivered, as the job's would have been. A child's answers its parent's tool call
instead: it is read in silence, and the parent's turn says what came of it."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import fields
from datetime import tzinfo
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts
from my_agent_crew.agent.events import ApprovalRequiredEvent, Event, kind_of
from my_agent_crew.agent.turn_context import JOB, conversation_source
from my_agent_crew.channels.telegram_api import TelegramError
from my_agent_crew.channels.telegram_buttons import buttons_for, call_line, deadline_line
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


def told_of(channel: TelegramChannel, conv: Conversation) -> bool:
    """Whether the chat hears of this conversation's requests and may settle them by a press:
    its own, any delegated child's, and a job's."""
    if conv.root_id or in_chat(channel, conv):
        return True
    return conversation_source(channel.store, conv.id) == JOB


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
    its answer sent to the chat, a job's with its answer delivered at the end, a child's
    and one of the web's in silence."""
    if not conv.root_id and in_chat(channel, conv):
        channel.spawn(channel.reply_to(events, conv.id))
    elif not conv.root_id and conversation_source(channel.store, conv.id) == JOB:
        channel.spawn(_read_through(events, channel, conv.id))
    else:
        channel.spawn(_read_through(events))


async def _read_through(
    events: AsyncIterator[Event], channel: TelegramChannel | None = None, conv_id: str = ""
) -> None:
    async for _ in events:
        pass
    if channel is not None:
        await channel.deliver(conv_id)


def request_text(event: ApprovalRequiredEvent, zone: tzinfo | None = None) -> str:
    """A request as the chat reads it: a question as itself, a tool call with what it runs,
    and either with the time it runs out."""
    deadline = deadline_line(event.expires_at, zone)
    if event.kind == QUESTION:
        return "\n\n".join(part for part in (question_notice(event), deadline) if part)
    reason = f" ({event.reason})" if event.reason else ""
    how = texts.TELEGRAM_APPROVAL_HOW
    asked = texts.REPLY_APPROVAL.format(name=event.name, reason=reason, how=how)
    return "\n\n".join(part for part in (asked, call_line(event), deadline) if part)


def told_request(
    channel: TelegramChannel, payload: dict[str, Any]
) -> tuple[Conversation, ApprovalRequiredEvent] | None:
    """The request an activity payload announces, when a delegated child made it. The chat's
    own conversation says its requests in its reply, and a job's says them when it is
    delivered, so those are not told twice."""
    event = payload.get("event") or {}
    if payload.get("type") != "event" or event.get("type") != APPROVAL_REQUIRED:
        return None
    try:
        conv = channel.store.get(str(payload.get("conversation_id") or ""))
    except KeyError:
        return None
    if not conv.root_id:
        return None
    return conv, ApprovalRequiredEvent(**{k: v for k, v in event.items() if k in _EVENT_FIELDS})


async def tell_request(
    channel: TelegramChannel, conv: Conversation, event: ApprovalRequiredEvent
) -> None:
    """The request said in the chat under the asking agent's name, with its buttons, and
    followed until it is settled (`telegram_told`). One the chat cannot be told of is
    logged: the web's approvals page still has it."""
    text, buttons = request_text(event, channel.deps.settings.zone), buttons_for(event)
    try:
        if conv.agent_id in channel.agents:
            await channel.outbound(conv.agent_id).ask(text, buttons)
        else:
            sent = await channel.api.send_message(channel.chat_id, text, buttons)
            channel.told.record(buttons, sent, text)
    except TelegramError as exc:
        logger.warning("telegram %s: a request was not told: %s", channel.agent_id, exc)


async def watch_children(channel: TelegramChannel) -> None:
    """Runs while the channel does: every request the chat is told of is told as it is
    made."""
    while True:
        async for payload in channel.hub.subscribe():
            found = told_request(channel, payload)
            if found is not None:
                channel.spawn(tell_request(channel, *found))
        await asyncio.sleep(REWATCH_SECONDS)
