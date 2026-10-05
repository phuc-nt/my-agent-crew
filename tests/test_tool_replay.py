"""Which calls a restart may make again (`agent/replay.py`).

A call with no result when the server stopped may have run. Made again unseen, one that
writes, sends or pays would do it twice, so only a tool that says it reads is repeated, and
a tool that says nothing is taken to change something. A call that never got as far as
running is left to the turn, which asks, refuses or fails it as it always does."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from my_agent_crew import texts
from my_agent_crew.agent.replay import replayable
from my_agent_crew.config import load_settings
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.server import build_runtime
from my_agent_crew.store.runs import AWAITING, DONE, RUNNING, RunRecord
from my_agent_crew.tools import Tool, ToolResult
from my_agent_crew.tools.ask_user import ASK_USER_TOOL_NAME
from my_agent_crew.tools.image import build_image_tool
from my_agent_crew.tools.workspace_search import build_search_tools
from tests.queue_helpers import Served
from tests.restart_helpers import carried_on, go_down, history, next_server, stored_run
from tests.test_server_api import parse_sse

GUARDED = ToolCall("g1", "guarded", {})
# Every tool that only reads. A tool added to this list is one a restart will run twice.
READS = {
    "artifact_list",
    "artifact_read",
    "conversation_search",
    "delegate",  # finds the child it already opened, and waits for it again
    "fetch_url",
    "image_read",
    "memory_search",
    "pdf_read",
    "progress_note",
    "skill_read",
    "tool_output_read",
    "web_search",
    "wiki_get",
    "wiki_search",
    "workspace_glob",
    "workspace_grep",
    "workspace_list",
    "workspace_read",
}


async def _noop(_: dict) -> ToolResult:
    return ToolResult(ok=True, output="")


def test_a_tool_that_says_nothing_is_taken_to_change_something():
    assert Tool("anything", "…", {"type": "object"}, _noop).replay_safe is False


def test_only_the_tools_that_read_may_be_made_again(tmp_path: Path):
    env = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    registry = runtime.default.tools
    tools = [registry.get(name) for name in registry.names()]
    # Not built for this agent, so taken from their builders.
    tools += [*build_search_tools(tmp_path), build_image_tool((tmp_path,), None)]
    runtime.hub.close()

    safe = {tool.name for tool in tools if tool.replay_safe}

    assert safe == READS
    assert {"workspace_write", "shell_run", "memory_save", "artifact_create"} <= {
        tool.name for tool in tools if not tool.replay_safe
    }
    # Nothing a person has to allow is ever made again on its own.
    assert not [t.name for t in tools if t.replay_safe and (t.requires_approval or t.ask_reason)]


async def paused_on_guarded(app: Served) -> str:
    """Sends a message whose turn pauses on the guarded tool; returns the decision's URL."""
    *_, pause = parse_sse((await app.client.post(app.messages, json={"text": "ghi đi"})).text)
    assert pause["type"] == "approval_required"
    return f"{app.detail}/approvals/{pause['approval_id']}"


async def test_a_write_a_person_allowed_is_not_made_again_after_it_was_cut(served):
    first = served([completion(tool_calls=[GUARDED])])
    first.guarded.release.clear()  # allowed, and still writing when the server stops
    url = await paused_on_guarded(first)
    decided = asyncio.create_task(first.client.post(url, json={"approve": True}))
    await asyncio.wait_for(first.guarded.started.wait(), 2)
    await go_down(first.runtime)
    await asyncio.wait_for(decided, 2)
    assert stored_run(first).status == RUNNING and first.guarded.runs == 1

    second = next_server(served, first, [completion("đã kiểm tra")])
    run = await carried_on(second)

    assert run.status == DONE and second.guarded.runs == 0
    assert history(second)[-2:] == [
        ("tool", texts.RESTART_CUT_TOOL),
        ("assistant", "đã kiểm tra"),
    ]
    assert second.runtime.store.approvals.pending(second.conv.id) is None


async def test_a_call_that_still_had_to_ask_is_asked_and_not_closed(served):
    """Cut between the model's answer and the request for a decision: it never ran."""
    first = served([])
    store, conv = first.runtime.store, first.conv
    store.append(conv.id, Message(role="user", content="ghi đi"))
    store.append(conv.id, Message(role="assistant", content="", tool_calls=(GUARDED,)))
    store.runs.save(
        RunRecord("r1", "default", conv.id, "chat", "t", RUNNING, "2026-10-06T08:00:00")
    )

    second = next_server(served, first, [])
    run = await carried_on(second)

    assert (run.id, run.status) == ("r1", AWAITING) and second.guarded.runs == 0
    pending = second.runtime.store.approvals.pending(conv.id)
    assert pending is not None and pending.tool_name == "guarded"
    assert history(second)[-1] == ("assistant", "")  # no result yet: it waits on the person


@pytest.mark.parametrize(
    "call",
    [
        ToolCall("u1", "no_such_tool", {}),
        ToolCall("i1", "slow", {}, invalid="Expecting value: line 1 column 1 (char 0)"),
    ],
    ids=["unknown tool", "arguments that never parsed"],
)
async def test_a_call_that_could_never_run_fails_as_itself_not_as_a_cut_call(served, call):
    first = served([])
    store, conv = first.runtime.store, first.conv
    store.append(conv.id, Message(role="user", content="làm đi"))
    store.append(conv.id, Message(role="assistant", content="", tool_calls=(call,)))
    store.runs.save(
        RunRecord("r1", "default", conv.id, "chat", "t", RUNNING, "2026-10-06T08:00:00")
    )

    second = next_server(served, first, [completion("gọi sai, xin lỗi")])
    run = await carried_on(second)

    assert run.status == DONE and second.slow.runs == 0
    role, said = history(second)[-2]
    assert role == "tool" and said and said != texts.RESTART_CUT_TOOL


def test_what_a_person_decided_about_a_call_says_whether_it_may_have_run(deps_factory):
    safe = Tool("peek", "…", {"type": "object"}, _noop, replay_safe=True)
    write = Tool("write", "…", {"type": "object"}, _noop)
    locked = Tool("locked", "…", {"type": "object"}, _noop, requires_approval=True)
    deps = deps_factory(extra_tools=[safe, write, locked])
    store = deps.store
    conv = store.create()

    def decided(call: ToolCall, approve: bool | None) -> ToolCall:
        approval = store.approvals.create(conv.id, 1, call, ttl_seconds=600)
        if approve is not None:
            store.approvals.resolve(approval.id, approve=approve)
        return call

    def may_repeat(call: ToolCall) -> bool:
        return replayable(deps, store.get(conv.id), call)

    # Nobody was asked: a tool that runs unasked may have run, one that asks first has not.
    assert may_repeat(ToolCall("a", "peek", {})) is True
    assert may_repeat(ToolCall("b", "write", {})) is False
    assert may_repeat(ToolCall("c", "locked", {})) is True
    # Still waiting, or refused: it did not run, and the turn settles it.
    assert may_repeat(decided(ToolCall("d", "locked", {}), None)) is True
    assert may_repeat(decided(ToolCall("e", "locked", {}), False)) is True
    # Allowed: it may have run, so only a read is made again.
    assert may_repeat(decided(ToolCall("f", "locked", {}), True)) is False
    # A decision about some other call under the same id decides nothing for this one.
    decided(ToolCall("g", "locked", {"path": "a"}), True)
    assert may_repeat(ToolCall("g", "locked", {"path": "b"})) is True
    # A question is answered by what the person said, which the store still holds.
    ask = ToolCall("h", ASK_USER_TOOL_NAME, {"question": "A hay B?", "options": ["A", "B"]})
    assert may_repeat(ask) is True
