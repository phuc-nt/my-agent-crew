"""One model call as the events a turn shows of it. A canvas write appears while the model is
still writing it, and no other tool's arguments do. When the chain gives up on an attempt, the
stream says so before the next attempt's pieces arrive, so whoever drew the old attempt drops
it instead of gluing two attempts of one document together."""

from __future__ import annotations

import inspect
import json
import time
from collections.abc import Sequence
from dataclasses import replace

import pytest

from my_agent_crew.agent.events import (
    AssistantMessageEvent,
    Event,
    ModelCallEvent,
    RouteFallbackEvent,
    TextDeltaEvent,
    ToolCallDeltaEvent,
)
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agent.model_stream import complete_step
from my_agent_crew.config import Route
from my_agent_crew.llm.fake import EchoProvider, ScriptedProvider, completion
from my_agent_crew.llm.provider import ProviderChain, ProviderError
from my_agent_crew.llm.types import (
    Message,
    RouteFailed,
    RouteRetry,
    StreamItem,
    ToolCall,
    ToolCallDelta,
    ToolSpec,
)
from tests.conftest import collect

DOCUMENT = "# Kế hoạch\n" + "".join(f"- ngày {day}: chạy 5 km\n" for day in range(1, 31))
ARGUMENTS = {"title": "Kế hoạch", "kind": "markdown", "content": DOCUMENT}
WRITE = ToolCall("c1", "artifact_create", ARGUMENTS)
WRITTEN = json.dumps(ARGUMENTS, ensure_ascii=False)
PIECES = [WRITTEN[at : at + 12] for at in range(0, len(WRITTEN), 12)]
SENT = ModelCallEvent(stage="sent")


class Clock:
    """Moves on by `step` seconds each time it is read: a test sets how often a piece is due."""

    def __init__(self, step: float = 0.0):
        self.now, self._step = 0.0, step

    def __call__(self) -> float:
        now = self.now
        self.now += self._step
        return now


def shown(chunk: str, attempt: int = 0, index: int = 0) -> ToolCallDeltaEvent:
    return ToolCallDeltaEvent(index=index, name=WRITE.name, chunk=chunk, attempt=attempt)


def called_off(attempt: int) -> ToolCallDeltaEvent:
    """What the stream says when an attempt it showed pieces of was given up."""
    return ToolCallDeltaEvent(index=0, name="", chunk="", attempt=attempt)


def pieces(count: int | None = None, name: str = WRITE.name) -> list[ToolCallDelta]:
    return [ToolCallDelta(index=0, name=name, chunk=chunk) for chunk in PIECES[:count]]


def whole(provider: str = "scripted"):
    return replace(completion("", [WRITE]), provider=provider)


async def step_events(
    deps: AgentDeps,
    clock: Clock | None = None,
    text: str = "viết kế hoạch đi",
    tools: Sequence[ToolSpec] | None = None,
) -> list[Event]:
    """The events of one model call answering `text`, with the answer taken off the end and
    checked: whatever was previewed, the whole call still arrives with the stored answer."""
    conv = deps.store.create()
    deps.store.append(conv.id, Message(role="user", content=text))
    history = deps.store.history(conv.id)
    specs = deps.tools.specs() if tools is None else tools
    events = await collect(complete_step(deps, conv, history, specs, 0, clock=clock or Clock()))
    answer = events.pop()
    assert isinstance(answer, AssistantMessageEvent)
    assert answer.message_id == deps.store.history(conv.id)[-1].id
    assert answer.tool_calls
    return events


class CutOffOnce:
    """A provider whose first attempt streams `before_failing` and is then cut off by a
    failure that asking again may cure; its second attempt writes the whole document."""

    name = "flaky"

    def __init__(self, before_failing: Sequence[StreamItem]):
        self._before_failing = before_failing
        self.calls = 0

    async def stream(self, messages, tools, model):
        self.calls += 1
        if self.calls == 1:
            for item in self._before_failing:
                yield item
            raise ProviderError("cut off", transient=True)
        for item in pieces():
            yield item
        yield whole(self.name)


class Replayed:
    """Stands in for the chain and hands the step exactly these items. The chain as it stands
    never moves on after an attempt streamed something; the step does not lean on that."""

    def __init__(self, *items: StreamItem):
        self._items = items

    async def stream(self, messages, tools):
        for item in self._items:
            yield item


def on_one_route(deps: AgentDeps, provider: CutOffOnce) -> AgentDeps:
    deps.chain = ProviderChain({provider.name: provider}, [Route(provider.name, "m")])
    return deps


async def test_a_canvas_write_is_shown_ahead_of_the_answer_that_carries_it(deps_factory):
    deps = deps_factory(script=[completion("Viết đây.", [WRITE])])
    events = await step_events(deps)
    assert events == [SENT, TextDeltaEvent("Viết đây."), shown(PIECES[0])]


async def test_what_is_still_held_when_the_answer_arrives_is_not_sent_after_it(deps_factory):
    """On a clock that stands still only the first piece is due. The rest is never flushed:
    the answer that follows carries the whole call."""
    events = await step_events(deps_factory(script=[whole()]), Clock(step=0.0))
    assert events == [SENT, shown(PIECES[0])]


async def test_the_step_previews_at_the_pace_of_the_clock_it_was_given(deps_factory):
    """A piece a second: the first goes out at once, then every third brings out the three
    gathered since. The tail that no later piece released is left to the answer."""
    events = await step_events(deps_factory(script=[whole()]), Clock(step=1.0))
    gathered = ["".join(PIECES[at : at + 3]) for at in range(1, len(PIECES) - 2, 3)]
    assert len(gathered) >= 3
    assert events == [SENT, *(shown(chunk) for chunk in [PIECES[0], *gathered])]
    assert WRITTEN.startswith(PIECES[0] + "".join(gathered))
    assert PIECES[0] + "".join(gathered) != WRITTEN


async def test_the_arguments_of_any_other_tool_reach_no_one_before_the_answer(deps_factory):
    write = ToolCall("c1", "workspace_write", {"path": "ke-hoach.md", "content": DOCUMENT})
    events = await step_events(deps_factory(script=[completion("", [write])]), Clock(step=1.0))
    assert events == [SENT]


async def test_a_canvas_write_next_to_another_call_is_shown_under_its_own_place(deps_factory):
    listing = ToolCall("c0", "workspace_list", {"path": "."})
    deps = deps_factory(script=[completion("", [listing, replace(WRITE, id="c2")])])
    assert await step_events(deps) == [SENT, shown(PIECES[0], index=1)]


async def test_an_attempt_cut_off_mid_document_is_called_off_before_the_next_one_shows(
    deps_factory,
):
    provider = CutOffOnce(pieces(4))
    events = await step_events(on_one_route(deps_factory(), provider))
    assert provider.calls == 2
    assert events == [SENT, shown(PIECES[0]), called_off(1), shown(PIECES[0], attempt=1)]


async def test_the_next_attempt_starts_from_nothing_whatever_the_last_one_still_held(
    deps_factory,
):
    """A piece every second and a half: the cut-off attempt had shown two events and was
    holding a fourth piece. The new attempt's first piece goes out at once and alone, and
    every event after the call-off carries the new attempt's number."""
    deps = on_one_route(deps_factory(), CutOffOnce(pieces(4)))
    events = await step_events(deps, Clock(step=1.5))
    second = PIECES[1] + PIECES[2]
    assert events[:6] == [
        SENT,
        shown(PIECES[0]),
        shown(second),
        called_off(1),
        shown(PIECES[0], attempt=1),
        shown(second, attempt=1),
    ]
    assert {event.attempt for event in events[4:]} == {1}
    assert called_off(1) not in events[4:]


@pytest.mark.parametrize(
    "before_failing",
    [[], pieces(3, name="workspace_write"), pieces(3, name="")],
    ids=["nothing streamed", "another tool's call", "pieces of a call not yet named"],
)
async def test_an_attempt_that_showed_nothing_is_not_called_off(deps_factory, before_failing):
    """There is nothing to drop, so nothing says so. The next attempt is still a new answer:
    it is numbered, a place that held another tool's call may hold a canvas write now, and
    what was held of a call nobody had named is not glued in front of it."""
    deps = on_one_route(deps_factory(), CutOffOnce(before_failing))
    assert await step_events(deps) == [SENT, shown(PIECES[0], attempt=1)]


async def test_a_route_that_fails_outright_is_still_reported_and_counts_as_an_attempt(
    deps_factory,
):
    refused = ScriptedProvider([ProviderError("HTTP 401")], name="a")
    served = ScriptedProvider([whole()], name="b")
    routes = (Route("a", "m1"), Route("b", "m2"))
    deps = deps_factory(providers={"a": refused, "b": served}, routes=routes)
    events = await step_events(deps)
    assert events == [SENT, RouteFallbackEvent("a", "m1", "HTTP 401"), shown(PIECES[0], attempt=1)]


async def test_a_route_asked_again_and_then_left_counts_as_two_attempts(deps_factory):
    down = ProviderError("down", transient=True)
    failing = ScriptedProvider([down, down], name="a")
    served = ScriptedProvider([whole()], name="b")
    routes = (Route("a", "m1"), Route("b", "m2"))
    deps = deps_factory(providers={"a": failing, "b": served}, routes=routes)
    events = await step_events(deps)
    assert len(failing.requests) == 2
    assert events == [SENT, RouteFallbackEvent("a", "m1", "down"), shown(PIECES[0], attempt=2)]


async def test_pieces_shown_of_a_route_that_then_failed_are_called_off_too(deps_factory):
    deps = deps_factory()
    deps.chain = Replayed(*pieces(2), RouteFailed("a", "m1", "cut off"), *pieces(1), whole("b"))
    assert await step_events(deps) == [
        SENT,
        shown(PIECES[0]),
        RouteFallbackEvent("a", "m1", "cut off"),
        called_off(1),
        shown(PIECES[0], attempt=1),
    ]


async def test_every_attempt_given_up_is_counted_and_only_those_that_showed_are_called_off(
    deps_factory,
):
    """Four attempts: the first showed a piece, the second only another tool's call, the
    third showed a piece and its route failed, the fourth answers. The second is counted
    without a call-off, and what the first showed is not held against it."""
    retry = RouteRetry("a", "m1", "cut off")
    deps = deps_factory()
    deps.chain = Replayed(
        *pieces(1),
        retry,
        *pieces(2, name="workspace_write"),
        retry,
        *pieces(1),
        RouteFailed("a", "m1", "gone"),
        *pieces(1),
        whole("b"),
    )
    assert await step_events(deps) == [
        SENT,
        shown(PIECES[0]),
        called_off(1),
        shown(PIECES[0], attempt=2),
        RouteFallbackEvent("a", "m1", "gone"),
        called_off(3),
        shown(PIECES[0], attempt=3),
    ]


async def test_on_the_slow_model_a_document_of_a_few_kilobytes_is_seen_filling_in(deps_factory):
    """What a self-test without a model key leans on: over such a document the waits of the
    slow model add up to several preview intervals, so the pane is drawn again and again
    rather than once, and to less than a minute, so whoever watches the document to its end
    is not left waiting. The clock here moves only by what the model waited."""
    clock = Clock()

    async def wait(seconds: float) -> None:
        clock.now += seconds

    arguments = {"title": "Kế hoạch", "kind": "markdown", "content": "chạy 5 km. " * 300}
    written = json.dumps(arguments, ensure_ascii=False)
    deps = deps_factory(
        providers={"fake": EchoProvider(sleep=wait)}, routes=(Route("fake", "slow"),)
    )
    tools = (ToolSpec("artifact_create", "writes a canvas", {}),)
    events = await step_events(deps, clock, f"/tool artifact_create {written}", tools)

    previews = [event for event in events if isinstance(event, ToolCallDeltaEvent)]
    assert 3000 < len(written) < 4000
    assert len(previews) >= 3
    assert written.startswith("".join(event.chunk for event in previews))
    assert len(previews[1].chunk) > len(previews[0].chunk)
    assert clock.now < 60


def test_left_to_itself_the_step_reads_the_clock_that_only_goes_forward():
    assert inspect.signature(complete_step).parameters["clock"].default is time.monotonic
