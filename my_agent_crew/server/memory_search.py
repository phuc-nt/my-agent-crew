"""Searching every memory the crew has, labelled by whose it is.

`search_memory` answers for one agent at a time; the panel asks about all of them at once,
so this widens the same search and tags each hit with the scope it came from.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import zip_longest
from typing import TYPE_CHECKING, Any

from my_agent_crew.tools.memory import search_facts, search_memory

if TYPE_CHECKING:
    from my_agent_crew.server.runtime import Runtime

USER, AGENT = "user", "agent"
MAX_HITS = 50


@dataclass(frozen=True)
class MemoryHit:
    scope: str
    agent_id: str
    file: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def search_all(rt: Runtime, query: str, agent_id: str | None = None) -> list[MemoryHit]:
    """Shared facts first, then the agents' own files. Without an agent, every agent, their
    hits interleaved by rank: each agent's best entry comes before any agent's second one.
    Appending whole lists instead would put a note-heavy agent's weakest matches ahead of
    another agent's only exact one."""
    if not query.strip():
        return []
    hits = [
        MemoryHit(scope=USER, agent_id="", file=file, text=text)
        for file, text in search_facts(rt.settings.user_dir, query)
    ]
    wanted = [agent_id] if agent_id is not None else list(rt.agents)
    ranked = [agent_hits(rt, one, query) for one in wanted]
    for rank in zip_longest(*ranked):
        hits.extend(hit for hit in rank if hit is not None)
    return hits[:MAX_HITS]


def agent_hits(rt: Runtime, agent_id: str, query: str) -> list[MemoryHit]:
    """One agent's hits in the order `search_memory` ranks them."""
    profile = rt.agents[agent_id].profile
    return [
        MemoryHit(scope=AGENT, agent_id=agent_id, file=file, text=text)
        for file, text in search_memory(profile.memory_dir, profile.memory_file, query)
    ]
