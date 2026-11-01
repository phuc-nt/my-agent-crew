"""`GET /api/spend`: what each model provider has cost today and this month, for the figure
the header keeps in view. The sources and why Anthropic's is the crew's own count are in
`provider_spend.py`."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter

from my_agent_crew.server import provider_spend
from my_agent_crew.server.deps import Rt

router = APIRouter(tags=["activity"])


async def _openrouter(rt: Rt, key: str) -> dict[str, Any] | None:
    if rt.client is not None:
        return await provider_spend.cached_openrouter_report(rt.client, key)
    async with httpx.AsyncClient() as client:
        return await provider_spend.cached_openrouter_report(client, key)


@router.get("/spend")
async def spend(rt: Rt) -> dict[str, Any]:
    s = rt.settings
    today = s.today()
    billed = [
        name
        for name, key in (("anthropic", s.anthropic_api_key), ("openrouter", s.openrouter_api_key))
        if key
    ]
    return {
        "day": today.isoformat(),
        "month": today.isoformat()[:7],
        "providers": provider_spend.ledger_rows(rt.store.usage, today, s.zone, billed),
        "openrouter": await _openrouter(rt, s.openrouter_api_key) if s.openrouter_api_key else None,
    }
