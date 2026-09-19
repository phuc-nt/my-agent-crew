"""POST a message, receive the turn as SSE. One event per loop event, same names. Every
turn is also recorded on the activity hub so other views can watch it."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from my_agent_crew.activity import tracked
from my_agent_crew.agent.events import Event, kind_of, to_dict
from my_agent_crew.agent.loop import AgentDeps, ConversationBusy, run_turn
from my_agent_crew.server.deps import ConvDeps, Rt
from my_agent_crew.server.runtime import Runtime

router = APIRouter(tags=["chat"])
CHAT_SOURCE = "chat"


class ChatBody(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


async def sse_events(events: AsyncIterator[Event]) -> AsyncIterator[dict[str, str]]:
    async for event in events:
        yield {"event": kind_of(event), "data": json.dumps(to_dict(event), ensure_ascii=False)}


def track_turn(rt: Runtime, deps: AgentDeps, conv_id: str, events: AsyncIterator[Event]):
    conv = deps.store.get(conv_id)
    return tracked(rt.hub, events, deps.agent.id, CHAT_SOURCE, conv.title, conv.id)


@router.post("/conversations/{conv_id}/messages")
async def post_message(conv_id: str, body: ChatBody, deps: ConvDeps, rt: Rt) -> EventSourceResponse:
    if deps.store.approvals.pending(conv_id) is not None:
        raise HTTPException(409, "awaiting approval")
    try:
        events = run_turn(deps, conv_id, body.text)
    except ConversationBusy as exc:
        raise HTTPException(409, "awaiting approval") from exc
    return EventSourceResponse(sse_events(track_turn(rt, deps, conv_id, events)))
