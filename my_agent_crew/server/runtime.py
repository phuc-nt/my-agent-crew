"""Everything the server holds for its lifetime: one store, one activity hub, one
scheduler, and one `AgentDeps` per agent profile. All agents share the store and the
provider clients; each gets its own workspace, memory, skills, shell cwd and routes.
Building a runtime from a home directory is `runtime_build`; agents joining, changing and
leaving a crew that runs is `runtime_crew`."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from typing import Any

import httpx

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents import DEFAULT_AGENT_ID, AgentProfile
from my_agent_crew.channels import TelegramChannel
from my_agent_crew.config import Settings
from my_agent_crew.inbound import Inbound
from my_agent_crew.inbound_queue import QueueDrain
from my_agent_crew.mcp.hub import McpHub
from my_agent_crew.memory.session_summary import schedule_summary
from my_agent_crew.scheduler import Scheduler
from my_agent_crew.server import runtime_crew
from my_agent_crew.server.crew_abilities import crew_abilities
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
    mcp: McpHub = field(default_factory=McpHub)
    # Agents whose MEMORY.md is being rewritten right now; a second request is a conflict.
    consolidating: set[str] = field(default_factory=set)
    # Whether the channel was started by the app's lifespan; a rebuilt one follows suit
    # (`runtime_connections`).
    channel_live: bool = False
    scheduler: Scheduler = field(init=False)
    # The gate every platform's messages pass through; it shares `agents`, so it grows too.
    inbound: Inbound = field(init=False)
    # Answers what waited while a conversation was busy, whichever channel it came from.
    drain: QueueDrain = field(init=False)

    def __post_init__(self) -> None:
        self.scheduler = Scheduler(
            self.agents, self.hub, clock=self.settings.now, deliver=self.deliver, notify=self.notify
        )
        self.inbound = Inbound(
            self.agents, self.hub, self.summarize_replaced, keep=self.scheduler.keep
        )
        self.drain = QueueDrain(self.store, self.hub, self.inbound)
        if self.channel is not None:
            self.channel.set_on_replaced(self.summarize_replaced)
            self.channel.set_drain(self.drain)

    def summarize_replaced(self, deps: AgentDeps, conv_id: str) -> None:
        """A channel opened a new conversation; recap the one it replaced in the
        background, held by the scheduler so the task is not collected mid-flight."""
        schedule_summary(self.scheduler.keep, deps, conv_id)

    async def deliver(self, agent_id: str, conv_id: str) -> bool:
        """Pushes a conversation's last reply to the chat: any agent's scheduled brief goes
        out through the master's bot, under that agent's name. False when there is no
        channel or it found nothing to send."""
        return self.channel is not None and await self.channel.deliver(conv_id)

    async def notify(self, agent_id: str, text: str) -> bool:
        """Says a sentence of the runtime's about an agent's work to the chat, under that
        agent's name. False when there is no channel to say it to."""
        return self.channel is not None and await self.channel.notify(agent_id, text)

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
        return self.inbound.deps_for(agent_id)

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
        return profile.hands_work_out

    def wire_delegation(self) -> None:
        """Agents that delegate get the tool once every agent exists — it holds the
        runtime, so it cannot be built during assembly, when the runtime is still being
        made. Called again after `add_agents`, it rebuilds every tool so the targets each
        one offers include the newcomers."""
        for deps in self.agents.values():
            # Read when a prompt is built, so a roster tells what the crew holds by then.
            deps.crew = lambda: crew_abilities(self)
            if not self.delegates(deps):
                continue
            if deps.tools.get(DELEGATE_TOOL_NAME) is not None:
                deps.tools = deps.tools.without(DELEGATE_TOOL_NAME)
            deps.tools.register(build_delegate_tool(self, deps.agent))
        # Every path that rebuilds an agent ends here, so its MCP tools come back too.
        self.mcp.attach(self.agents)

    def add_agents(self, profiles: Iterable[AgentProfile]) -> list[str]:
        """Brings agents installed while the server runs into the crew, their schedules onto
        the clock, and returns the ids that joined (`runtime_crew.py`)."""
        return runtime_crew.add_agents(self, profiles)

    def replace_agent(self, profile: AgentProfile, write: Callable[[], None] | None = None) -> None:
        """Swaps in an edited profile, schedules and all, without a restart; `write` puts
        the edit in its file once the agent is built (`runtime_crew.py`)."""
        runtime_crew.replace_agent(self, profile, write)

    def remove_agent(self, agent_id: str) -> None:
        """Drops an agent from the running crew, and its jobs from the clock
        (`runtime_crew.py`)."""
        runtime_crew.remove_agent(self, agent_id)

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
        agents, hub = {deps.agent.id: deps}, ActivityHub(deps.store)
        runtime = cls(settings=deps.settings, store=deps.store, agents=agents, hub=hub)
        runtime.wire_delegation()
        return runtime
