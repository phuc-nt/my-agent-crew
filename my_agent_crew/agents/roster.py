"""Who an agent may hand work to, and how that crew is described to it.

The master (the default agent) is the one the person talks to. Unless its manifest names
a `delegates` list, it may reach every other agent on the machine: installing an agent is
enough to put it at the master's disposal. Any other agent reaches only what it lists.
"""

from __future__ import annotations

from collections.abc import Mapping

from my_agent_crew import texts
from my_agent_crew.agents.profile import AgentProfile

# The name of the tool that hands a task over. It lives here rather than in the tool
# module so the prompt side can ask "does this agent delegate?" without importing the
# tool, which imports the loop, which builds the prompt.
DELEGATE_TOOL_NAME = "delegate"


def delegate_targets(profile: AgentProfile, peers: Mapping[str, AgentProfile]) -> tuple[str, ...]:
    """The agents `profile` may delegate to, itself excluded (self is always allowed and
    handled by the tool). Order follows `peers`, which is load order: sorted by id."""
    if profile.delegates or not profile.is_master:
        return profile.delegates
    return tuple(agent_id for agent_id in peers if agent_id != profile.id)


def crew_roster_section(
    profile: AgentProfile, peers: Mapping[str, AgentProfile]
) -> tuple[str, str] | None:
    """A system-prompt section listing each agent this one may hand work to, with the
    guidance on when to. None when there is nobody to list: the tool then only offers a
    clean second context of the agent itself, which needs no roster."""
    ids = delegate_targets(profile, peers)
    targets = [peers[agent_id] for agent_id in ids if agent_id in peers]
    if not targets:
        return None
    lines = [
        texts.CREW_ROSTER_LINE.format(
            id=peer.id,
            name=peer.name,
            mode=peer.mode,
            description=peer.description or texts.CREW_ROSTER_NO_DESCRIPTION,
        )
        for peer in targets
    ]
    return texts.CREW_ROSTER_TITLE, "\n".join([texts.CREW_ROSTER_INTRO, *lines])
