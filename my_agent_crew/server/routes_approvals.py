"""Approve or deny a pending tool call; the turn resumes as SSE either way. The history
of decided requests is listed across agents, so what was allowed can be reviewed later."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from my_agent_crew.agent.loop import resolve_approval
from my_agent_crew.server.deps import ConvDeps, Rt
from my_agent_crew.server.routes_chat import sse_events, track_turn

router = APIRouter(tags=["approvals"])
HISTORY_LIMIT = 50


class Decision(BaseModel):
    approve: bool
    # Approve and stop asking for this tool in this conversation.
    always: bool = False


@router.get("/approvals")
def list_approvals(rt: Rt, limit: int = Query(HISTORY_LIMIT, ge=1, le=500)) -> list[dict[str, Any]]:
    out = []
    for approval in rt.store.approvals.recent(limit):
        try:
            agent_id = rt.store.get(approval.conversation_id).agent_id
        except KeyError:
            agent_id = ""
        out.append({**approval.to_dict(), "agent_id": agent_id})
    return out


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
    events = resolve_approval(deps, conv_id, approval_id, body.approve, always=body.always)
    return EventSourceResponse(sse_events(track_turn(rt, deps, conv_id, events)))
