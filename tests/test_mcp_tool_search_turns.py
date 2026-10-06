"""Turns that load a server's tools with `tool_search`: from when the model is told of a
tool it loaded and in what order, and what a later turn, another conversation and a
restart make of it (`agent/declared_tools.py` over `mcp/tool_search.py`)."""

from __future__ import annotations

from my_agent_crew import texts
from my_agent_crew import texts_mcp as t
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.mcp.tool_search import SEARCH_TOOL
from my_agent_crew.store.runs import DONE
from tests.queue_helpers import Served
from tests.restart_helpers import carried_on, history, next_server
from tests.test_mcp_turns import cut_while_the_server_answers, declared, say, use, with_notion
from tests.test_server_api import parse_sse

SEARCH_NAME, CREATE_NAME = "mcp__notion__search", "mcp__notion__create_page"
FIND_CREATE = ToolCall("s1", SEARCH_TOOL, {"query": "make a page", "limit": 1})
FIND_SEARCH = ToolCall("s2", SEARCH_TOOL, {"query": "find by words"})
CREATE = ToolCall("c1", CREATE_NAME, {"title": "Báo cáo"})


def up_front(app: Served) -> list[str]:
    """What the agent is told of before it has searched for anything."""
    names = app.runtime.default.tools.names()
    return [name for name in names if not name.startswith("mcp__")]


def system(app: Served, call: int) -> str:
    return app.provider.requests[call].messages[0].content


async def test_a_tool_the_agent_searched_for_is_told_from_the_next_call_on(served):
    script = [
        completion(tool_calls=[FIND_CREATE]),
        completion(tool_calls=[FIND_SEARCH]),
        completion("xong"),
    ]
    app, fake = await with_notion(served, script)
    base = up_front(app)
    assert base[-1] == SEARCH_TOOL

    events = await say(app)

    # A search waits for nobody and asks the server nothing.
    kinds = [event["type"] for event in events]
    assert "approval_required" not in kinds and kinds[-1] == "done"
    assert fake.calls == [] and "tools/call" not in fake.methods()
    first, second = [event for event in events if event["type"] == "tool_result"]
    assert (first["name"], first["ok"]) == (SEARCH_TOOL, True)
    assert first["output"] == (
        f"{t.TOOL_SEARCH_LOADED.format(count=1)}\n"
        f"- {CREATE_NAME}: [MCP notion] Make a page.\n"
        f"{t.TOOL_SEARCH_MORE.format(count=1)}"
    )
    assert second["output"].splitlines()[1:] == [
        f"- {SEARCH_NAME}: [MCP notion] Find pages by words."
    ]
    # Each load goes on the end: what the model was told before is told again as it was,
    # so the part of the request a provider keeps from call to call is still the same.
    assert declared(app, 0) == base
    assert declared(app, 1) == [*base, CREATE_NAME]
    assert declared(app, 2) == [*base, CREATE_NAME, SEARCH_NAME]
    assert system(app, 0) == system(app, 1) == system(app, 2)
    assert SEARCH_TOOL in system(app, 0) and CREATE_NAME not in system(app, 0)


async def test_a_tool_that_was_loaded_still_waits_for_a_person(served):
    script = [
        completion(tool_calls=[FIND_CREATE]),
        completion(tool_calls=[CREATE]),
        completion("Đã tạo."),
    ]
    app, fake = await with_notion(served, script)
    base = up_front(app)

    *_, pause = await say(app)

    assert (pause["type"], pause["name"]) == ("approval_required", CREATE_NAME)
    assert fake.calls == []
    url = f"{app.detail}/approvals/{pause['approval_id']}"
    resumed = parse_sse((await app.client.post(url, json={"approve": True})).text)

    assert resumed[-1]["type"] == "done"
    assert fake.calls == [("create-page", {"title": "Báo cáo"})]
    # The turn a person let go on reads the conversation again, and finds the load in it.
    assert declared(app, 2) == [*base, CREATE_NAME]
    assert history(app)[-2:] == [("tool", "ran create-page"), ("assistant", "Đã tạo.")]


async def test_a_load_lasts_the_conversation_and_reaches_no_other(served):
    script = [
        completion(tool_calls=[FIND_CREATE]),
        completion("xong"),
        completion("lượt sau"),
        completion("chỗ khác"),
    ]
    app, _ = await with_notion(served, script)
    base = up_front(app)
    await say(app)

    await say(app, "làm tiếp")
    other = app.runtime.store.create("Việc khác", agent_id=app.runtime.default.agent.id)
    await app.client.post(f"/api/conversations/{other.id}/messages", json={"text": "chào"})

    assert declared(app, 2) == [*base, CREATE_NAME]
    assert declared(app, 3) == base


async def test_a_restart_leaves_what_a_conversation_loaded_as_it_was(served):
    """What was loaded is in the conversation, not in the server that went down: the turn
    the next server carries on is told of the same tools, in the same order."""
    script = [
        completion(tool_calls=[FIND_SEARCH]),
        completion(tool_calls=[FIND_CREATE]),
        completion(tool_calls=[CREATE]),
    ]
    first, fake = await with_notion(served, script)
    base, hub = up_front(first), first.runtime.mcp
    await cut_while_the_server_answers(first, fake)
    assert declared(first, 2) == [*base, SEARCH_NAME, CREATE_NAME]

    second = next_server(served, first, [completion("Đã kiểm tra lại.")])
    use(second, hub)
    run = await carried_on(second)

    assert run.status == DONE and fake.calls == []
    assert declared(second) == [*base, SEARCH_NAME, CREATE_NAME]
    assert history(second)[-2:] == [
        ("tool", texts.RESTART_CUT_TOOL),
        ("assistant", "Đã kiểm tra lại."),
    ]


async def test_a_loaded_tool_the_server_stopped_listing_is_told_no_longer(served):
    script = [completion(tool_calls=[FIND_CREATE]), completion("xong"), completion("lượt sau")]
    app, fake = await with_notion(served, script)
    base = up_front(app)
    await say(app)
    assert declared(app, 1) == [*base, CREATE_NAME]

    fake.tools = [tool for tool in fake.tools if tool["name"] != "create-page"]
    await app.runtime.mcp.connect()
    app.runtime.wire_delegation()
    await say(app, "làm tiếp")

    assert declared(app, 2) == base
