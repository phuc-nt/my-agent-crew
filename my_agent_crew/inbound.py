"""The one door every platform knocks on. The web UI, the Telegram bots and the plain
`POST /api/inbound` all hand a person's message to `Inbound`, which finds the agent,
guards the conversation, runs the turn and records it on the activity hub. A platform
that streams (the web) reads the events; one that shows a message per turn (Telegram, a
relay behind the API) takes the collected `TurnReply`. Nothing here knows which platform
called, so a new one needs an adapter and no change to the agents.

A message that finds its conversation busy does not start a second turn beside the first:
it waits in the conversation's queue and is answered once the turn is over, or, when it is
`/steer text` or a command from the agent's kit, is handed to the running turn at its next
step (`inbound_queue.py`)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.activity.turn_watch import Frame, Resync
from my_agent_crew.agent.events import Event
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.agent.resume import answer_question, resolve_approval
from my_agent_crew.agent.turn_context import CHAT
from my_agent_crew.agents.kit_commands import steer_text
from my_agent_crew.inbound_conversations import ConversationOpening, OnReplaced, channel_label
from my_agent_crew.inbound_queue import enqueue, in_line
from my_agent_crew.memory.conversation_title import title_on_first_message
from my_agent_crew.store.models import AWAITING_APPROVAL
from my_agent_crew.turn_host import TurnHost

# Re-exported: a turn collapsed to one message lives in its own module now, but every
# platform adapter reaches for it through this door.
from my_agent_crew.turn_reply import TurnReply, collect_reply

__all__ = ["Inbound", "InboundBusy", "TurnReply", "channel_label", "collect_reply"]

# How long naming waits for the turn it queued behind before giving up on a better title.
TITLE_AFTER_TURN_TIMEOUT_S = 300.0


class InboundBusy(Exception):
    """The conversation waits for a decision on a tool call, or a decision was already
    taken and its turn has not started yet; a new message or decision must wait too."""


async def _as_it_stands() -> AsyncIterator[Frame]:
    """A view with no turn to follow: the stored conversation, and nothing after it."""
    yield Resync(replay=(), under_way=False)


class Inbound(ConversationOpening):
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
        # Reads the web's turns to their end, so a closed tab only stops watching.
        self.host = TurnHost(hub.turns)

    def stream(
        self, conv_id: str, text: str, source: str = CHAT, request_id: str = ""
    ) -> AsyncIterator[Event]:
        """A person's message as a tracked turn or, while the conversation is busy, as its
        place in the queue: one `QueuedEvent`. Raises `InboundBusy` while a tool call of
        this conversation waits for a decision: the loop would refuse the message too, but
        only once the stream is read, which is too late for a status code. `request_id` is
        the name its sender gave the send, stored with the message (`repeated`)."""
        deps = self.deps_for_conversation(conv_id)
        conv = deps.store.get(conv_id)
        # `/steer text` and `/name args` from the agent's kit ask to jump the queue; idle,
        # they are simply the text the agent reads. A bare `/steer` is refused either way.
        steer = steer_text(text, deps.agent.commands)
        if self.hub.busy.busy(conv_id):
            return enqueue(deps, conv_id, text, steer, source, request_id)
        if conv.status == AWAITING_APPROVAL or deps.store.approvals.pending(conv_id) is not None:
            raise InboundBusy(conv_id)
        text = text if steer is None else steer
        # Before naming, which waits for this turn to end: the wait must not read the
        # signal the previous turn left raised.
        self.hub.turn_starting(conv_id)
        title = self._name_conversation(deps, conv_id, text)
        self.hub.busy.claim(conv_id)
        events = run_turn(deps, conv_id, text, source=source, request_id=request_id)
        return tracked(self.hub, events, deps.agent.id, source, title, conv.id)

    def stream_hosted(self, conv_id: str, text: str, request_id: str = "") -> AsyncIterator[Frame]:
        """`stream` for the web: the server reads the turn to its end and the sender gets
        its view of it. A message that joins the queue starts no turn, so its one event
        comes back as it is."""
        queued = self.hub.busy.busy(conv_id)  # what `stream` is about to find, in this step
        events = self.stream(conv_id, text, request_id=request_id)
        return events if queued else self.host.run(conv_id, events, request_id)

    def repeated(self, conv_id: str, request_id: str) -> AsyncIterator[Frame] | None:
        """What a send already taken is answered with when it is made again, so a sender
        that never heard the first answer cannot say the same thing twice: its place in
        line while it still waits there, otherwise the conversation as it stands and the
        turn under way. None for a send not taken before, a nameless one among them. A
        message withdrawn from the queue was not taken, and neither was one refused."""
        store = self.deps_for_conversation(conv_id).store
        if not request_id:
            return None
        waiting = store.queue.waiting(conv_id, request_id)
        if waiting is not None:
            return in_line(*waiting)
        if not (
            self.host.answering(conv_id, request_id) or store.messages.took(conv_id, request_id)
        ):
            return None
        return self.hub.turns.join(conv_id) or _as_it_stands()

    def stream_delivered(self, conv_id: str, source: str = CHAT) -> AsyncIterator[Event]:
        """The turn that answers what the queue already wrote into the conversation. The
        drain claimed the conversation before writing; this turn's run takes it over."""
        deps = self.deps_for_conversation(conv_id)
        conv = deps.store.get(conv_id)
        self.hub.turn_starting(conv_id)
        events = run_turn(deps, conv_id, None, source=source)
        return tracked(self.hub, events, deps.agent.id, source, conv.title, conv.id)

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

    def _claim(self, conv_id: str) -> None:
        """A decision holds the conversation from the moment it is taken, so a second one
        — a double click, the other channel — is turned away instead of racing the first
        to the same pending call, and a message sent meanwhile waits in the queue."""
        if self.hub.busy.busy(conv_id):
            raise InboundBusy(conv_id)
        self.hub.busy.claim(conv_id)

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
        self._claim(conv_id)
        events = resolve_approval(deps, conv_id, approval_id, approve, always=always)
        return tracked(self.hub, events, deps.agent.id, source, conv.title, conv.id)

    def answer(
        self, conv_id: str, approval_id: str, answer: str, source: str = CHAT
    ) -> AsyncIterator[Event]:
        """Answers a waiting question and streams the rest of the turn. The sibling of
        `decide`: same pause, same resume, but the outcome is text rather than a yes."""
        deps = self.deps_for_conversation(conv_id)
        conv = deps.store.get(conv_id)
        self._claim(conv_id)
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
