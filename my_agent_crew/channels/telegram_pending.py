"""Requests said again with their buttons: what a job delivered while it waits stopped on,
and `/pending`, every request the chat may settle.

A request told an hour ago sits far up the chat, under whatever came since, and one told
before a restart lost its message to a new process. The command lists what still waits,
oldest first, each as the request it is, so a press settles it from here."""

from __future__ import annotations

from typing import TYPE_CHECKING

from my_agent_crew import texts
from my_agent_crew.agent.events import ApprovalRequiredEvent
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.channels.telegram_approvals import request_text, tell_request, told_of
from my_agent_crew.channels.telegram_buttons import buttons_for
from my_agent_crew.store.models import Approval

if TYPE_CHECKING:
    from my_agent_crew.channels.telegram_channel import TelegramChannel
    from my_agent_crew.channels.telegram_outbound import TelegramOutbound

MAX_LISTED = 10


def as_event(approval: Approval) -> ApprovalRequiredEvent:
    """A stored request as the event that announced it; the reason it asked is not kept."""
    return ApprovalRequiredEvent(
        approval.id,
        approval.tool_call_id,
        approval.tool_name,
        approval.arguments,
        expires_at=approval.expires_at or "",
        kind=approval.kind,
        options=list(approval.options),
    )


async def list_pending(channel: TelegramChannel) -> str:
    """Says how many wait, then each one; nothing is left to say after them."""
    found = []
    for approval in channel.store.approvals.waiting(limit=MAX_LISTED * 5):
        try:
            conv = channel.store.get(approval.conversation_id)
        except KeyError:
            continue
        if told_of(channel, conv):
            found.append((conv, approval))
    if not found:
        return texts.TELEGRAM_PENDING_NONE
    await channel.say(texts.TELEGRAM_PENDING.format(count=len(found)))
    for conv, approval in found[:MAX_LISTED]:
        await tell_request(channel, conv, as_event(approval))
    return ""


async def ask_waiting(out: TelegramOutbound, deps: AgentDeps, conv_id: str) -> bool:
    """A job delivered while it waits: the request it waits on, with its buttons. False when
    nothing waits, and the run is said to have stopped instead."""
    approval = deps.store.approvals.pending(conv_id)
    if approval is None:
        return False
    event = as_event(approval)
    await out.ask(request_text(event, deps.settings.zone), buttons_for(event))
    return True
