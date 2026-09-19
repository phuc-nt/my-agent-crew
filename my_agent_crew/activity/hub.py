"""The activity hub: every turn and job is a run with a step timeline. Runs are stored
as they progress and broadcast to whoever is watching `/api/activity/stream`, so the UI
can show all agents working at once, not only the conversation on screen."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
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
        self._store.runs.mark_interrupted(now_iso())

    # --- runs ----------------------------------------------------------------------------

    def start(
        self, agent_id: str, source: str, title: str, conversation_id: str | None
    ) -> RunRecord:
        """A turn that resumes after an approval continues the run that paused."""
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

    def recent(self, limit: int = RECENT_LIMIT) -> list[RunRecord]:
        stored = self._store.runs.recent(limit)
        by_id = {r.id: r for r in stored}
        by_id.update(self._live)
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
