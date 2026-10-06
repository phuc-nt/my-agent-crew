"""A turn as SSE, for the tab that started it and for any that joins while it runs.

The server reads the web's turns itself (`turn_host.py`), so a stream here is a view of a
turn and never the thing that keeps it going. `GET …/turn` is that view for a tab that did
not start the turn, or lost the stream it had: Telegram's and a job's turns can be watched
through it the same way."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Response
from sse_starlette.sse import AppStatus, EventSourceResponse

from my_agent_crew.activity.turn_watch import Frame, Resync
from my_agent_crew.agent.events import Event, kind_of, to_dict
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.server.deps import ConvDeps, Rt
from my_agent_crew.server.routes_conversations import conversation_detail

router = APIRouter(tags=["chat"])
WATCHING = "watching"


def _message(event: Event) -> dict[str, str]:
    return {"event": kind_of(event), "data": json.dumps(to_dict(event), ensure_ascii=False)}


async def sse_frames(
    deps: AgentDeps, conv_id: str, frames: AsyncIterator[Frame]
) -> AsyncIterator[dict[str, str]]:
    """One SSE message per event, under the event's own name. A `Resync` goes out as
    `watching`, carrying the conversation as it is stored at that moment, and is followed by
    the events that draw the answer being written; the reader replaces what it showed."""
    try:
        async for frame in frames:
            if not isinstance(frame, Resync):
                yield _message(frame)
                continue
            try:
                # Nothing is awaited between the frame being built and this read, so the
                # stored conversation and the replay are of one moment.
                detail = conversation_detail(deps, conv_id)
            except KeyError:
                return  # the conversation was deleted while it was watched
            watching = {"type": WATCHING, "running": frame.under_way, "detail": detail}
            data = json.dumps(watching, ensure_ascii=False)
            yield {"event": WATCHING, "data": data}
            for event in frame.replay:
                yield _message(event)
    finally:
        close = getattr(frames, "aclose", None)
        if close is not None:
            await close()  # a reader that left stops being held events for


@router.get("/conversations/{conv_id}/turn")
async def watch_turn(conv_id: str, deps: ConvDeps, rt: Rt) -> Response:
    """The turn under way: `watching` first, then its events as they come, ending when the
    turn does or pauses for a decision. 204 when the conversation has no turn to watch, and
    from a server told to stop: sse-starlette cuts a stream begun then before its first
    byte, a 500 to the tab that asked, and the turn is the next server's to carry on."""
    frames = None if AppStatus.should_exit else rt.hub.turns.join(conv_id)
    if frames is None:
        return Response(status_code=204)
    return EventSourceResponse(sse_frames(deps, conv_id, frames))
