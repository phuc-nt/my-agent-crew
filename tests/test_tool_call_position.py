"""A piece of a tool call is numbered by its call's position in the answer, not by the number
the provider gave the call. The finished calls are ordered by rank of that number, and a reader
finds the call a piece belongs to by position: a stream that numbers its calls from 1 (the text
of the answer being its block 0), or leaves gaps, must still send each piece to its own call."""

from __future__ import annotations

import json

import httpx
import pytest

from my_agent_crew.agent.events import AssistantMessageEvent, DoneEvent, ToolCallDeltaEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agents.profile import DEFAULT_AGENT_ID
from my_agent_crew.config import DEFAULT_TOOL_OUTPUT_CHARS, Route
from my_agent_crew.llm.openrouter import OpenRouterProvider
from my_agent_crew.llm.tool_call_buffer import ToolCallBuffer
from my_agent_crew.llm.types import ToolCallDelta
from my_agent_crew.store.db import Store
from my_agent_crew.tools.artifact import build_artifact_tools
from tests.canvas_helpers import ZONE
from tests.conftest import collect


def _opening(index: object, name: str, args: str) -> dict:
    return {"index": index, "id": f"c{index}", "function": {"name": name, "arguments": args}}


def _more(index: object, args: str) -> dict:
    return {"index": index, "function": {"arguments": args}}


def _places(pieces: list[ToolCallDelta]) -> list[tuple[int, str]]:
    return [(piece.index, piece.name) for piece in pieces]


@pytest.mark.parametrize("numbers", [(1, 2), (0, 5), (3, 40)], ids=["from 1", "a gap", "both"])
def test_a_piece_carries_the_position_of_its_call_whatever_number_the_stream_gave_it(numbers):
    first, second = numbers
    buffer = ToolCallBuffer()

    opened = buffer.feed([_opening(first, "workspace_list", '{"path"')])
    opened += buffer.feed([_more(first, ': "."}'), _opening(second, "artifact_create", '{"ti')])
    closed = buffer.feed([_more(second, 'tle": "A"}')])

    assert _places(opened) == [(0, "workspace_list"), (0, "workspace_list"), (1, "artifact_create")]
    assert _places(closed) == [(1, "artifact_create")]
    calls = buffer.calls()
    assert [call.name for call in calls] == ["workspace_list", "artifact_create"]
    # Each piece went to the place its finished call has.
    assert all(calls[piece.index].name == piece.name for piece in opened + closed)


def test_a_call_keeps_its_position_while_later_calls_open_after_it():
    buffer = ToolCallBuffer()

    buffer.feed([_opening(1, "artifact_create", '{"a"')])
    buffer.feed([_opening(2, "artifact_rewrite", '{"b"')])
    buffer.feed([_opening(7, "artifact_create", '{"c"')])
    late = buffer.feed([_more(1, ": 1}"), _more(7, ": 3}"), _more(2, ": 2}")])

    assert _places(late) == [
        (0, "artifact_create"),
        (2, "artifact_create"),
        (1, "artifact_rewrite"),
    ]
    assert [call.arguments for call in buffer.calls()] == [{"a": 1}, {"b": 2}, {"c": 3}]


def test_arguments_ahead_of_the_name_are_placed_like_any_other_piece():
    buffer = ToolCallBuffer()
    buffer.feed([_opening(1, "workspace_list", "{}")])

    early = buffer.feed([_more(2, '{"ti')])
    named = buffer.feed([_opening(2, "artifact_create", 'tle": "A"}')])

    assert early == [ToolCallDelta(index=1, name="", chunk='{"ti')]
    assert named == [ToolCallDelta(index=1, name="artifact_create", chunk='tle": "A"}')]


def test_a_call_that_has_brought_no_arguments_yet_still_holds_its_position():
    """A call opened with only its id and name is a call of the answer all the same: the one
    after it is the second, whether or not the first ever brings an argument."""
    buffer = ToolCallBuffer()

    assert buffer.feed([{"index": 1, "id": "c1", "function": {"name": "workspace_list"}}]) == []
    pieces = buffer.feed([_opening(2, "artifact_create", "{}")])

    assert pieces == [ToolCallDelta(index=1, name="artifact_create", chunk="{}")]
    assert [call.name for call in buffer.calls()] == ["workspace_list", "artifact_create"]


def test_a_stream_that_gives_its_one_call_no_number_at_all_still_places_it_first():
    """`"index": null` was always taken as one call; counting places must not choke on it."""
    buffer = ToolCallBuffer()

    pieces = buffer.feed([_opening(None, "artifact_create", '{"a"'), _more(None, ": 1}")])

    assert _places(pieces) == [(0, "artifact_create"), (0, "artifact_create")]
    assert [call.arguments for call in buffer.calls()] == [{"a": 1}]


# --- through a turn ------------------------------------------------------------------------

CANVAS = {"title": "Kế hoạch", "kind": "markdown", "content": "# Kế hoạch\nchạy 5 km\n"}
WRITTEN = json.dumps(CANVAS, ensure_ascii=False)


def _sse(*deltas: dict) -> str:
    chunks = [{"choices": [{"delta": delta, "finish_reason": None}]} for delta in deltas]
    return "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"


def _numbered_from_one() -> OpenRouterProvider:
    """A gateway that passes on the number of each content block: the words of the answer are
    block 0, so the two calls are 1 and 2. Its second answer ends the turn."""
    answers = [
        _sse(
            {"content": "Để tôi xem rồi viết."},
            {"tool_calls": [_opening(1, "workspace_list", '{"path": "."}')]},
            {"tool_calls": [_opening(2, "artifact_create", WRITTEN[:20])]},
            {"tool_calls": [_more(2, WRITTEN[20:])]},
        ),
        _sse({"content": "Xong."}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=answers.pop(0))

    return OpenRouterProvider("test-key", httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_the_piece_a_turn_shows_names_the_place_of_its_call_in_the_answer(
    deps_factory, store: Store
):
    tools = build_artifact_tools(store, DEFAULT_AGENT_ID, False, DEFAULT_TOOL_OUTPUT_CHARS, ZONE)
    deps = deps_factory(
        routes=(Route("openrouter", "m"),),
        providers={"openrouter": _numbered_from_one()},
        extra_tools=tools,
    )
    conv = store.create()

    events = await collect(run_turn(deps, conv.id, "viết kế hoạch đi"))

    [piece] = [event for event in events if isinstance(event, ToolCallDeltaEvent)]
    answer = next(event for event in events if isinstance(event, AssistantMessageEvent))
    assert [call["name"] for call in answer.tool_calls] == ["workspace_list", "artifact_create"]
    assert piece == ToolCallDeltaEvent(1, "artifact_create", WRITTEN[:20], 0)
    assert answer.tool_calls[piece.index]["name"] == piece.name
    assert answer.tool_calls[piece.index]["arguments"] == CANVAS
    assert isinstance(events[-1], DoneEvent)
    assert [canvas.title for canvas in store.artifacts.list()] == ["Kế hoạch"]
