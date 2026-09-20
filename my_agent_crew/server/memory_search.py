"""Searching every memory the crew has, labelled by whose it is.

`search_memory` answers for one agent at a time; the panel asks about all of them at once,
so this widens the same search and tags each hit with the scope it came from.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
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
    """Shared facts first, then each agent's own files. Without an agent, every agent."""
    if not query.strip():
        return []
    hits = [
        MemoryHit(scope=USER, agent_id="", file=file, text=text)
        for file, text in search_facts(rt.settings.user_dir, query)
    ]
    wanted = [agent_id] if agent_id is not None else list(rt.agents)
    for one in wanted:
        profile = rt.agents[one].profile
        hits.extend(
            MemoryHit(scope=AGENT, agent_id=one, file=file, text=text)
            for file, text in search_memory(profile.memory_dir, profile.memory_file, query)
        )
    return hits[:MAX_HITS]
