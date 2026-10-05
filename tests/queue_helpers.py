"""A turn held open on purpose: a provider that waits at a gate before answering or with
its answer half written, a tool that runs until released, a rig wiring one agent to a hub,
the inbound door and the queue drain the way the runtime does, and the app served on the
test's own loop. Waits are on events, never on long sleeps."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

import httpx

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.events import Event
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents.kit_commands import Command
from my_agent_crew.inbound import Inbound
from my_agent_crew.inbound_queue import QueueDrain
from my_agent_crew.llm.fake import ScriptedProvider
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import Completion
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store import Conversation, Store
from my_agent_crew.store.runs import RunRecord
from my_agent_crew.tools import Tool, ToolResult


class GatedProvider(ScriptedProvider):
    """A scripted provider whose calls listed in `held` wait for `release(i)` before
    answering, and whose calls listed in `paused` stream their whole answer and then wait
    for `finish(i)` before ending it. `started(i)` is set as soon as call `i` begins,
    `written(i)` once a paused call has streamed all it has."""

    def __init__(
        self,
        script: Sequence[Completion | ProviderError],
        held: Sequence[int] = (),
        paused: Sequence[int] = (),
    ):
        super().__init__(script)
        self.calls = 0
        self._gates = {index: asyncio.Event() for index in held}
        self._pauses = {index: asyncio.Event() for index in paused}
        self._started: dict[int, asyncio.Event] = {}
        self._written: dict[int, asyncio.Event] = {}

    def started(self, index: int) -> asyncio.Event:
        return self._started.setdefault(index, asyncio.Event())

    def written(self, index: int) -> asyncio.Event:
        return self._written.setdefault(index, asyncio.Event())

    def release(self, index: int) -> None:
        self._gates[index].set()

    def finish(self, index: int) -> None:
        self._pauses[index].set()

    async def stream(self, messages, tools, model, reasoning=""):
        index = self.calls
        self.calls += 1
        self.started(index).set()
        gate = self._gates.get(index)
        if gate is not None:
            await gate.wait()
        pause = self._pauses.get(index)
        async for item in super().stream(messages, tools, model, reasoning):
            if pause is not None and isinstance(item, Completion):
                self.written(index).set()
                await pause.wait()
            yield item


class SlowTool:
    """A tool that runs until released, counting how often it ran."""

    def __init__(self, name: str = "slow", requires_approval: bool = False):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.runs = 0
        schema = {"type": "object", "properties": {}}
        self.tool = Tool(name, "Chạy chậm.", schema, self._run, requires_approval)

    async def _run(self, args: dict[str, Any]) -> ToolResult:
        self.runs += 1
        self.started.set()
        await self.release.wait()
        return ToolResult(ok=True, output="xong")


class OrderedHub(ActivityHub):
    """Remembers the order runs started in: stored runs carry one-second stamps, so two
    runs of one test share a stamp and `recent` cannot tell which came first."""

    def __init__(self, store: Store):
        super().__init__(store)
        self.started: list[str] = []

    def start(self, agent_id, source, title, conversation_id):
        run = super().start(agent_id, source, title, conversation_id)
        if run.id not in self.started:
            self.started.append(run.id)
        return run


async def until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


async def settle_loop(rounds: int = 5) -> None:
    """Lets tasks already scheduled run, for asserting that nothing more happens."""
    for _ in range(rounds):
        await asyncio.sleep(0.01)


@dataclass
class Rig:
    """One agent wired the way the runtime wires it. Its conversation already has a title,
    so no naming call competes with the turns for the scripted answers."""

    deps: AgentDeps
    hub: OrderedHub
    inbound: Inbound
    drain: QueueDrain
    provider: GatedProvider
    slow: SlowTool
    guarded: SlowTool  # the same, but a person must allow each call
    conv: Conversation

    @property
    def store(self) -> Store:
        return self.deps.store

    def history(self, conv_id: str | None = None) -> list[tuple[str, str]]:
        messages = self.store.history(conv_id or self.conv.id)
        return [(m.message.role, m.message.content) for m in messages]

    def runs(self, conv_id: str | None = None) -> list[RunRecord]:
        """This conversation's runs in the order they started, live ones included."""
        found = self.hub.recent(conversation_ids=[conv_id or self.conv.id])
        by_id = {run.id: run for run in found}
        return [by_id[run_id] for run_id in self.hub.started if run_id in by_id]

    def statuses(self, conv_id: str | None = None) -> list[str]:
        return [run.status for run in self.runs(conv_id)]


def make_rig(
    deps_factory,
    script: Sequence[Completion | ProviderError],
    held: Sequence[int] = (),
    commands: Sequence[Command] = (),
    channel: str = "",
    extra_tools: Sequence[Tool] = (),
) -> Rig:
    provider = GatedProvider(script, held)
    slow, guarded = SlowTool(), SlowTool("guarded", requires_approval=True)
    guarded.release.set()
    deps = deps_factory(
        providers={"scripted": provider}, extra_tools=[slow.tool, guarded.tool, *extra_tools]
    )
    if commands:
        deps = replace(deps, profile=replace(deps.agent, commands=tuple(commands)))
    hub = OrderedHub(deps.store)
    inbound = Inbound({deps.agent.id: deps}, hub)
    drain = QueueDrain(deps.store, hub, inbound)
    conv = deps.store.create("Việc thử", agent_id=deps.agent.id, channel=channel)
    return Rig(deps, hub, inbound, drain, provider, slow, guarded, conv)


async def while_the_tool_runs(rig: Rig, *messages: str) -> tuple[list, list]:
    """Starts a turn whose tool call waits, sends `messages` meanwhile, then lets the tool
    finish. Returns what each message got back and the running turn's events."""
    first = asyncio.create_task(_collect(rig.inbound.stream(rig.conv.id, "làm việc chậm")))
    await asyncio.wait_for(rig.slow.started.wait(), 2)
    answers = [await _collect(rig.inbound.stream(rig.conv.id, text)) for text in messages]
    rig.slow.release.set()
    return answers, await asyncio.wait_for(first, 2)


async def _collect(events: AsyncIterator[Event]) -> list[Event]:
    return [event async for event in events]


@dataclass
class Served:
    """The app on the test's own event loop (`served` in `conftest.py`), with one
    conversation that already has a title."""

    client: httpx.AsyncClient
    runtime: Runtime
    provider: GatedProvider
    slow: SlowTool
    guarded: SlowTool  # a person must allow each call; it runs at once when allowed
    conv: Conversation

    @property
    def detail(self) -> str:
        return f"/api/conversations/{self.conv.id}"

    @property
    def messages(self) -> str:
        return f"{self.detail}/messages"

    @property
    def stop(self) -> str:
        return f"{self.detail}/stop"

    @property
    def turn(self) -> str:
        return f"{self.detail}/turn"

    def statuses(self) -> list[str]:
        runs = self.runtime.hub.recent(conversation_ids=[self.conv.id])
        return sorted(run.status for run in runs)
