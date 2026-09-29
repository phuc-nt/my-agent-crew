"""Recording a loop's event stream as a run while passing it on unchanged."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from my_agent_crew.activity.hub import ActivityHub
from my_agent_crew.agent.events import Event
from my_agent_crew.store.runs import RUNNING


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
