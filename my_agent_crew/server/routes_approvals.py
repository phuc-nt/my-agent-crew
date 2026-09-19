"""Approve or deny a pending tool call; the turn resumes as SSE either way."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from my_agent_crew.agent.loop import resolve_approval
from my_agent_crew.server.deps import ConvDeps, Rt
from my_agent_crew.server.routes_chat import sse_events, track_turn

router = APIRouter(tags=["approvals"])


class Decision(BaseModel):
    approve: bool


@router.post("/conversations/{conv_id}/approvals/{approval_id}")
async def decide(
    conv_id: str, approval_id: str, body: Decision, deps: ConvDeps, rt: Rt
) -> EventSourceResponse:
    try:
        approval = deps.store.approvals.get(approval_id)
    except KeyError as exc:
        raise HTTPException(404, "approval not found") from exc
    if approval.conversation_id != conv_id or approval.status != "pending":
        raise HTTPException(409, "approval already resolved")
    events = resolve_approval(deps, conv_id, approval_id, body.approve)
    return EventSourceResponse(sse_events(track_turn(rt, deps, conv_id, events)))
