"""The offline model calls tools as a provider does: no two of its calls share an id. A delegate
finds the child it opened again by the id of its call, so ids that repeat between conversations
would hand one conversation another's child. The tool line a person writes ends their message,
so it still calls the tool when the prompt puts a canvas note ahead of it."""

from __future__ import annotations

import pytest

from my_agent_crew.llm.fake import EchoProvider
from my_agent_crew.llm.types import Completion, Message, ToolSpec
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
