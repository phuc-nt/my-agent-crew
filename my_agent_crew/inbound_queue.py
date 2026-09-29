"""What becomes of a message that finds its conversation busy.

`enqueue` stores it and answers with its place in line. `QueueDrain` hands the waiting
messages over once the conversation stops being busy: they become one user message, written
in the same commit that empties the line, and a turn answers them. A Telegram chat hears the
answer from its bot, which registers a runner for that; any other conversation's turn is read
through here, and its answer lands in the conversation for the web to show.

`Busy` wakes the drain when a turn ends or an unread claim lapses. From the check that
nothing holds the conversation to the claim the drain then makes is one synchronous step,
so two drains of one conversation cannot both hand its messages over."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import TYPE_CHECKING

from my_agent_crew.agent.events import Event, QueuedEvent
from my_agent_crew.agent.tool_calls import close_interrupted
from my_agent_crew.agent.turn_context import TELEGRAM
from my_agent_crew.inbound_conversations import channel_label
from my_agent_crew.store.models import AWAITING_APPROVAL
from my_agent_crew.store.queue import FOLLOW_UP, STEER, QueuedItem

if TYPE_CHECKING:
    from my_agent_crew.activity import ActivityHub
    from my_agent_crew.agent.loop import AgentDeps
    from my_agent_crew.inbound import Inbound
    from my_agent_crew.store import Conversation, Store

logger = logging.getLogger(__name__)
# Answers a conversation whose waiting messages were just written into it: (conv_id, source).
Runner = Callable[[str, str], Awaitable[None]]


def enqueue(
    deps: AgentDeps, conv_id: str, text: str, steer: str | None, source: str
) -> AsyncIterator[Event]:
    """Queues a message that found its conversation busy — for the running turn itself when
    `steer` holds what it asks — and returns its place in line as the only event. Raises
    `QueueFull` before anything is stored."""
    kind = FOLLOW_UP if steer is None else STEER
    item, position = deps.store.queue.add(conv_id, kind, text if steer is None else steer, source)
    return _one(QueuedEvent(item_id=item.id, kind=kind, position=position))


async def _one(event: Event) -> AsyncIterator[Event]:
    yield event


class QueueDrain:
    def __init__(self, store: Store, hub: ActivityHub, inbound: Inbound):
        self._store = store
        self._hub = hub
        self._inbound = inbound
        self._runners: dict[str, Runner] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        # The turn each drain is running, by conversation, for `cancel` to reach.
        self._turns: dict[str, asyncio.Task[None]] = {}
        self._stopped = False
        hub.busy.on_idle = self.schedule

    def register(self, channel: str, runner: Runner) -> None:
        """Answers the channel's conversations with `runner` from now on; the ones that
        waited for it drain now."""
        self._runners[channel] = runner
        self._schedule_all()

    def unregister(self, channel: str) -> None:
        self._runners.pop(channel, None)

    def start(self) -> None:
        """Drains what was still waiting when the server last stopped."""
        self._stopped = False
        self._schedule_all()

    async def stop(self) -> None:
        """Ends the drains in flight; what still waits stays queued for the next start."""
        self._stopped = True
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._turns.clear()

    def schedule(self, conv_id: str) -> None:
        """Drains the conversation in the background, if anything waits for it."""
        if self._stopped or self._store.queue.count(conv_id) == 0:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(self._drain(conv_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def cancel(self, conv_id: str) -> bool:
        """Stops the turn the drain runs for the conversation. False when there is none: a
        turn someone else reads — a web stream, a bot — is theirs to end."""
        task = self._turns.pop(conv_id, None)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def _schedule_all(self) -> None:
        for conv_id in self._store.queue.conversations_with_items():
            self.schedule(conv_id)

    async def _drain(self, conv_id: str) -> None:
        try:
            taken = self._take(conv_id)
        except Exception:
            logger.exception("queue of %s: handing the messages over failed", conv_id)
            return
        if taken is None:
            return
        runner, source, token = taken
        task = asyncio.current_task()
        if task is not None:
            self._turns[conv_id] = task
        try:
            await runner(conv_id, source)
        except Exception:
            logger.exception("queue of %s: the turn answering it failed", conv_id)
        finally:
            if task is not None and self._turns.get(conv_id) is task:
                del self._turns[conv_id]
            # A runner that failed before its run started would otherwise hold the
            # conversation until the claim lapsed; a later claim is not this one to drop.
            self._hub.busy.release(conv_id, token)
            self._hub.busy.settle(conv_id)

    def _take(self, conv_id: str) -> tuple[Runner, str, object] | None:
        """Writes the waiting messages into the conversation when nothing holds it, and says
        who answers them: the runner, the source its turn runs as, and the claim's token."""
        busy = self._hub.busy
        if busy.busy(conv_id):
            return None
        try:
            conv = self._store.get(conv_id)
        except KeyError:
            self._store.queue.take_all(conv_id)  # the conversation is gone, so is its line
            return None
        if conv.status == AWAITING_APPROVAL or self._store.approvals.pending(conv_id) is not None:
            return None  # the decision's turn drains the line when it ends
        items = self._store.queue.peek_all(conv_id)
        chosen = self._runner_for(conv, items) if items else None
        if chosen is None:
            return None
        token = busy.claim(conv_id)
        try:
            close_interrupted(self._store, conv_id)
            delivered = self._store.queue.deliver(conv_id, [item.id for item in items])
        except BaseException:
            busy.release(conv_id, token)
            raise
        if not delivered:
            busy.release(conv_id, token)
            return None
        return (*chosen, token)

    def _runner_for(
        self, conv: Conversation, items: Sequence[QueuedItem]
    ) -> tuple[Runner, str] | None:
        """A Telegram chat hears its answer from its bot, so with no bot registered its
        messages keep waiting; every other conversation is answered here."""
        if channel_label(conv.channel) == TELEGRAM and any(i.source == TELEGRAM for i in items):
            runner = self._runners.get(TELEGRAM)
            return None if runner is None else (runner, TELEGRAM)
        return self._read_through, items[0].source

    async def _read_through(self, conv_id: str, source: str) -> None:
        async for _ in self._inbound.stream_delivered(conv_id, source):
            pass
