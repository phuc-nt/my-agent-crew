"""A whole turn collapsed into the one message a chat platform can show.

The web reads a turn as it happens, event by event. Telegram and the relay behind
`POST /api/inbound` cannot: they send a message and show a reply. This is the translation
between the two — everything the agent said during the turn, plus the reason it stopped
if it stopped for a reason a person needs to act on."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from my_agent_crew import texts
from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    HaltedEvent,
    kind_of,
)


@dataclass(frozen=True)
class TurnReply:
    """A whole turn as one message: the assistant's text with the halt, error or
    approval notice appended, how many model steps it took, and how it ended."""

    text: str
    steps: int
    status: str  # done | halted | error | approval_required

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "steps": self.steps, "status": self.status}


async def collect_reply(
    events: AsyncIterator[Event], approval_how: str = texts.REPLY_APPROVAL_HOW
) -> TurnReply:
    """Reads a turn to the end and returns what the person should see: every piece of
    assistant text, including text written next to a tool call (models often put the
    answer there and finish with a bare `MEDIA:` line), then the halt, error or approval
    notice. A turn that ends without a word still gets a line: silence reads like a dead
    bot."""
    parts: list[str] = []
    steps = 0
    status = kind_of(DoneEvent(0.0, 0))
    async for event in events:
        if isinstance(event, AssistantMessageEvent):
            steps += 1
            parts.append(event.content.strip())
        elif isinstance(event, HaltedEvent):
            parts.append(texts.REPLY_HALTED.format(reason=event.reason, spent=event.spent_usd))
            status = kind_of(event)
        elif isinstance(event, ErrorEvent):
            parts.append(texts.REPLY_ERROR.format(message=event.message))
            status = kind_of(event)
        elif isinstance(event, ApprovalRequiredEvent):
            reason = f" ({event.reason})" if event.reason else ""
            notice = texts.REPLY_APPROVAL.format(name=event.name, reason=reason, how=approval_how)
            parts.append(notice)
            status = kind_of(event)
    answer = "\n\n".join(part for part in parts if part)
    return TurnReply(answer or texts.REPLY_EMPTY.format(steps=steps), steps, status)
