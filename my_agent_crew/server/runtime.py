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
from my_agent_crew.inbound import Inbound
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
    # The master's Telegram bot, when its profile names one and the token is set.
    channel: TelegramChannel | None = None
    # What `add_agents` needs to build deps for an agent installed while running; a
    # runtime made without them (tests around one agent) cannot grow, and says so.
    providers: dict[str, Any] = field(default_factory=dict)
    client: httpx.AsyncClient | None = None
    # Agents whose MEMORY.md is being rewritten right now; a second request is a conflict.
    consolidating: set[str] = field(default_factory=set)
    # Whether the channel was started by the app's lifespan; a rebuilt one follows suit
    # (`runtime_connections`).
    channel_live: bool = False
    scheduler: Scheduler = field(init=False)
    # The gate every platform's messages pass through; it shares `agents`, so it grows too.
    inbound: Inbound = field(init=False)

    def __post_init__(self) -> None:
        self.scheduler = Scheduler(
            self.agents, self.hub, clock=self.settings.now, deliver=self.deliver
        )
        self.inbound = Inbound(
            self.agents, self.hub, self.summarize_replaced, keep=self.scheduler.keep
        )
        if self.channel is not None:
            self.channel.set_on_replaced(self.summarize_replaced)

    def summarize_replaced(self, deps: AgentDeps, conv_id: str) -> None:
        """A channel opened a new conversation; recap the one it replaced in the
        background, held by the scheduler so the task is not collected mid-flight."""
        schedule_summary(self.scheduler.keep, deps, conv_id)

    async def deliver(self, agent_id: str, conv_id: str) -> bool:
        """Pushes a conversation's last reply to the chat: any agent's scheduled brief goes
        out through the master's bot, under that agent's name. False when there is no
        channel or it found nothing to send."""
        if self.channel is None:
            return False
        return await self.channel.deliver(conv_id)

    def start_channel(self) -> None:
        self.channel_live = True
        if self.channel is not None:
            self.channel.start()

    async def stop_channel(self) -> None:
        self.channel_live = False
        if self.channel is not None:
            await self.channel.stop()

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

    def replace_agent(self, profile: AgentProfile) -> None:
        """Swap in an edited profile without a restart.

        The deps are rebuilt rather than patched: routes, skills and the tool set are all
        derived from the profile at assembly, so editing the profile in place would leave
        an agent whose description no longer matches what it can do. The peer map is
        shared by identity, so updating the entry is what makes the new name and the new
        delegate list visible to everyone else.
        """
        if self.client is None:
            raise RuntimeError(texts.RUNTIME_CANNOT_GROW)
        deps = build_agent_deps(
            profile, self.providers, self.client, self.store, self.fallback_routes
        )
        peers = self.default.peers if isinstance(self.default.peers, dict) else {}
        deps.peers = peers
        self.agents[profile.id] = deps
        peers[profile.id] = profile
        self.wire_delegation()

    def remove_agent(self, agent_id: str) -> None:
        """Drop an agent from the running crew. Conversations that named it stay put and
        fall back to the default agent, which is why this does not touch the store."""
        # The peer map is reached through the default agent, so it is taken before the
        # pop rather than after: dropping the default first would leave nothing to read
        # it from.
        peers = self.default.peers if isinstance(self.default.peers, dict) else {}
        self.agents.pop(agent_id, None)
        peers.pop(agent_id, None)
        self.wire_delegation()

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
