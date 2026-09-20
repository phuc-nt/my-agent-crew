"""Everything the server holds for its lifetime: one store, one activity hub, one
scheduler, and one `AgentDeps` per agent profile. All agents share the store and the
provider clients; each gets its own workspace, memory, skills, shell cwd and routes."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

import httpx

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents import DEFAULT_AGENT_ID, AgentProfile, load_profiles
from my_agent_crew.agents.context import ensure_agent_dirs
from my_agent_crew.channels import TelegramChannel, build_channels
from my_agent_crew.config import Route, Settings, ensure_home
from my_agent_crew.llm.fake import EchoProvider
from my_agent_crew.llm.openrouter import OpenRouterProvider
from my_agent_crew.llm.provider import Provider, ProviderChain
from my_agent_crew.scheduler import Scheduler
from my_agent_crew.skills import BUILTIN_DIR, load_skills
from my_agent_crew.store import Store
from my_agent_crew.tools import ToolRegistry
from my_agent_crew.tools.memory import build_memory_tools
from my_agent_crew.tools.shell import build_shell_tool
from my_agent_crew.tools.web import build_web_tools
from my_agent_crew.tools.workspace import build_workspace_tools

logger = logging.getLogger(__name__)

# Models can think for well over httpx's 5 s default before the first token arrives; the
# shared client must wait as long as the provider itself would.
PROVIDER_TIMEOUT_SECONDS = 120.0


def build_providers(settings: Settings, client: httpx.AsyncClient) -> dict[str, Provider]:
    providers: dict[str, Provider] = {"fake": EchoProvider()}
    if settings.openrouter_api_key:
        providers["openrouter"] = OpenRouterProvider(settings.openrouter_api_key, client)
    return providers


def usable_routes(
    routes: Sequence[Route], providers: dict[str, Provider], fallback: Sequence[Route]
) -> list[Route]:
    """Routes whose provider is actually built. A profile written for OpenRouter must
    still load when the key is absent (echo runs, tests), so such routes are dropped and
    the global routes take over; only when nothing usable remains is it an error."""
    kept = [r for r in routes if r.provider in providers]
    if kept:
        return kept
    kept = [r for r in fallback if r.provider in providers]
    if kept:
        logger.warning("no usable route among %s; using %s", list(routes), kept)
        return kept
    raise ValueError(texts.NO_USABLE_ROUTE.format(routes=list(routes)))


def build_agent_deps(
    profile: AgentProfile,
    providers: dict[str, Provider],
    client: httpx.AsyncClient,
    store: Store,
    fallback_routes: Sequence[Route] = (),
) -> AgentDeps:
    ensure_agent_dirs(profile)
    routes = usable_routes(profile.settings.routes, providers, fallback_routes)
    if routes != list(profile.settings.routes):
        profile = replace(profile, settings=replace(profile.settings, routes=tuple(routes)))
    tools = ToolRegistry(
        [
            *build_workspace_tools(profile.workspace),
            *build_web_tools(profile.settings, client),
            *build_memory_tools(profile.memory_dir, profile.memory_file),
            build_shell_tool(profile.workspace),
        ]
    )
    chain = ProviderChain(providers, profile.settings.routes)
    skills = load_skills(BUILTIN_DIR, *profile.skills_dirs)
    return AgentDeps(
        settings=profile.settings,
        chain=chain,
        tools=tools,
        store=store,
        skills=skills,
        profile=profile,
    )


@dataclass
class Runtime:
    settings: Settings
    store: Store
    agents: dict[str, AgentDeps]
    hub: ActivityHub
    channels: dict[str, TelegramChannel] = field(default_factory=dict)
    scheduler: Scheduler = field(init=False)

    def __post_init__(self) -> None:
        self.scheduler = Scheduler(self.agents, self.hub, deliver=self.deliver)

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
    hub = ActivityHub(store)
    channels = build_channels(agents, hub, client, os.environ if env is None else env)
    return Runtime(settings=settings, store=store, agents=agents, hub=hub, channels=channels)


def build_deps(settings: Settings, client: httpx.AsyncClient | None = None) -> AgentDeps:
    """The default agent's deps alone, for callers that only need one agent."""
    return build_runtime(settings, client).default
