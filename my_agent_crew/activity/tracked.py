"""Recording a loop's event stream as a run while passing it on unchanged."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from my_agent_crew import texts
from my_agent_crew.activity.hub import ActivityHub
from my_agent_crew.agent.events import ErrorEvent, Event
from my_agent_crew.store.runs import RUNNING


async def tracked(
    hub: ActivityHub,
    events: AsyncIterator[Event],
    agent_id: str,
    source: str,
    title: str,
    conversation_id: str | None,
) -> AsyncIterator[Event]:
    """Re-yields the loop's events while recording them on a run, and passes them to
    whoever watches the conversation. A reader that stops reading leaves the run marked as
    failed, not running forever. The watchers are let go the moment the run is over or
    pauses for a decision: from then on the conversation may start its next turn, which is
    not this one's to end."""
    run = hub.start(agent_id, source, title, conversation_id)
    turn = hub.turns.begin(conversation_id) if conversation_id else None
    try:
        async for event in events:
            hub.record(run, event, time.monotonic())
            if turn is not None and conversation_id:
                turn.publish(event)
                if run.status != RUNNING:
                    hub.turns.end(conversation_id, turn)
            yield event
    except Exception:
        # The reader hears of it from the exception; a watcher has only the events.
        if turn is not None:
            turn.publish(ErrorEvent(message=texts.TURN_BROKE))
        raise
    finally:
        if turn is not None and conversation_id:
            hub.turns.end(conversation_id, turn)
        if run.status == RUNNING:
            hub.finish(run, status="error", summary="interrupted")
