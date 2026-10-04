"""The offline model calls tools as a provider does: no two of its calls share an id. A delegate
finds the child it opened again by the id of its call, so ids that repeat between conversations
would hand one conversation another's child. The tool line a person writes ends their message,
so it still calls the tool when the prompt puts a canvas note ahead of it.

It also streams as a provider does: words and the arguments of a call arrive in pieces ahead of
the answer that carries them, and on the `slow` model with a wait between two pieces, so an
answer or a canvas can be watched arriving without a model key."""

from __future__ import annotations

import asyncio
import inspect

import pytest

from my_agent_crew.llm.fake import SLOW_CHUNK_S, EchoProvider
from my_agent_crew.llm.types import Completion, Message, TextDelta, ToolCallDelta, ToolSpec
from tests.canvas_helpers import framed
from tests.conftest import collect

TOOLS = (ToolSpec("shell_run", "runs a command", {}),)
LIST = '/tool shell_run {"command": "ls"}'


async def answer(text: str) -> Message:
    items = await collect(EchoProvider().stream([Message("user", text)], TOOLS, "echo"))
    return next(item for item in items if isinstance(item, Completion)).message


async def call_ids(*users: str) -> list[str]:
    ids: list[str] = []
    for text in users:
        ids.extend(call.id for call in (await answer(text)).tool_calls)
    return ids


async def test_the_same_request_made_twice_gets_a_different_call_id_each_time():
    ids = await call_ids('/tool shell_run {"command": "ls"}', '/tool shell_run {"command": "ls"}')

    assert len(ids) == 2
    assert ids[0] != ids[1]


async def test_an_answer_that_calls_no_tool_has_no_call_id():
    assert await call_ids("hello") == []


@pytest.mark.parametrize(
    "above",
    ["", "Xem thư mục:\n", f"{framed('Kế hoạch đã đổi')}\n\n", '/tool shell_run {"a": 1}\n'],
)
async def test_the_last_line_that_names_a_tool_calls_it_whatever_comes_above(above: str):
    message = await answer(above + LIST)
    [call] = message.tool_calls
    assert (message.content, call.name, call.arguments) == ("", "shell_run", {"command": "ls"})


async def test_a_tool_line_inside_a_canvas_note_calls_nothing():
    """What the person wrote comes last; a line above it is not theirs to run."""
    text = f"{framed(LIST)}\n\ntiếp nhé"
    message = await answer(text)
    assert (message.content, message.tool_calls) == (f"(echo) {text}", ())


async def test_arguments_that_mention_a_tool_line_are_passed_on_whole():
    message = await answer('/tool shell_run {"command": "echo /tool done"}')
    assert [call.arguments for call in message.tool_calls] == [{"command": "echo /tool done"}]


async def streamed(text: str, model: str = "echo") -> list:
    return await collect(EchoProvider().stream([Message("user", text)], TOOLS, model))


async def timeline_of(text: str, model: str) -> list:
    """Everything the provider did in order: the items it streamed, and each wait it asked
    for as `("wait", seconds)`. The wait is recorded and never slept."""
    timeline: list = []

    async def wait(seconds: float) -> None:
        timeline.append(("wait", seconds))

    async for item in EchoProvider(sleep=wait).stream([Message("user", text)], TOOLS, model):
        timeline.append(item)
    return timeline


async def test_a_tool_call_is_streamed_in_pieces_ahead_of_the_answer_that_carries_it():
    """Twelve characters at a time, each piece naming the call. Nothing else comes ahead of
    the answer: a turn that only calls a tool streams no empty word of text."""
    items = await streamed(LIST)

    assert items[:-1] == [
        ToolCallDelta(index=0, name="shell_run", chunk='{"command": '),
        ToolCallDelta(index=0, name="shell_run", chunk='"ls"}'),
    ]
    done = items[-1]
    assert isinstance(done, Completion)
    assert [(call.name, call.arguments) for call in done.message.tool_calls] == [
        ("shell_run", {"command": "ls"})
    ]


async def test_the_pieces_of_a_call_spell_its_arguments_as_they_were_written():
    """Joined, they are the JSON of the arguments with every letter as the person typed it,
    not an escape code a preview would then have to show."""
    items = await streamed('/tool shell_run {"command": "echo chào buổi sáng"}')
    pieces = [item for item in items if isinstance(item, ToolCallDelta)]

    assert "".join(piece.chunk for piece in pieces) == '{"command": "echo chào buổi sáng"}'
    assert [len(piece.chunk) for piece in pieces] == [12, 12, 10]
    assert {(piece.index, piece.name) for piece in pieces} == {(0, "shell_run")}


async def test_a_plain_answer_streams_its_words_and_no_piece_of_a_call():
    items = await streamed("xin chào bạn")

    assert items[:-1] == [TextDelta("(echo) xin c"), TextDelta("hào bạn")]
    assert isinstance(items[-1], Completion) and items[-1].message.content == "(echo) xin chào bạn"


async def test_the_slow_model_waits_between_two_pieces_of_a_call():
    first, wait, second, done = await timeline_of(LIST, "slow")

    assert wait == ("wait", SLOW_CHUNK_S) and SLOW_CHUNK_S > 0
    assert (first.chunk, second.chunk) == ('{"command": ', '"ls"}')
    assert isinstance(done, Completion)


async def test_the_slow_model_waits_between_two_pieces_of_text():
    first, wait, second, done = await timeline_of("xin chào bạn", "slow")

    assert wait == ("wait", SLOW_CHUNK_S)
    assert (first, second) == (TextDelta("(echo) xin c"), TextDelta("hào bạn"))
    assert isinstance(done, Completion)


async def test_the_slow_model_does_not_wait_around_an_answer_of_one_piece():
    """The wait stands between two pieces: none before the first, none before the answer."""
    piece, done = await timeline_of("hello", "slow")

    assert piece == TextDelta("(echo) hello")
    assert isinstance(done, Completion)


@pytest.mark.parametrize("text", ["xin chào bạn", LIST])
async def test_the_echo_model_never_waits(text: str):
    timeline = await timeline_of(text, "echo")

    assert len(timeline) == 3
    assert not any(isinstance(entry, tuple) for entry in timeline)


def test_left_to_itself_the_provider_waits_on_the_event_loop():
    """So a slow answer holds up nothing else the server is doing."""
    assert inspect.signature(EchoProvider).parameters["sleep"].default is asyncio.sleep
