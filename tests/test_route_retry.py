"""A passing upstream failure is asked again on the same route, once, while nothing has
been shown; a refused request, or one already showing text, is not."""

from __future__ import annotations

import json

import httpx
import pytest

from my_agent_crew.agent.events import DoneEvent, ErrorEvent, RouteFallbackEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.config import Route
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.metered_chain import MeteredChain
from my_agent_crew.llm.openrouter import OpenRouterProvider
from my_agent_crew.llm.provider import AllRoutesFailed, ProviderChain, ProviderError
from my_agent_crew.llm.types import (
    Completion,
    Message,
    ReasoningDelta,
    RouteFailed,
    RouteRetry,
    StreamStarted,
    TextDelta,
    ToolCall,
    ToolCallDelta,
)
from my_agent_crew.store import Store
from tests.conftest import collect

USER = [Message(role="user", content="hi")]
# What OpenRouter sent on a 200 stream the morning the host behind it fell over.
UPSTREAM_DOWN = {
    "code": 502,
    "message": "Upstream error from OpenInference: Internal server error",
    "metadata": {"error_type": "provider_unavailable"},
}


def sse(*chunks: dict) -> str:
    return "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"


def openrouter(*replies: tuple[int, str]) -> tuple[OpenRouterProvider, list]:
    """A provider answering each request with the next (status, body) in turn."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status, body = replies[len(seen)]
        seen.append(request)
        return httpx.Response(status, text=body, headers={"content-type": "text/event-stream"})

    return OpenRouterProvider("k", httpx.AsyncClient(transport=httpx.MockTransport(handler))), seen


def one_route(provider) -> ProviderChain:
    return ProviderChain({"openrouter": provider}, [Route("openrouter", "m")])


THINKING = {"choices": [{"delta": {"reasoning": "đang nghĩ"}, "finish_reason": None}]}
ANSWER = sse({"choices": [{"delta": {"content": "xong"}, "finish_reason": "stop"}]})


async def test_an_upstream_outage_mid_stream_is_asked_again_and_answers(caplog):
    provider, seen = openrouter((200, sse(THINKING, {"error": UPSTREAM_DOWN})), (200, ANSWER))
    with caplog.at_level("WARNING", logger="my_agent_crew.llm.provider"):
        items = await collect(one_route(provider).stream(USER, []))

    assert len(seen) == 2
    assert [type(i) for i in items[:3]] == [StreamStarted, ReasoningDelta, RouteRetry]
    assert "provider_unavailable" in items[2].error
    assert isinstance(items[-1], Completion) and items[-1].message.content == "xong"
    assert any("retrying" in r.message and "openrouter:m" in r.message for r in caplog.records)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (503, "busy"),
        (429, "slow down"),
        (200, sse({"error": {"code": 500, "message": "boom"}})),
        (200, sse({"error": {"code": 429, "message": "rate limited"}})),
    ],
)
async def test_overload_and_outage_answers_are_retried(status, body):
    provider, seen = openrouter((status, body), (200, ANSWER))
    items = await collect(one_route(provider).stream(USER, []))
    assert len(seen) == 2 and items[-1].message.content == "xong"


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (402, '{"error": {"message": "no credit"}}'),
        (400, "bad request"),
        (200, sse({"error": {"code": 400, "message": "context too long"}})),
        (200, sse({"error": {"message": "no code at all"}})),
        (200, "data: {not json\n\n"),
    ],
)
async def test_a_refused_or_malformed_answer_is_not_asked_again(status, body):
    provider, seen = openrouter((status, body), (200, ANSWER))
    with pytest.raises(AllRoutesFailed):
        await collect(one_route(provider).stream(USER, []))
    assert len(seen) == 1


async def test_a_transport_failure_is_retried():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, text=ANSWER)

    provider = OpenRouterProvider("k", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    items = await collect(one_route(provider).stream(USER, []))
    assert len(calls) == 2 and items[-1].message.content == "xong"


async def test_nothing_is_asked_again_once_text_has_been_shown():
    cut = sse({"choices": [{"delta": {"content": "nửa câu"}}]}, {"error": UPSTREAM_DOWN})
    provider, seen = openrouter((200, cut), (200, ANSWER))
    with pytest.raises(ProviderError, match="provider_unavailable"):
        await collect(one_route(provider).stream(USER, []))
    assert len(seen) == 1


async def test_a_route_is_still_asked_again_after_part_of_a_tool_call_arrived():
    """Half a call is not text a person has read as the answer: the attempt can still be
    dropped and asked again, and the pieces of both attempts are passed on in order."""
    half = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {"index": 0, "id": "c1", "function": {"name": "t", "arguments": '{"a"'}}
                    ]
                }
            }
        ]
    }
    rest = {
        "choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": ": 1}"}}]}}]
    }
    provider, seen = openrouter((200, sse(half, {"error": UPSTREAM_DOWN})), (200, sse(half, rest)))
    items = await collect(one_route(provider).stream(USER, []))

    assert len(seen) == 2
    assert items[:-1] == [
        StreamStarted(),
        ToolCallDelta(index=0, name="t", chunk='{"a"'),
        RouteRetry(provider="openrouter", model="m", error=str(UPSTREAM_DOWN)),
        StreamStarted(),
        ToolCallDelta(index=0, name="t", chunk='{"a"'),
        ToolCallDelta(index=0, name="t", chunk=": 1}"),
    ]
    assert items[-1].message.tool_calls == (ToolCall("c1", "t", {"a": 1}),)


async def test_a_tool_call_piece_does_not_use_up_the_retry_that_text_would():
    """The same failure after a word of the answer is not retried; this pins that the two
    kinds of piece are told apart, so a preview never costs a route its second try."""
    piece = ToolCallDelta(index=0, name="t", chunk="{}")

    class CutOffOnce:
        name = "flaky"

        def __init__(self, before_failing):
            self.calls = 0
            self._before_failing = before_failing

        async def stream(self, messages, tools, model):
            self.calls += 1
            if self.calls == 1:
                yield self._before_failing
                raise ProviderError("cut off", transient=True)
            yield TextDelta("xong")

    after_a_piece = CutOffOnce(piece)
    chain = ProviderChain({"flaky": after_a_piece}, [Route("flaky", "m")])
    items = await collect(chain.stream(USER, []))
    assert after_a_piece.calls == 2
    assert items == [piece, RouteRetry("flaky", "m", "cut off"), TextDelta("xong")]

    after_text = CutOffOnce(TextDelta("nửa câu"))
    with pytest.raises(ProviderError, match="cut off"):
        await collect(ProviderChain({"flaky": after_text}, [Route("flaky", "m")]).stream(USER, []))
    assert after_text.calls == 1


async def test_a_route_still_failing_after_its_retry_falls_back_to_the_next():
    down = ProviderError("down", transient=True)
    a = ScriptedProvider([down, down], name="a")
    b = ScriptedProvider([completion("from b")], name="b")
    chain = ProviderChain({"a": a, "b": b}, [Route("a", "m1"), Route("b", "m2")])
    items = await collect(chain.stream(USER, []))

    assert len(a.requests) == 2 and len(b.requests) == 1
    assert [type(i) for i in items[:2]] == [RouteRetry, RouteFailed]
    assert items[-1].provider == "b"


async def test_a_lone_route_failing_twice_gives_up_with_the_last_error():
    a = ScriptedProvider([ProviderError("x", transient=True), ProviderError("y", transient=True)])
    chain = ProviderChain({"scripted": a}, [Route("scripted", "m")])
    with pytest.raises(AllRoutesFailed, match="y"):
        await collect(chain.stream(USER, []))
    assert len(a.requests) == 2


async def test_a_retried_attempt_that_was_served_is_written_down_at_an_unknown_cost(
    store: Store,
):
    conv = store.create()
    provider, _ = openrouter((200, sse(THINKING, {"error": UPSTREAM_DOWN})), (200, ANSWER))
    metered = MeteredChain(one_route(provider), store, "default", "title", conv.id)
    await collect(metered.stream(USER, []))

    calls = store.side_calls.for_conversation(conv.id)
    assert len(calls) == 2
    assert calls[0].cost_usd is None and calls[0].prompt_tokens is None
    assert all(c.model == "m" for c in calls)


async def test_an_attempt_refused_before_its_first_chunk_is_not_written_down(store: Store):
    conv = store.create()
    provider, _ = openrouter((503, "busy"), (200, ANSWER))
    metered = MeteredChain(one_route(provider), store, "default", "title", conv.id)
    await collect(metered.stream(USER, []))

    assert len(store.side_calls.for_conversation(conv.id)) == 1


async def test_a_turn_whose_first_attempt_failed_keeps_only_the_answer(deps_factory, store):
    provider, _ = openrouter((200, sse(THINKING, {"error": UPSTREAM_DOWN})), (200, ANSWER))
    deps = deps_factory(providers={"openrouter": provider}, routes=(Route("openrouter", "m"),))
    conv = store.create()
    events = await collect(run_turn(deps, conv.id, "chào"))

    assert isinstance(events[-1], DoneEvent)
    assert [m.message.content for m in store.history(conv.id) if m.message.role == "assistant"] == [
        "xong"
    ]
    assert not any(isinstance(e, RouteFallbackEvent | ErrorEvent) for e in events)
