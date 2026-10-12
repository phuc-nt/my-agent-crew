"""Who is in the crew while the server runs: agents that join it, one swapped for its
edited self, one that leaves. `Runtime` holds the crew, and these are what its methods of
the same names do.

Each ends on the two things a change of the crew leaves to be done: every agent's tools
are wired again for the crew as it now stands, and the clock reads again the schedules the
crew's files state. So an agent that joined, or one that was saved, runs its jobs on time
with no restart: a new job from its first time after this moment, a job whose timing
changed from this moment by the timing it has now, and a job taken out of the file never
again (`scheduler/table.py`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts
from my_agent_crew.agents import AgentProfile
from my_agent_crew.server.agent_assembly import build_agent_deps

if TYPE_CHECKING:
    from my_agent_crew.server.runtime import Runtime


def _peers(rt: Runtime) -> dict[str, Any]:
    """The map every agent reads its peers from, reached through the default agent."""
    return rt.default.peers if isinstance(rt.default.peers, dict) else {}


def add_agents(rt: Runtime, profiles: Iterable[AgentProfile]) -> list[str]:
    """Brings agents installed while the server runs into the crew: deps built the same way
    as at startup, the shared peer map extended, every delegating agent's tool rebuilt, the
    newcomers' schedules put on the clock. A channel is not started here; that needs a
    restart. Ids already present are skipped and not reported. Every newcomer is built
    before any joins: one that cannot be built leaves the crew as it was."""
    if rt.client is None:
        raise RuntimeError(texts.RUNTIME_CANNOT_GROW)
    peers = _peers(rt)
    fresh = [profile for profile in profiles if profile.id not in rt.agents]
    built = [
        build_agent_deps(p, rt.providers, rt.client, rt.store, rt.settings.routes) for p in fresh
    ]
    for profile, deps in zip(fresh, built, strict=True):
        deps.peers = peers
        rt.agents[profile.id] = deps
        peers[profile.id] = profile
    if fresh:
        rt.wire_delegation()
        rt.scheduler.reload_profiles()
    return [profile.id for profile in fresh]


def replace_agent(
    rt: Runtime, profile: AgentProfile, write: Callable[[], None] | None = None
) -> None:
    """Swaps in an edited profile without a restart. The deps are rebuilt, not patched:
    routes, skills and tools all derive from the profile, so a patched agent would not
    match what it can do. The shared peer map shows the new name to everyone else, and the
    clock goes by the schedules the profile states now.

    `write` puts the edit in the agent's file, and is called between the two halves. After
    the agent is built, which is the last step that can refuse an edit: one refused there
    is not on the disk. Before anything of the crew changes: a file that could not be
    written leaves the crew, the clock and every job's pause switch as they were."""
    if rt.client is None:
        raise RuntimeError(texts.RUNTIME_CANNOT_GROW)
    deps = build_agent_deps(profile, rt.providers, rt.client, rt.store, rt.settings.routes)
    if write is not None:
        write()
    peers = _peers(rt)
    deps.peers = peers
    rt.agents[profile.id] = deps
    peers[profile.id] = profile
    rt.wire_delegation()
    rt.scheduler.reload_profiles()


def remove_agent(rt: Runtime, agent_id: str) -> None:
    """Drops an agent from the running crew, and its jobs from the clock. Conversations
    that named it stay put and fall back to the default agent; nothing else is kept."""
    # The peer map is reached through the default agent, so it is taken before the pop
    # rather than after: dropping the default first would leave nothing to read it from.
    peers = _peers(rt)
    rt.agents.pop(agent_id, None)
    peers.pop(agent_id, None)
    rt.scheduler.forget_agent(agent_id)
    rt.wire_delegation()
