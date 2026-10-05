"""Approve or deny a pending tool call; the turn resumes as SSE either way, read to its
end by the server like the turn a message starts. The history of decided requests is listed
across agents, so what was allowed can be reviewed later.

A question the agent asked is a row in the same table and resumes down the same stream,
but it is closed on its own route: its outcome is the person's words, and a yes with no
words in it would tell the agent nothing."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from my_agent_crew.inbound import InboundBusy
from my_agent_crew.server.deps import ConvDeps, Rt
from my_agent_crew.server.routes_turn import sse_frames
from my_agent_crew.store.models import QUESTION

router = APIRouter(tags=["approvals"])
HISTORY_LIMIT = 50


class Decision(BaseModel):
    approve: bool
    # Approve and stop asking for this tool in this conversation.
    always: bool = False


class Answer(BaseModel):
    # What the person said. Free text even when the question offered choices: the agent
    # asked because it could not decide, and narrowing the reply to the buttons it
    # happened to think of would lose the part that was worth asking for.
    answer: str


@router.get("/approvals")
def list_approvals(
    rt: Rt,
    limit: int = Query(HISTORY_LIMIT, ge=1, le=500),
    conversation_id: str | None = None,
) -> list[dict[str, Any]]:
    """Settled approval requests, newest first, optionally only one conversation's."""
    out = []
    for approval in rt.store.approvals.recent(limit, conversation_id):
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
    if approval.kind == QUESTION:
        raise HTTPException(409, "this is a question; answer it instead")
    try:
        events = rt.inbound.decide(conv_id, approval_id, body.approve, always=body.always)
    except InboundBusy as exc:  # a decision taken a moment ago holds it, still unapplied
        raise HTTPException(409, "approval already resolved") from exc
    return EventSourceResponse(sse_frames(deps, conv_id, rt.inbound.host.run(conv_id, events)))


@router.post("/conversations/{conv_id}/approvals/{approval_id}/answer")
async def answer(
    conv_id: str, approval_id: str, body: Answer, deps: ConvDeps, rt: Rt
) -> EventSourceResponse:
    try:
        approval = deps.store.approvals.get(approval_id)
    except KeyError as exc:
        raise HTTPException(404, "approval not found") from exc
    if approval.conversation_id != conv_id or approval.status != "pending":
        raise HTTPException(409, "approval already resolved")
    if approval.kind != QUESTION:
        raise HTTPException(409, "this is a tool call; approve or deny it instead")
    if not body.answer.strip():
        raise HTTPException(422, "answer is empty")
    try:
        events = rt.inbound.answer(conv_id, approval_id, body.answer)
    except InboundBusy as exc:
        raise HTTPException(409, "approval already resolved") from exc
    return EventSourceResponse(sse_frames(deps, conv_id, rt.inbound.host.run(conv_id, events)))
