"""`GET /api/messages/search`, over HTTP: the same index `conversation_search` reads, for
the person at the keyboard rather than a model.

Not under `/conversations/…`: `GET /conversations/{conv_id}` is registered first in
`ROUTERS` and would catch a literal `/conversations/search` as that path parameter before
this route ever saw the request.

Unlike the tool, this route has no `agent` scoping question to answer: the person calling
it already owns the whole crew, and the route only runs locally, like every other one
here. `agent_id` narrows the search; it does not gate who may run it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from my_agent_crew.server.deps import Rt

router = APIRouter(tags=["search"])


@router.get("/messages/search")
def search_messages(
    rt: Rt,
    q: str = "",
    agent_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    agent_ids = [agent_id] if agent_id is not None else None
    hits = rt.store.search.find(q, agent_ids=agent_ids, limit=limit)
    return {"hits": [hit.to_dict() for hit in hits]}
