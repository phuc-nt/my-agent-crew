"""The offline model calls tools as a provider does: no two of its calls share an id. A delegate
finds the child it opened again by the id of its call, so ids that repeat between conversations
would hand one conversation another's child."""

from __future__ import annotations

from my_agent_crew.llm.fake import EchoProvider
from my_agent_crew.llm.types import Completion, Message, ToolSpec
from tests.conftest import collect

TOOLS = (ToolSpec("shell_run", "runs a command", {}),)


async def call_ids(*users: str) -> list[str]:
    ids: list[str] = []
    for text in users:
        items = await collect(EchoProvider().stream([Message("user", text)], TOOLS, "echo"))
        done = next(item for item in items if isinstance(item, Completion))
        ids.extend(call.id for call in done.message.tool_calls)
    return ids


async def test_the_same_request_made_twice_gets_a_different_call_id_each_time():
    ids = await call_ids('/tool shell_run {"command": "ls"}', '/tool shell_run {"command": "ls"}')

    assert len(ids) == 2
    assert ids[0] != ids[1]


async def test_an_answer_that_calls_no_tool_has_no_call_id():
    assert await call_ids("hello") == []
