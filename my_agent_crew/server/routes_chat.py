"""POST a message, receive the turn as SSE. One event per loop event, same names. The
turn goes through the same `Inbound` gate as every other platform's, so it is recorded
on the activity hub like theirs."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from my_agent_crew.agent.events import Event, kind_of, to_dict
from my_agent_crew.inbound import InboundBusy
from my_agent_crew.server.deps import Rt

router = APIRouter(tags=["chat"])


class ChatBody(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


async def sse_events(events: AsyncIterator[Event]) -> AsyncIterator[dict[str, str]]:
    async for event in events:
        yield {"event": kind_of(event), "data": json.dumps(to_dict(event), ensure_ascii=False)}


@router.post("/conversations/{conv_id}/messages")
async def post_message(conv_id: str, body: ChatBody, rt: Rt) -> EventSourceResponse:
    try:
        events = rt.inbound.stream(conv_id, body.text)
    except KeyError as exc:
        raise HTTPException(404, "conversation not found") from exc
    except InboundBusy as exc:
        raise HTTPException(409, "awaiting approval") from exc
    return EventSourceResponse(sse_events(events))
