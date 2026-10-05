"""POST a message, receive the turn as SSE. One event per loop event, same names. The
turn goes through the same `Inbound` gate as every other platform's, so it is recorded
on the activity hub like theirs, and the server reads it to its end: the stream answering
the POST is a view of the turn, so a tab that closes stops watching and the turn goes on. A
message sent while the conversation is busy is queued and its stream is the one `queued`
event; `stop` withdraws what still waits and ends the turn."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from my_agent_crew.agents.kit_commands import EmptySteer
from my_agent_crew.inbound import InboundBusy
from my_agent_crew.server.deps import ConvDeps, Rt
from my_agent_crew.server.routes_canvas_focus import FocusBody, apply_focus, check_focus
from my_agent_crew.server.routes_turn import sse_frames
from my_agent_crew.store.queue import QueueFull

router = APIRouter(tags=["chat"])


class ChatBody(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    canvas: FocusBody | None = None  # the canvas open in the sending tab; absent leaves it
    # The sender's own name for this send. One it makes again under the same name, having
    # never heard the answer, starts nothing new; without a name every POST is a new send.
    request_id: str = Field(default="", max_length=64, pattern=r"^[A-Za-z0-9_-]*$")


@router.post("/conversations/{conv_id}/messages")
async def post_message(conv_id: str, body: ChatBody, deps: ConvDeps, rt: Rt) -> EventSourceResponse:
    """The sending tab's canvas is checked before the gate, so a selection the note would
    drop stores and queues nothing, and applied right after it with no `await` in between:
    a message the gate refuses leaves the open canvas, and the turn's note, built only as
    the stream is read or the queued message delivered, names the new one. A send made
    again is answered with what became of the first, and changes nothing."""
    canvas = body.canvas
    try:
        again = rt.inbound.repeated(conv_id, body.request_id)
    except KeyError as exc:
        raise HTTPException(404, "conversation not found") from exc
    if again is not None:
        return EventSourceResponse(sse_frames(deps, conv_id, again))
    present = False if canvas is None else check_focus(rt.store, canvas)
    try:
        frames = rt.inbound.stream_hosted(conv_id, body.text, body.request_id)
    except KeyError as exc:
        raise HTTPException(404, "conversation not found") from exc
    except InboundBusy as exc:
        raise HTTPException(409, "awaiting approval") from exc
    except EmptySteer as exc:
        raise HTTPException(422, str(exc)) from exc
    except QueueFull as exc:
        raise HTTPException(429, str(exc)) from exc
    if canvas is not None:
        apply_focus(rt.store, conv_id, canvas, present)
    return EventSourceResponse(sse_frames(deps, conv_id, frames))


@router.post("/conversations/{conv_id}/stop")
async def stop(conv_id: str, deps: ConvDeps, rt: Rt) -> dict[str, Any]:
    """Hands back the texts still waiting, removed from the queue, and ends the turn the
    server reads for the conversation: one the queue runs, or one the web started.
    `cancelled` is false when there is no such turn: one that a bot or a job reads belongs
    to its reader. Async so the cancel happens on the event loop that runs the turn."""
    cleared = deps.store.queue.take_all(conv_id)
    cancelled = rt.drain.cancel(conv_id)
    cancelled = rt.inbound.host.cancel(conv_id) or cancelled
    return {"cleared": [item.to_dict() for item in cleared], "cancelled": cancelled}
