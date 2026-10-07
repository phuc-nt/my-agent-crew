"""What each agent of the running crew can do at this instant (`agents/abilities.py`), read
from where the runtime keeps it: the tools in an agent's registry, the skills it loaded,
the MCP servers its profile names with how each connection stands, the jobs the scheduler
holds for it and the routes it was built with.

Read each time a prompt is built and kept nowhere, so what is told is what the agent itself
can use at that moment: a server that connected, dropped or lost its sign-in, a job switched
on or off and a tool given or taken are in the very next model call. A skill file put on
disk is told once the agent is built again (an edit of the agent, or a restart), which is
also when the agent itself first holds it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from my_agent_crew import texts
from my_agent_crew.agents.abilities import (
    DOWN,
    READ_ONLY,
    READ_WRITE,
    SIGNED_OUT,
    Abilities,
    Service,
)
from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME
from my_agent_crew.agents.schedule import CONSOLIDATE
from my_agent_crew.mcp import hub
from my_agent_crew.mcp.tools import PREFIX, McpTool

if TYPE_CHECKING:
    from my_agent_crew.agent.loop import AgentDeps
    from my_agent_crew.server.runtime import Runtime
    from my_agent_crew.skills import Skill


def _services(deps: AgentDeps, links: Mapping[str, hub.Link]) -> tuple[Service, ...]:
    """A server by how its connection stands, then by the tools of it the agent holds."""
    held: dict[str, list[McpTool]] = {}
    for name in deps.tools.names():
        tool = deps.tools.get(name)
        if isinstance(tool, McpTool):
            held.setdefault(tool.server, []).append(tool)
    services = []
    for name in dict.fromkeys(deps.agent.mcp):
        link = links.get(name)
        if link is None:
            continue
        tools = held.get(name)
        # The connection first: a sign-in that ended or a key the server stopped taking
        # leaves the agent holding tools none of which can be called.
        if link.status == hub.SIGNED_OUT:
            standing = SIGNED_OUT
        elif link.status != hub.CONNECTED:
            standing = DOWN
        elif not tools:
            # Reached, and nothing of it is for agents: there is nothing to hand work for.
            continue
        else:
            # A tool neither the owner nor the server says only reads may write.
            writes = any(tool.requires_approval and not tool.read_only_hint for tool in tools)
            standing = READ_WRITE if writes else READ_ONLY
        services.append(Service(name, standing, link.server.description))
    return tuple(services)


def _skill(skill: Skill) -> tuple[str, str]:
    """A skill whose command is not on this machine is told so, in the words of its owner's
    own index and ahead of what it is for, where a long description cannot push it out."""
    if not skill.missing_bins:
        return skill.name, skill.description
    missing = texts.SKILL_INDEX_MISSING_BINS.format(bins=", ".join(skill.missing_bins))
    return skill.name, f"{missing} {skill.description}".strip()


def _abilities(deps: AgentDeps, links: Mapping[str, hub.Link], jobs: Sequence[str]) -> Abilities:
    names = deps.tools.names()
    tools = [n for n in names if n != DELEGATE_TOOL_NAME and not n.startswith(PREFIX)]
    routes, spare = deps.settings.routes, deps.settings.escalation_route
    return Abilities(
        tools=tuple(tools),
        skills=tuple(_skill(skill) for skill in deps.skills),
        services=_services(deps, links),
        jobs=tuple(jobs),
        model=routes[0].model if routes else "",
        # Named and usable: a route whose provider has no key was left out when the agent
        # was built, and a turn of it never moves there.
        escalation=spare.model if spare and deps.escalation else "",
    )


def crew_abilities(rt: Runtime) -> dict[str, Abilities]:
    jobs: dict[str, list[str]] = {}
    for job in rt.scheduler.jobs():
        # Tidying its own memory is upkeep every agent has, not work it can be handed.
        if job.schedule.kind != CONSOLIDATE and rt.scheduler.enabled(job):
            jobs.setdefault(job.agent_id, []).append(job.schedule.name or job.schedule.id)
    links = rt.mcp.links
    # A prompt is also built off the event loop (the preview route), while an edit of an
    # agent may be replacing entries: read from a copy of the listing.
    return {
        agent_id: _abilities(deps, links, jobs.get(agent_id, ()))
        for agent_id, deps in list(rt.agents.items())
    }
