"""A stuck turn moves to its agent's escalation route once, and only when it is stuck: the
loop guard is about to halt it, or a model call failed on every route with nothing shown.
The step limit and the cost cap still end it, and an agent that names no route ends the way
it always did (`agent/escalation.py`)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from my_agent_crew import texts
from my_agent_crew.agent.events import (
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    EscalatedEvent,
    HaltedEvent,
    ModelCallEvent,
    RouteFallbackEvent,
    ToolResultEvent,
)
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.config import Route
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.provider import ProviderChain, ProviderError
from my_agent_crew.llm.types import (
    ReasoningDelta,
    StreamItem,
    StreamStarted,
    TextDelta,
    ToolCall,
    ToolCallDelta,
)
from tests.conftest import collect
from tests.test_loop_guard import counter, repeating

DOWN = ProviderError("upstream 502")
MOVED_FOR_LOOP = EscalatedEvent(reason="loop", provider="strong", model="big")


def with_spare(deps: AgentDeps, script: Sequence) -> ScriptedProvider:
    """Gives the agent an escalation route, answered by the returned provider."""
    spare = ScriptedProvider(script, name="strong")
    providers = {**deps.chain.providers, "strong": spare}
    deps.escalation = ProviderChain(providers, [Route("strong", "big")])
    return spare


def usual(deps: AgentDeps) -> ScriptedProvider:
    return deps.chain.providers["scripted"]


def moves(events: list) -> list[EscalatedEvent]:
    return [e for e in events if isinstance(e, EscalatedEvent)]


def different(times: int) -> list:
    """Model calls that each ask for the tool with other arguments: work, not a loop."""
    return [
        completion(tool_calls=(ToolCall(f"d{i}", "count_up", {"what": f"bài {i}"}),))
        for i in range(times)
    ]


async def test_a_turn_about_to_halt_for_repeating_itself_moves_to_the_escalation_route(
    deps_factory,
):
    tool, runs = counter()
    deps = deps_factory(script=repeating(10), extra_tools=[tool], max_steps=20)
    spare = with_spare(deps, [completion("Máy chủ không phản hồi, bạn kiểm tra mạng giúp nhé.")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đếm bài"))

    assert isinstance(events[-1], DoneEvent) and moves(events) == [MOVED_FOR_LOOP]
    assert len(usual(deps).requests) == 6 and len(spare.requests) == 1
    assert len(runs) == 5  # the sixth call was refused, not run
    # The refusal comes first, so the model that takes over reads a conversation in which
    # every call has its result; and it is not told the turn stopped, because it did not.
    at = events.index(MOVED_FOR_LOOP)
    refused = events[at - 1]
    assert isinstance(refused, ToolResultEvent) and refused.tool_call_id == "c5"
    assert refused.output == texts.LOOP_ESCALATED_TOOL and not refused.ok
    assert "dừng" not in texts.LOOP_ESCALATED_TOOL
    assert events[at + 1] == ModelCallEvent(stage="sent")
    assert spare.requests[0].model == "big"
    assert spare.requests[0].messages[-1].content == texts.LOOP_ESCALATED_TOOL
    answer = deps.store.history(conv.id)[-1]
    assert (answer.provider, answer.model) == ("strong", "big")


async def test_a_turn_that_repeats_itself_on_the_escalation_route_too_is_halted(deps_factory):
    tool, runs = counter()
    deps = deps_factory(script=repeating(6), extra_tools=[tool], max_steps=20)
    spare = with_spare(deps, repeating(10))
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đếm bài"))

    assert events[-1] == HaltedEvent(reason="loop", spent_usd=pytest.approx(0.012))
    assert moves(events) == [MOVED_FOR_LOOP]
    # The model it moved to is given the whole count again, reminder included, and no more.
    assert len(usual(deps).requests) == 6 and len(spare.requests) == 6
    assert len(runs) == 10
    history = [m.message for m in deps.store.history(conv.id)]
    assert len([m for m in history if texts.LOOP_REDIRECT[:10] in m.content]) == 2
    refusals = [e.output for e in events if isinstance(e, ToolResultEvent) and not e.ok]
    assert refusals == [texts.LOOP_ESCALATED_TOOL, texts.LOOP_HALTED_TOOL]


async def test_a_model_call_every_route_failed_is_asked_again_on_the_escalation_route(
    deps_factory,
):
    # A passing failure is first asked again on the same route; only then is the turn stuck.
    passing = ProviderError("upstream 502", transient=True)
    deps = deps_factory(script=[passing, passing])
    spare = with_spare(deps, [completion("xong")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "chào"))

    assert isinstance(events[-1], DoneEvent)
    assert not any(isinstance(e, ErrorEvent) for e in events)
    [moved] = moves(events)
    assert (moved.reason, moved.provider, moved.model) == ("error", "strong", "big")
    assert "scripted:m: upstream 502" in moved.error
    failed = [e for e in events if isinstance(e, RouteFallbackEvent)]
    assert [(e.provider, e.model) for e in failed] == [("scripted", "m")]
    assert events.index(failed[0]) < events.index(moved)
    assert len(usual(deps).requests) == 2 and len(spare.requests) == 1
    # Nothing was stored for the call that failed: the same thing is asked.
    assert spare.requests[0].messages == usual(deps).requests[0].messages
    assert [m.message.role for m in deps.store.history(conv.id)] == ["user", "assistant"]


async def test_the_rest_of_the_turn_stays_there_and_the_next_turn_starts_on_the_usual_routes(
    deps_factory,
):
    tool, runs = counter()
    deps = deps_factory(script=[DOWN, completion("lượt sau")], extra_tools=[tool])
    spare = with_spare(deps, [*different(1), completion("xong")])
    conv = deps.store.create()

    first = await collect(run_turn(deps, conv.id, "đếm bài"))

    assert isinstance(first[-1], DoneEvent) and len(moves(first)) == 1 and len(runs) == 1
    assert len(usual(deps).requests) == 1 and len(spare.requests) == 2
    spoke = [(e.provider, e.model) for e in first if isinstance(e, AssistantMessageEvent)]
    assert spoke == [("strong", "big"), ("strong", "big")]

    second = await collect(run_turn(deps, conv.id, "nữa đi"))

    assert isinstance(second[-1], DoneEvent) and moves(second) == []
    assert len(usual(deps).requests) == 2 and len(spare.requests) == 2
    assert deps.store.history(conv.id)[-1].message.content == "lượt sau"


async def test_a_turn_moves_once_and_an_error_there_ends_it(deps_factory):
    deps = deps_factory(script=[DOWN, completion("không được hỏi")])
    spare = with_spare(deps, [ProviderError("strong is down too"), completion("không được hỏi")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "chào"))

    assert isinstance(events[-1], ErrorEvent) and "strong is down too" in events[-1].message
    assert len(moves(events)) == 1
    assert len(usual(deps).requests) == 1 and len(spare.requests) == 1


async def test_a_turn_that_moved_for_an_error_is_halted_when_it_then_repeats_itself(
    deps_factory,
):
    tool, _ = counter()
    deps = deps_factory(script=[DOWN], extra_tools=[tool], max_steps=20)
    spare = with_spare(deps, repeating(10))
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đếm bài"))

    assert events[-1] == HaltedEvent(reason="loop", spent_usd=pytest.approx(0.006))
    assert [e.reason for e in moves(events)] == ["error"]
    assert len(spare.requests) == 6
    refusals = [e.output for e in events if isinstance(e, ToolResultEvent) and not e.ok]
    assert refusals == [texts.LOOP_HALTED_TOOL]


async def test_an_agent_that_names_no_route_ends_on_the_error(deps_factory):
    deps = deps_factory(script=[DOWN, completion("không được hỏi")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "chào"))

    assert deps.escalation is None
    assert isinstance(events[-1], ErrorEvent) and moves(events) == []
    assert len(usual(deps).requests) == 1


class Flaky:
    """Plays one list of stream items per request; a `ProviderError` in a list is raised
    where it stands, the way an upstream that breaks off mid-answer does."""

    name = "scripted"

    def __init__(self, *plays: Sequence[StreamItem | ProviderError]):
        self._plays = list(plays)
        self.requests = 0

    async def stream(self, messages, tools, model, reasoning=""):
        self.requests += 1
        for item in self._plays.pop(0):
            if isinstance(item, ProviderError):
                raise item
            yield item


BROKE = ProviderError("đứt giữa chừng")
DRAFT = ToolCallDelta(0, "artifact_create", '{"title": "Kế hoạch')


@pytest.mark.parametrize(
    ("plays", "moved"),
    [
        # Words of the answer were shown: asking another model would show the seam.
        ([[StreamStarted(), TextDelta("Đang trả lời"), BROKE]], False),
        # So were pieces of a canvas being written, and nothing called them off.
        ([[StreamStarted(), DRAFT, BROKE]], False),
        # Thinking and timing marks are never shown.
        ([[StreamStarted(), ReasoningDelta("đang nghĩ"), BROKE]], True),
        # Pieces the chain's own retry called off are gone from the reader's screen.
        ([[DRAFT, ProviderError("502", transient=True)], [ProviderError("502")]], True),
    ],
    ids=["words", "canvas pieces", "thinking only", "pieces called off"],
)
async def test_a_call_that_had_begun_to_show_is_not_asked_again_somewhere_else(
    deps_factory, plays, moved
):
    flaky = Flaky(*plays)
    deps = deps_factory(providers={"scripted": flaky})
    spare = with_spare(deps, [completion("xong")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "viết kế hoạch"))

    assert flaky.requests == len(plays)
    assert len(spare.requests) == (1 if moved else 0)
    assert isinstance(events[-1], DoneEvent if moved else ErrorEvent)
    assert len(moves(events)) == (1 if moved else 0)


async def test_a_turn_with_no_model_call_left_is_halted_for_repeating_itself_not_moved(
    deps_factory,
):
    """Moved there it could only run out of steps, and the halt would name the wrong cause."""
    tool, _ = counter()
    deps = deps_factory(script=repeating(6), extra_tools=[tool], max_steps=6)
    spare = with_spare(deps, [completion("không được hỏi")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đếm bài"))

    assert events[-1] == HaltedEvent(reason="loop", spent_usd=pytest.approx(0.006))
    assert moves(events) == [] and spare.requests == []
    refused = [e for e in events if isinstance(e, ToolResultEvent)][-1]
    assert refused.output == texts.LOOP_HALTED_TOOL


async def test_a_turn_with_no_model_call_left_ends_on_the_error_not_moved(deps_factory):
    deps = deps_factory(script=[DOWN], max_steps=1)
    spare = with_spare(deps, [completion("không được hỏi")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "chào"))

    assert isinstance(events[-1], ErrorEvent) and moves(events) == []
    assert spare.requests == []


async def test_a_turn_with_one_model_call_left_makes_it_on_the_escalation_route(deps_factory):
    deps = deps_factory(script=[DOWN], max_steps=2)
    spare = with_spare(deps, [completion("xong")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "chào"))

    assert isinstance(events[-1], DoneEvent) and len(moves(events)) == 1
    assert len(spare.requests) == 1


async def test_what_an_earlier_call_of_the_turn_showed_is_not_held_against_the_one_that_failed(
    deps_factory,
):
    """Only the call that failed is asked again. Words an earlier call wrote are stored
    with their message and stay where they are."""
    tool, runs = counter()
    spoke = completion("Để tôi đếm đã.", tool_calls=(ToolCall("d0", "count_up", {"what": "a"}),))
    deps = deps_factory(script=[spoke, DOWN], extra_tools=[tool])
    spare = with_spare(deps, [completion("xong")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đếm bài"))

    assert isinstance(events[-1], DoneEvent) and len(moves(events)) == 1 and len(runs) == 1
    said = [m.message.content for m in deps.store.history(conv.id) if m.message.role == "assistant"]
    assert said == ["Để tôi đếm đã.", "xong"]
    assert len(spare.requests) == 1


async def test_a_turn_that_repeats_itself_while_talking_is_moved_all_the_same(deps_factory):
    """A call that came back whole is not one to ask again: what it said is stored, and the
    model that takes over reads it. Only a call cut short can leave a seam."""
    tool, _ = counter()
    talking = [
        completion("Đang đếm…", tool_calls=(ToolCall(f"c{i}", "count_up", {"what": "bài"}),))
        for i in range(6)
    ]
    deps = deps_factory(script=talking, extra_tools=[tool], max_steps=20)
    spare = with_spare(deps, [completion("xong")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đếm bài"))

    assert isinstance(events[-1], DoneEvent) and moves(events) == [MOVED_FOR_LOOP]
    assert len(spare.requests) == 1


async def test_a_turn_that_moved_still_stops_at_the_step_limit(deps_factory):
    """The call that failed counts: a turn makes no more model calls than its limit."""
    tool, _ = counter()
    deps = deps_factory(script=[DOWN], extra_tools=[tool], max_steps=3)
    spare = with_spare(deps, different(5))
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đếm bài"))

    assert isinstance(events[-1], HaltedEvent) and events[-1].reason == "max_steps"
    assert len(moves(events)) == 1
    assert len(usual(deps).requests) + len(spare.requests) == 3


async def test_a_turn_that_moved_still_stops_at_the_cost_cap(deps_factory):
    tool, _ = counter()
    deps = deps_factory(script=[DOWN], extra_tools=[tool], max_steps=20, cost_cap_usd=0.5)
    dear = completion(tool_calls=(ToolCall("d0", "count_up", {"what": "bài"}),), cost_usd=0.6)
    spare = with_spare(deps, [dear, completion("không được hỏi")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đếm bài"))

    assert events[-1] == HaltedEvent(reason="budget", spent_usd=pytest.approx(0.6))
    assert len(moves(events)) == 1 and len(spare.requests) == 1


async def test_a_turn_over_its_cost_cap_is_not_moved(deps_factory):
    """The cap is read before each model call, the one after a move included."""
    tool, _ = counter()
    dear = [replace_cost(c, 0.2) for c in repeating(6)]
    deps = deps_factory(script=dear, extra_tools=[tool], max_steps=20, cost_cap_usd=0.5)
    spare = with_spare(deps, [completion("không được hỏi")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đếm bài"))

    assert isinstance(events[-1], HaltedEvent) and events[-1].reason == "budget"
    assert moves(events) == [] and spare.requests == []


def replace_cost(item, cost_usd: float):
    return completion(tool_calls=item.message.tool_calls, cost_usd=cost_usd)
