"""Changing the model routes every agent falls back on, from the web.

These are the routes an agent without its own `routes` answers with, and the ones an
agent's own routes fall back to when none of theirs has a key. They are read from
`MY_AGENT_ROUTES` first, then from `routes` in `<home>/config.yaml`, then the default;
the page writes the file, so while the variable is set the page shows them read-only
rather than saving something the variable would hide.

A change is tried before it is kept, like a key: the crew is built with the new routes
and a list it cannot run with is refused with the reason. The file is written round-trip,
so its comments and other keys stay as they were typed.
"""

from __future__ import annotations

import os
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ruamel.yaml import YAMLError

from my_agent_crew import texts_credentials as t
from my_agent_crew.agents.profile_write import read_raw, write_raw
from my_agent_crew.config_parse import Route
from my_agent_crew.server.agent_edit_common import write_lock
from my_agent_crew.server.connection_apply import apply, prepared_or_refused
from my_agent_crew.server.deps import Rt
from my_agent_crew.server.routes_registry import ROUTES_ENV, config_path, list_connections
from my_agent_crew.server.runtime_connections import channel_key

MAX_ROUTES = 10
FAKE = "fake"
# A provider is a plain name; a model id may carry `/`, `:`, `.` or `@` (an Ollama tag,
# an OpenRouter variant) but never a space or a comma, which the env form splits on.
PROVIDER_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
MODEL_RE = re.compile(r"^[^\s,]{1,200}$")

router = APIRouter(tags=["registry"])


class RouteBody(BaseModel):
    provider: str
    model: str


class RoutesRequest(BaseModel):
    routes: list[RouteBody]


def _checked(body: RoutesRequest) -> list[Route]:
    if not body.routes:
        raise HTTPException(422, t.ROUTES_EMPTY)
    if len(body.routes) > MAX_ROUTES:
        raise HTTPException(422, t.ROUTES_TOO_MANY.format(limit=MAX_ROUTES))
    routes = []
    for item in body.routes:
        provider, model = item.provider.strip(), item.model.strip()
        if not PROVIDER_RE.match(provider) or not MODEL_RE.match(model):
            raise HTTPException(422, t.ROUTE_INVALID.format(route=f"{provider}:{model}"[:120]))
        routes.append(Route(provider=provider, model=model))
    return list(dict.fromkeys(routes))


def _adds_fake(routes: list[Route], saved: tuple[Route, ...]) -> bool:
    return any(r.provider == FAKE for r in routes) and all(r.provider != FAKE for r in saved)


@router.put("/connections/routes")
async def set_routes(body: RoutesRequest, rt: Rt) -> dict[str, Any]:
    routes = _checked(body)
    if os.environ.get(ROUTES_ENV):
        raise HTTPException(409, t.ROUTES_FROM_ENV.format(env=ROUTES_ENV))
    async with write_lock:
        # A route whose provider has no key would be dropped without a word at build time;
        # saying so here beats a saved list that quietly means less than it shows.
        missing = sorted({r.provider for r in routes} - set(rt.providers))
        if missing:
            raise HTTPException(409, t.ROUTES_NO_PROVIDER.format(providers=", ".join(missing)))
        # `fake` echoes the prompt back: a crew that already runs on it (a demo, a test
        # home) may keep it, but a real crew does not gain it from one wrong pick.
        if _adds_fake(routes, rt.settings.routes):
            raise HTTPException(409, t.ROUTES_FAKE)
        prepared = prepared_or_refused(rt, os.environ, routes)
        path = config_path(rt.settings.home)
        try:
            data = read_raw(path)
        except (OSError, ValueError, YAMLError) as exc:
            raise HTTPException(409, t.NOT_APPLICABLE.format(error=str(exc))) from None
        data["routes"] = [f"{r.provider}:{r.model}" for r in routes]
        before = channel_key(rt.agents, os.environ)
        try:
            write_raw(path, data)
        except OSError as exc:
            raise HTTPException(409, t.CONFIG_UNWRITABLE.format(error=str(exc))) from None
        problem = await apply(rt, prepared, before)
    return {**list_connections(rt), "restart_required": problem}
