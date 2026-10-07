"""What each agent of the running crew can do at this instant (`agents/abilities.py`), read
from where the runtime keeps it: the tools in an agent's registry, the skills it loaded,
the MCP servers its profile names with how each connection stands, the jobs the scheduler
holds for it and the routes it was built with.

Read each time a prompt is built and kept nowhere, so a server, a skill, a job or a tool
that came or went is told on the very next model call, whoever changed it and however.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

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


def _services(deps: AgentDeps, links: Mapping[str, hub.Link]) -> tuple[Service, ...]:
    """A server by the tools of it the agent holds now, and by why when it holds none."""
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
        if tools:
            # A tool the owner did not say only reads asks first: it may write.
            writes = any(tool.requires_approval for tool in tools)
            standing = READ_WRITE if writes else READ_ONLY
        elif link.status == hub.CONNECTED:
            # Reached, and nothing of it is for agents: there is nothing to hand work for.
            continue
        else:
            standing = SIGNED_OUT if link.status == hub.SIGNED_OUT else DOWN
        services.append(Service(name, standing, link.server.description))
    return tuple(services)


def _abilities(deps: AgentDeps, links: Mapping[str, hub.Link], jobs: Sequence[str]) -> Abilities:
    names = deps.tools.names()
    tools = [n for n in names if n != DELEGATE_TOOL_NAME and not n.startswith(PREFIX)]
    routes, spare = deps.settings.routes, deps.settings.escalation_route
    return Abilities(
        tools=tuple(tools),
        skills=tuple((skill.name, skill.description) for skill in deps.skills),
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
    return {
        agent_id: _abilities(deps, links, jobs.get(agent_id, ()))
        for agent_id, deps in rt.agents.items()
    }
