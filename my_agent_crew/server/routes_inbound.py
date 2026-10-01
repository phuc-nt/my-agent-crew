"""`POST /api/inbound`: a person's message from any platform, answered as one JSON reply.
A relay for a chat product that has no adapter of its own posts here; so does a test
that wants to walk the whole crew, delegation included, without a browser or a bot."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from my_agent_crew.agent.turn_context import (
    API,
    CHAT,
    DELEGATE,
    JOB,
    TELEGRAM,
    WEB,
    normalize_source,
)
from my_agent_crew.agents import DEFAULT_AGENT_ID
from my_agent_crew.agents.kit_commands import EmptySteer
from my_agent_crew.inbound import InboundBusy
from my_agent_crew.server.deps import Rt
from my_agent_crew.store.queue import QueueFull

router = APIRouter(tags=["inbound"])

# The names the server gives its own turns. A relay that borrowed one would be taken for
# that channel: the person watching in chat, the Telegram bot, a delegated child, a memory
# job, or a scheduled job, whose last run and run history are looked up by source.
INTERNAL_SOURCES = frozenset({CHAT, TELEGRAM, JOB, DELEGATE, WEB})
INTERNAL_PREFIXES = ("memory:",)


class InboundBody(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    agent_id: str = DEFAULT_AGENT_ID
    # Where the person is talking from: one conversation per agent per day on a channel.
    channel: str = API
    # Continue this conversation instead of today's on the channel.
    conversation_id: str | None = None
    # Recorded on the run, so the activity view can tell platforms apart.
    source: str = API

    @field_validator("source")
    @classmethod
    def _not_internal(cls, source: str) -> str:
        if normalize_source(source) in INTERNAL_SOURCES or source.startswith(INTERNAL_PREFIXES):
            raise ValueError(f"source {source!r} names one of the server's own channels")
        return source


@router.post("/inbound")
async def post_inbound(body: InboundBody, rt: Rt) -> dict[str, Any]:
    try:
        if body.conversation_id:
            conv = rt.store.get(body.conversation_id)
        else:
            conv = rt.inbound.conversation_for(body.agent_id, body.channel, rt.settings.now)
        reply = await rt.inbound.reply(conv.id, body.text, source=body.source)
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0]) if exc.args else "not found") from exc
    except InboundBusy as exc:
        raise HTTPException(409, "awaiting approval") from exc
    except EmptySteer as exc:
        raise HTTPException(422, str(exc)) from exc
    except QueueFull as exc:
        raise HTTPException(429, str(exc)) from exc
    # A queued message has no answer yet: the turn it waits for answers it later, into the
    # conversation, where a relay reads it back if it needs it.
    queued = reply.status == "queued"
    return {
        "conversation_id": conv.id,
        "agent_id": conv.agent_id,
        **reply.to_dict(),
        "queued": queued,
    }
