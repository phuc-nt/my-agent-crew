"""Everything the server holds for its lifetime: one store, one activity hub, one
scheduler, and one `AgentDeps` per agent profile. All agents share the store and the
provider clients; each gets its own workspace, memory, skills, shell cwd and routes.
Building a runtime from a home directory is `runtime_build`."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any

import httpx

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents import DEFAULT_AGENT_ID, AgentProfile
from my_agent_crew.channels import TelegramChannel
from my_agent_crew.config import Route, Settings
from my_agent_crew.memory.session_summary import schedule_summary
from my_agent_crew.scheduler import Scheduler
from my_agent_crew.server.agent_assembly import build_agent_deps
from my_agent_crew.store import Store
from my_agent_crew.tools.delegate import DELEGATE_TOOL_NAME, build_delegate_tool

# Models can think for well over httpx's 5 s default before the first token arrives; the
# shared client must wait as long as the provider itself would.
PROVIDER_TIMEOUT_SECONDS = 120.0


@dataclass
class Runtime:
    settings: Settings
    store: Store
    agents: dict[str, AgentDeps]
    hub: ActivityHub
    channels: dict[str, TelegramChannel] = field(default_factory=dict)
    # What `add_agents` needs to build deps for an agent installed while running; a
    # runtime made without them (tests around one agent) cannot grow, and says so.
    providers: dict[str, Any] = field(default_factory=dict)
    client: httpx.AsyncClient | None = None
    # Agents whose MEMORY.md is being rewritten right now; a second request is a conflict.
    consolidating: set[str] = field(default_factory=set)
    scheduler: Scheduler = field(init=False)

    def __post_init__(self) -> None:
        self.scheduler = Scheduler(self.agents, self.hub, deliver=self.deliver)
        for channel in self.unique_channels():
            channel.set_on_replaced(self.summarize_replaced)

    def summarize_replaced(self, deps: AgentDeps, conv_id: str) -> None:
        """A channel opened a new conversation; recap the one it replaced in the
        background, held by the scheduler so the task is not collected mid-flight."""
        schedule_summary(self.scheduler.keep, deps, conv_id)

    async def deliver(self, agent_id: str, conv_id: str) -> bool:
        """Pushes a conversation's last reply through the agent's channel, if it has one;
        False when the agent has no channel or the channel found nothing to send."""
        channel = self.channels.get(agent_id)
        if channel is None:
            return False
        return await channel.deliver(conv_id)

    def unique_channels(self) -> list[TelegramChannel]:
        """A bot shared by several agents is one object listed under each agent id."""
        seen: dict[int, TelegramChannel] = {}
        for channel in self.channels.values():
            seen.setdefault(id(channel), channel)
        return list(seen.values())

    def start_channels(self) -> None:
        for channel in self.unique_channels():
            channel.start()

    async def stop_channels(self) -> None:
        for channel in self.unique_channels():
            await channel.stop()

    @property
    def default(self) -> AgentDeps:
        return self.agents[DEFAULT_AGENT_ID]

    def deps_for(self, agent_id: str) -> AgentDeps:
        try:
            return self.agents[agent_id]
        except KeyError as exc:
            raise KeyError(texts.AGENT_UNKNOWN.format(agent_id=agent_id)) from exc

    def deps_for_child(self, agent_id: str) -> AgentDeps:
        """The same agent, minus `delegate`. A child that could delegate would make the
        depth limit a matter of the model reading its instructions carefully."""
        deps = self.deps_for(agent_id)
        return replace(deps, tools=deps.tools.without(DELEGATE_TOOL_NAME))

    def delegates(self, deps: AgentDeps) -> bool:
        """The master and every work agent hand work out, as does any agent whose profile
        names delegates. A profile that lists its tools is capping what it gets, and that
        cap covers this one too, so a specialist stays a specialist instead of quietly
        becoming a lead."""
        profile = deps.agent
        if profile.tools and DELEGATE_TOOL_NAME not in profile.tools:
            return False
        return profile.is_master or profile.is_work or bool(profile.delegates)

    def wire_delegation(self) -> None:
        """Agents that delegate get the tool once every agent exists — it holds the
        runtime, so it cannot be built during assembly, when the runtime is still being
        made. Called again after `add_agents`, it rebuilds every tool so the targets each
        one offers include the newcomers."""
        for deps in self.agents.values():
            if not self.delegates(deps):
                continue
            if deps.tools.get(DELEGATE_TOOL_NAME) is not None:
                deps.tools = deps.tools.without(DELEGATE_TOOL_NAME)
            deps.tools.register(build_delegate_tool(self, deps.agent))

    def add_agents(self, profiles: Iterable[AgentProfile]) -> list[str]:
        """Brings agents installed while the server runs into this runtime: deps built
        the same way as at startup, the shared peer map extended, every delegating agent's
        tool rebuilt. Channels and schedules are not started here; those need a restart.
        Ids already present are skipped and not reported."""
        if self.client is None:
            raise RuntimeError(texts.RUNTIME_CANNOT_GROW)
        added: list[str] = []
        peers = self.default.peers if isinstance(self.default.peers, dict) else {}
        for profile in profiles:
            if profile.id in self.agents:
                continue
            deps = build_agent_deps(
                profile, self.providers, self.client, self.store, self.fallback_routes
            )
            deps.peers = peers
            self.agents[profile.id] = deps
            peers[profile.id] = profile
            added.append(profile.id)
        if added:
            self.wire_delegation()
        return added

    @property
    def fallback_routes(self) -> tuple[Route, ...]:
        return self.settings.routes

    def deps_for_conversation(self, conv_id: str) -> AgentDeps:
        """Raises KeyError for an unknown conversation; a conversation whose agent profile
        was removed from disk falls back to the default agent rather than 404."""
        conv = self.store.get(conv_id)
        return self.agents.get(conv.agent_id) or self.default

    def profiles(self) -> list[AgentProfile]:
        return [deps.agent for deps in self.agents.values()]

    @classmethod
    def single(cls, deps: AgentDeps) -> Runtime:
        """A runtime around one already-built default agent; what tests hand to the app."""
        hub = ActivityHub(deps.store)
        runtime = cls(
            settings=deps.settings, store=deps.store, agents={deps.agent.id: deps}, hub=hub
        )
        runtime.wire_delegation()
        return runtime
