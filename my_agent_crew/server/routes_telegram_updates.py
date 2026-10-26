"""Where a host that holds the bot's webhook hands its updates over
(`hosting.telegram_webhook`). A bot that polls takes none here: two ways in for one bot
would answer a message twice."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from my_agent_crew.server.deps import Rt

router = APIRouter(tags=["channels"])
NO_CHANNEL = "no telegram channel is running"
POLLING = "the bot polls; it takes no updates handed over"


class Updates(BaseModel):
    updates: list[dict[str, Any]]


@router.post("/channels/telegram/updates")
async def take_updates(body: Updates, rt: Rt) -> dict[str, int]:
    channel = rt.channel
    if channel is None or not rt.channel_live:
        raise HTTPException(503, NO_CHANNEL)
    if not channel.webhook:
        raise HTTPException(409, POLLING)
    if any("update_id" not in update for update in body.updates):
        raise HTTPException(422, "every update needs its update_id")
    return {"handled": await channel.receive(body.updates)}
