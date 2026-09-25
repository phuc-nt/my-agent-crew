"""The activity hub: every turn and job is a run with a step timeline. Runs are stored
as they progress and broadcast to whoever is watching `/api/activity/stream`, so the UI
can show all agents working at once, not only the conversation on screen."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Sequence
from typing import Any

from my_agent_crew.activity.steps import apply_event
from my_agent_crew.agent.events import Event, kind_of, to_dict
from my_agent_crew.store import Store
from my_agent_crew.store.db import new_id, now_iso
from my_agent_crew.store.runs import ACTIVE_STATUSES, AWAITING, RUNNING, RunRecord

RECENT_LIMIT = 100


class ActivityHub:
    def __init__(self, store: Store):
        self._store = store
        self._live: dict[str, RunRecord] = {}
        self._subscribers: set[asyncio.Queue[dict[str, Any] | None]] = set()
        # Set when a conversation's run reaches a terminal status, so a caller waiting on
        # a delegated turn wakes up instead of polling.
        self._finished: dict[str, asyncio.Event] = {}
        self._store.runs.mark_interrupted(now_iso())

    # --- runs ----------------------------------------------------------------------------

    def turn_starting(self, conversation_id: str) -> None:
        """Lowers the conversation's terminal signal before the turn produces anything.

        `tracked` is a generator, so `start` does not run until the caller reads the first
        event. A waiter created in between — naming, which must queue behind the answer —
        would otherwise read the *previous* turn's raised signal and run straight away,
        competing with the live turn for the same chain."""
        self._finished.setdefault(conversation_id, asyncio.Event()).clear()

    def start(
        self, agent_id: str, source: str, title: str, conversation_id: str | None
    ) -> RunRecord:
        """A turn that resumes after an approval continues the run that paused."""
        if conversation_id:
            self.turn_starting(conversation_id)
        for live in self._live.values():
            if live.conversation_id == conversation_id and live.status == AWAITING:
                live.status = RUNNING
                self._store.runs.save(live)
                self._broadcast({"type": "run", "run": live.to_dict()})
                return live
        run = RunRecord(
            id=new_id(),
            agent_id=agent_id,
            conversation_id=conversation_id,
            source=source,
            title=title,
            status=RUNNING,
            started_at=now_iso(),
        )
        self._live[run.id] = run
        self._store.runs.save(run)
        self._broadcast({"type": "run", "run": run.to_dict()})
        return run

    def record(self, run: RunRecord, event: Event, clock: float) -> None:
        apply_event(run, event, clock)
        self._store.runs.save(run)
        payload = {
            "type": "event",
            "run_id": run.id,
            "agent_id": run.agent_id,
            "conversation_id": run.conversation_id,
            "status": run.status,
            "event": {"type": kind_of(event), **to_dict(event)},
        }
        self._broadcast(payload)
        if run.status not in ACTIVE_STATUSES:
            self.finish(run)

    def finish(self, run: RunRecord, status: str | None = None, summary: str = "") -> None:
        if status:
            run.status = status
        if summary:
            run.summary = summary
        run.finished_at = run.finished_at or now_iso()
        self._live.pop(run.id, None)
        self._store.runs.save(run)
        self._broadcast({"type": "run", "run": run.to_dict()})
        if run.conversation_id:
            self._finished.setdefault(run.conversation_id, asyncio.Event()).set()

    async def wait_finished(self, conversation_id: str, timeout: float) -> RunRecord | None:
        """Blocks until this conversation's run reaches a terminal status, and returns it.

        A run that pauses for an approval is not finished: the wait continues while the
        person decides, and ends when the resumed run does. `None` means the timeout ran
        out with the run still going, which the caller reports rather than hangs on."""
        event = self._finished.setdefault(conversation_id, asyncio.Event())
        try:
            await asyncio.wait_for(event.wait(), timeout)
        except TimeoutError:
            return None
        return self._store.runs.latest_for_conversation(conversation_id)

    def publish_conversation(self, conversation: dict[str, Any]) -> None:
        """Tells watchers a conversation changed outside a run — a new title, so far.

        The sidebar is built from a list fetched once, so a name written in the
        background would otherwise not appear until something else forced a reload."""
        self._broadcast({"type": "conversation", "conversation": conversation})

    def recent(
        self,
        limit: int = RECENT_LIMIT,
        conversation_ids: Sequence[str] | None = None,
        source: str | None = None,
    ) -> list[RunRecord]:
        """Newest runs first, optionally only those of some conversations or one source.

        The narrowing reaches the query and the live runs alike, so `limit` counts the rows
        actually asked for instead of whatever a busy crew left over."""
        stored = self._store.runs.recent(limit, conversation_ids=conversation_ids, source=source)
        by_id = {r.id: r for r in stored}
        wanted = None if conversation_ids is None else set(conversation_ids)
        for run in self._live.values():
            if (wanted is None or run.conversation_id in wanted) and (
                source is None or run.source == source
            ):
                by_id[run.id] = run
        return sorted(by_id.values(), key=lambda r: r.started_at, reverse=True)[:limit]

    def live(self) -> list[RunRecord]:
        return list(self._live.values())

    # --- streaming -----------------------------------------------------------------------

    def _broadcast(self, payload: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            queue.put_nowait(payload)

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            yield {"type": "snapshot", "runs": [r.to_dict() for r in self.live()]}
            while True:
                item = await queue.get()
                if item is None:
                    return
                yield item
        finally:
            self._subscribers.discard(queue)

    def close(self) -> None:
        for queue in list(self._subscribers):
            queue.put_nowait(None)


async def tracked(
    hub: ActivityHub,
    events: AsyncIterator[Event],
    agent_id: str,
    source: str,
    title: str,
    conversation_id: str | None,
) -> AsyncIterator[Event]:
    """Re-yields the loop's events while recording them on a run. A consumer that stops
    reading (client disconnect) leaves the run marked as failed, not running forever."""
    run = hub.start(agent_id, source, title, conversation_id)
    try:
        async for event in events:
            hub.record(run, event, time.monotonic())
            yield event
    finally:
        if run.status == RUNNING:
            hub.finish(run, status="error", summary="interrupted")
