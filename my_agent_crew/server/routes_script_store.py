"""What an agent's scripts have kept (`store`, `load`), for a person to look at.

Reading only. A value is written by a script that ended well and by nothing else
(`script/store_session.py`), so there is no route here that changes one. Each namespace is
shown with its size as the limit on it counts, keys and values together, and each value
with the beginning of its JSON text: a value may be as long as a short book.
"""

from __future__ import annotations

from itertools import groupby
from typing import Any

from fastapi import APIRouter, HTTPException

from my_agent_crew.server.deps import Rt
from my_agent_crew.store.script_store import KeptValue, held_chars

router = APIRouter(tags=["agents"])
# How much of a value's JSON text is shown. The whole length is told beside it.
PREVIEW_CHARS = 200


def _entry(kept: KeptValue) -> dict[str, Any]:
    cut = len(kept.text) > PREVIEW_CHARS
    return {
        "key": kept.key,
        "preview": kept.text[:PREVIEW_CHARS] + "…" if cut else kept.text,
        "chars": len(kept.text),
        "updated_at": kept.updated_at,
    }


@router.get("/agents/{agent_id}/script-store")
def get_script_store(agent_id: str, rt: Rt) -> dict[str, Any]:
    try:
        deps = rt.deps_for(agent_id)
    except KeyError as exc:
        raise HTTPException(404, "agent not found") from exc
    kept = deps.store.script_store.kept_by(deps.agent.id)
    namespaces = []
    for namespace, rows in groupby(kept, key=lambda row: row.namespace):
        entries = list(rows)
        namespaces.append(
            {
                "namespace": namespace,
                "chars": held_chars({row.key: row.text for row in entries}),
                "entries": [_entry(row) for row in entries],
            }
        )
    return {"namespaces": namespaces}
