"""Everything the server holds for its lifetime: one store, one activity hub, one
scheduler, and one `AgentDeps` per agent profile. All agents share the store and the
provider clients; each gets its own workspace, memory, skills, shell cwd and routes."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents import DEFAULT_AGENT_ID, AgentProfile, load_profiles
from my_agent_crew.channels import TelegramChannel, build_channels
from my_agent_crew.config import Settings, ensure_home
from my_agent_crew.memory.session_summary import schedule_summary
from my_agent_crew.scheduler import Scheduler
from my_agent_crew.server.agent_assembly import (
    build_agent_deps,
    build_providers,
    usable_routes,
    warn_unknown_schedule_skills,
)
from my_agent_crew.store import Store

__all__ = [
    "PROVIDER_TIMEOUT_SECONDS",
    "Runtime",
    "build_agent_deps",
    "build_deps",
    "build_providers",
    "build_runtime",
    "usable_routes",
    "warn_unknown_schedule_skills",
]

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

    async def deliver(self, agent_id: str, conv_id: str) -> None:
        """Pushes a conversation's last reply through the agent's channel, if it has one."""
        channel = self.channels.get(agent_id)
        if channel is not None:
            await channel.deliver(conv_id)

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
        return cls(settings=deps.settings, store=deps.store, agents={deps.agent.id: deps}, hub=hub)


def build_runtime(
    settings: Settings,
    client: httpx.AsyncClient | None = None,
    env: Mapping[str, str] | None = None,
) -> Runtime:
    """`env` is where channel tokens are read from (the process environment by default);
    settings never hold them, so a profile can be committed while its token stays out."""
    settings = ensure_home(settings)
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(PROVIDER_TIMEOUT_SECONDS))
    store = Store(settings.db_path)
    providers = build_providers(settings, client)
    agents = {
        profile.id: build_agent_deps(profile, providers, client, store, settings.routes)
        for profile in load_profiles(settings)
    }
    peers = {agent_id: deps.agent for agent_id, deps in agents.items()}
    for deps in agents.values():
        deps.peers = peers  # every agent can name the others sharing its channel
    hub = ActivityHub(store)
    channels = build_channels(agents, hub, client, os.environ if env is None else env)
    return Runtime(settings=settings, store=store, agents=agents, hub=hub, channels=channels)


def build_deps(settings: Settings, client: httpx.AsyncClient | None = None) -> AgentDeps:
    """The default agent's deps alone, for callers that only need one agent."""
    return build_runtime(settings, client).default
