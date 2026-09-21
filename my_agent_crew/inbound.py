"""The one door every platform knocks on. The web UI, the Telegram bots and the plain
`POST /api/inbound` all hand a person's message to `Inbound`, which finds the agent,
guards the conversation, runs the turn and records it on the activity hub. A platform
that streams (the web) reads the events; one that shows a message per turn (Telegram, a
relay behind the API) takes the collected `TurnReply`. Nothing here knows which platform
called, so a new one needs an adapter and no change to the agents."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    HaltedEvent,
    kind_of,
)
from my_agent_crew.agent.loop import AgentDeps, resolve_approval, run_turn
from my_agent_crew.agent.turn_context import CHAT
from my_agent_crew.agents import DEFAULT_AGENT_ID
from my_agent_crew.agents.kit_commands import expand
from my_agent_crew.store import Conversation
from my_agent_crew.store.models import AWAITING_APPROVAL

OnReplaced = Callable[[AgentDeps, str], None]


class InboundBusy(Exception):
    """The conversation waits for a decision on a tool call; a new message must wait too."""


@dataclass(frozen=True)
class TurnReply:
    """A whole turn as one message: the assistant's text with the halt, error or
    approval notice appended, how many model steps it took, and how it ended."""

    text: str
    steps: int
    status: str  # done | halted | error | approval_required

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "steps": self.steps, "status": self.status}


def channel_label(channel: str) -> str:
    """`telegram:42` → `telegram`; a bare channel name is its own label."""
    return channel.split(":", 1)[0] or CHAT


class Inbound:
    def __init__(
        self,
        agents: Mapping[str, AgentDeps],
        hub: ActivityHub,
        on_replaced: OnReplaced | None = None,
    ):
        """`agents` is shared with the runtime, so an agent installed while running is
        reachable here at once. `on_replaced` receives a conversation a new day closed."""
        self.agents = agents
        self.hub = hub
        self.on_replaced = on_replaced

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
        conv = deps.store.create(
            title=title.format(channel=channel_label(channel), date=clock().date().isoformat()),
            autonomous=deps.settings.autonomous_default,
            cost_cap_usd=deps.settings.cost_cap_usd,
            agent_id=agent_id,
            channel=channel,
        )
        if previous is not None and self.on_replaced is not None:
            self.on_replaced(deps, previous.id)
        return conv

    def stream(self, conv_id: str, text: str, source: str = CHAT) -> AsyncIterator[Event]:
        """A person's message as a tracked turn. Raises `InboundBusy` while a tool call
        of this conversation waits for a decision: the loop would refuse the message too,
        but only once the stream is read, which is too late for a status code."""
        deps = self.deps_for_conversation(conv_id)
        conv = deps.store.get(conv_id)
        if conv.status == AWAITING_APPROVAL or deps.store.approvals.pending(conv_id) is not None:
            raise InboundBusy(conv_id)
        # `/name args` from the agent's kit becomes the command's prompt before the
        # agent reads it, on every platform alike.
        text = expand(text, deps.agent.commands)
        events = run_turn(deps, conv_id, text, source=source)
        return tracked(self.hub, events, deps.agent.id, source, conv.title, conv.id)

    def decide(
        self,
        conv_id: str,
        approval_id: str,
        approve: bool,
        always: bool = False,
        source: str = CHAT,
    ) -> AsyncIterator[Event]:
        """Resolves a pending tool call and streams the rest of the turn."""
        deps = self.deps_for_conversation(conv_id)
        conv = deps.store.get(conv_id)
        events = resolve_approval(deps, conv_id, approval_id, approve, always=always)
        return tracked(self.hub, events, deps.agent.id, source, conv.title, conv.id)

    async def reply(
        self,
        conv_id: str,
        text: str,
        source: str = CHAT,
        approval_how: str = texts.REPLY_APPROVAL_HOW,
    ) -> TurnReply:
        return await collect_reply(self.stream(conv_id, text, source), approval_how)


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
