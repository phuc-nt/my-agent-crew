"""The one door every platform knocks on. The web UI, the Telegram bots and the plain
`POST /api/inbound` all hand a person's message to `Inbound`, which finds the agent,
guards the conversation, runs the turn and records it on the activity hub. A platform
that streams (the web) reads the events; one that shows a message per turn (Telegram, a
relay behind the API) takes the collected `TurnReply`. Nothing here knows which platform
called, so a new one needs an adapter and no change to the agents."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from datetime import datetime
from typing import Any

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.agent.events import Event
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.agent.resume import answer_question, resolve_approval
from my_agent_crew.agent.turn_context import CHAT
from my_agent_crew.agents import DEFAULT_AGENT_ID
from my_agent_crew.agents.kit_commands import expand
from my_agent_crew.memory.conversation_title import title_on_first_message
from my_agent_crew.store import Conversation
from my_agent_crew.store.models import AWAITING_APPROVAL

# Re-exported: a turn collapsed to one message lives in its own module now, but every
# platform adapter reaches for it through this door.
from my_agent_crew.turn_reply import TurnReply, collect_reply

__all__ = ["Inbound", "InboundBusy", "TurnReply", "channel_label", "collect_reply"]

OnReplaced = Callable[[AgentDeps, str], None]
# How long naming waits for the turn it queued behind before giving up on a better title.
TITLE_AFTER_TURN_TIMEOUT_S = 300.0


class InboundBusy(Exception):
    """The conversation waits for a decision on a tool call; a new message must wait too."""


def channel_label(channel: str) -> str:
    """`telegram:42` → `telegram`; a bare channel name is its own label."""
    return channel.split(":", 1)[0] or CHAT


class Inbound:
    def __init__(
        self,
        agents: Mapping[str, AgentDeps],
        hub: ActivityHub,
        on_replaced: OnReplaced | None = None,
        keep: Callable[[Any], None] | None = None,
    ):
        """`agents` is shared with the runtime, so an agent installed while running is
        reachable here at once. `on_replaced` receives a conversation a new day closed.
        `keep` holds background tasks — naming a conversation — so they are not collected
        mid-flight; without one, a turn still runs and simply goes unnamed."""
        self.agents = agents
        self.hub = hub
        self.on_replaced = on_replaced
        self.keep = keep

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
        # Before naming, which waits for this turn to end: the wait must not read the
        # signal the previous turn left raised.
        self.hub.turn_starting(conv_id)
        title = self._name_conversation(deps, conv_id, text)
        events = run_turn(deps, conv_id, text, source=source)
        return tracked(self.hub, events, deps.agent.id, source, title, conv.id)

    def _name_conversation(self, deps: AgentDeps, conv_id: str, text: str) -> str:
        """Names a still-unnamed conversation from what was just said, and returns the
        title the run should carry. The model's better name is written once this turn is
        over, so naming never delays or competes with the answer."""

        async def after_the_turn() -> None:
            if await self.hub.wait_finished(conv_id, TITLE_AFTER_TURN_TIMEOUT_S) is None:
                # Still running after the wait: the turn owns the chain, and a nicer name
                # is not worth competing for it. The first sentence stays.
                raise TimeoutError

        return title_on_first_message(
            self.keep,
            deps,
            conv_id,
            text,
            publish=self.hub.publish_conversation,
            after=after_the_turn,
        )

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

    def answer(
        self, conv_id: str, approval_id: str, answer: str, source: str = CHAT
    ) -> AsyncIterator[Event]:
        """Answers a waiting question and streams the rest of the turn. The sibling of
        `decide`: same pause, same resume, but the outcome is text rather than a yes."""
        deps = self.deps_for_conversation(conv_id)
        conv = deps.store.get(conv_id)
        events = answer_question(deps, conv_id, approval_id, answer)
        return tracked(self.hub, events, deps.agent.id, source, conv.title, conv.id)

    async def reply(
        self,
        conv_id: str,
        text: str,
        source: str = CHAT,
        approval_how: str = texts.REPLY_APPROVAL_HOW,
    ) -> TurnReply:
        return await collect_reply(self.stream(conv_id, text, source), approval_how)
