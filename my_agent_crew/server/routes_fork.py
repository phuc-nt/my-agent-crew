"""Rewind and fork a conversation: "Sửa và gửi lại từ đây". See `store/fork.py` for the
copy itself and its Key Insights for why an open tool call at the cut must be closed, not
carried over, before the fork is handed back to the person."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from my_agent_crew.agent.tool_calls import refuse_unanswered
from my_agent_crew.server.deps import ConvDeps
from my_agent_crew.texts import FORK_CALL_NOT_RUN

router = APIRouter(tags=["conversations"])


class ForkRequest(BaseModel):
    before_message_id: int = Field(gt=0)


@router.post("/conversations/{conv_id}/fork", status_code=201)
async def fork_conversation(conv_id: str, body: ForkRequest, deps: ConvDeps) -> dict[str, Any]:
    try:
        fork, draft = deps.store.fork(
            conv_id, body.before_message_id, autonomous=deps.settings.autonomous_default
        )
    except KeyError as exc:
        raise HTTPException(404, "conversation or message not found") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    try:
        # Read to the end: an async generator that is never iterated never runs, and the
        # calls it would have closed would stay open, ready to be run for real on resume.
        async for _ in refuse_unanswered(deps, fork.id, FORK_CALL_NOT_RUN):
            pass
    except Exception:
        deps.store.delete(fork.id)
        raise
    return {**fork.to_dict(), "draft": draft}
