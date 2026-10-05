"""How a message from the chat becomes a turn. The turn runs in the background, so the poll
loop goes on reading the chat: a message sent while a turn runs waits in the conversation's
line, or steers the running turn when it is `/steer` or a kit command, and the chat hears so
at once. What waited gets a turn of its own when the conversation is free, answered by the
bot like any other (`run_delivered`, the drain's runner for Telegram).

While a turn runs or messages wait, the chat stays in that conversation, even past midnight
or after `/new`: a new conversation would start a second turn beside the first and recap
one that is still being written."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import TYPE_CHECKING

from my_agent_crew import texts
from my_agent_crew.agent.events import Event
from my_agent_crew.agent.turn_context import TELEGRAM
from my_agent_crew.agents.kit_commands import EmptySteer
from my_agent_crew.channels.telegram_answers import answer_text
from my_agent_crew.channels.telegram_canvas_notice import WrittenCanvases
from my_agent_crew.channels.telegram_polling import TelegramPolling
from my_agent_crew.inbound import Inbound, InboundBusy, TurnReply, collect_reply
from my_agent_crew.store.queue import QueueFull

if TYPE_CHECKING:
    from my_agent_crew.activity import ActivityHub
    from my_agent_crew.channels.telegram_outbound import TelegramOutbound
    from my_agent_crew.inbound_queue import QueueDrain
    from my_agent_crew.store import Conversation, Store

logger = logging.getLogger(__name__)


class TelegramChat(TelegramPolling):
    hub: ActivityHub
    inbound: Inbound
    store: Store
    channel_key: str
    say: Callable[[str], Awaitable[None]]
    outbound: Callable[..., TelegramOutbound]
    conversation: Callable[[], Conversation]
    _drain: QueueDrain | None = None

    def set_drain(self, drain: QueueDrain) -> None:
        """Set after construction, like `set_on_replaced`: the runtime builds the drain after
        the channel. While the bot polls, it answers what waited in its chat."""
        self._drain = drain

    def start(self) -> None:
        super().start()
        if self._drain is not None:
            self._drain.register(TELEGRAM, self.run_delivered)

    async def stop(self) -> None:
        if self._drain is not None:
            self._drain.unregister(TELEGRAM)  # first: no queued turn starts while it waits
        await super().stop()

    async def chat(self, text: str) -> None:
        conv = self.conversation()
        busy = self.hub.busy.busy(conv.id)
        question = self.store.approvals.pending_question(conv.id)
        # A slash command is a new instruction, never an answer. Someone who types `/brief`
        # while a question is open wants the brief, and storing "/brief" as the answer would
        # both lose the command and close the question with a word the agent cannot use.
        # Nor is a message the answer while the conversation is busy: the question is being
        # answered already, by an earlier message of the same poll.
        if question is not None and not busy and not text.startswith("/"):
            # The agent asked something and this is the reply. In a chat there is nowhere
            # else to put it: telling the person the conversation is busy when it is busy
            # waiting on them is the one answer that cannot be right.
            events = self.inbound.answer(conv.id, question.id, answer_text(text, question))
        else:
            try:
                events = self.inbound.stream(conv.id, text, source=TELEGRAM)
            except InboundBusy:
                return await self.say(texts.TELEGRAM_BUSY)
            except (EmptySteer, QueueFull) as exc:
                return await self.say(str(exc))
        if busy:  # it waits in line: say so at once, with no "typing…" for a turn not begun
            return await self.say((await collect_reply(events)).text)
        self.spawn(self.reply_to(events, conv.id))

    async def answer(self, events: AsyncIterator[Event]) -> TurnReply:
        """The turn as one message, read with "typing…" showing."""
        async with self.outbound().typing():
            return await collect_reply(events, texts.TELEGRAM_APPROVAL_HOW)

    async def reply_to(self, events: AsyncIterator[Event], conv_id: str) -> None:
        """A turn of the conversation `conv_id` in the background, its answer sent to the
        chat when it ends, then the list of the canvases it wrote. What breaks it is logged,
        and the chat hears of it by the error's kind only: the error's text may quote a
        request the chat has no business seeing. What it wrote before it broke is still
        listed, and what breaks the lines that close it is told the same way."""
        out, seen = self.outbound(), WrittenCanvases()
        unsaid = ""
        try:
            reply = await self.answer(seen.watch(events))
            if seen.tags and reply.text == texts.REPLY_EMPTY.format(steps=reply.steps):
                # It wrote canvases and said nothing: their list is its answer, and the
                # line calling the turn empty is kept for when none of them can be named.
                unsaid = reply.text
            else:
                await out.send(reply.text, conv_id)
        except Exception as exc:
            await self._turn_failed(exc)
        try:
            if not await out.send_written(seen.tags, conv_id) and unsaid:
                await out.send(unsaid, conv_id)
        except Exception as exc:
            await self._turn_failed(exc)

    async def _turn_failed(self, exc: Exception) -> None:
        """Logs what broke a turn and tells the chat its kind. A chat that cannot be told
        either is left with the log."""
        logger.error("telegram %s: a turn failed", self.agent_id, exc_info=exc)
        with suppress(Exception):
            await self.say(texts.TELEGRAM_TURN_FAILED.format(error=type(exc).__name__))

    async def run_delivered(self, conv_id: str, source: str) -> None:
        """The drain's runner: what waited is written into the conversation already, and
        its turn runs in the background like any other. Returning at once keeps the
        drain's claim on the conversation until the run takes it over."""
        self.spawn(self.reply_to(self.inbound.stream_delivered(conv_id, source), conv_id))

    def in_flight(self) -> Conversation | None:
        """The chat's latest conversation while a turn runs in it or messages wait in its
        line, where the chat stays until both are done."""
        conv = self.store.latest_for_channel(self.agent_id, self.channel_key)
        if conv is not None and (self.hub.busy.busy(conv.id) or self.store.queue.count(conv.id)):
            return conv
        return None
