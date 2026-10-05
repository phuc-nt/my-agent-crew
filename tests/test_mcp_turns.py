"""A turn that uses a server's tools: what the model is told of them, which calls wait for
a person, and what a restart does with a call it cut (`agent/declared_tools.py`,
`agent/tool_gate.py`, `agent/replay.py` over `mcp/hub.py`)."""

from __future__ import annotations

import asyncio
from dataclasses import replace

from my_agent_crew import texts
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.mcp.hub import McpHub
from my_agent_crew.store.runs import DONE, RUNNING
from my_agent_crew.tools.delegate import DELEGATE_TOOL_NAME
from tests.mcp_fakes import FakeMcp, make_hub, server
from tests.queue_helpers import Served, until
from tests.restart_helpers import carried_on, go_down, history, next_server, stored_run
from tests.test_server_api import parse_sse

SEARCH_NAME, CREATE_NAME = "mcp__notion__search", "mcp__notion__create_page"
SEARCH = ToolCall("c1", SEARCH_NAME, {"query": "kế hoạch"})
CREATE = ToolCall("c2", CREATE_NAME, {"title": "Báo cáo"})


def use(app: Served, hub: McpHub) -> None:
    """The app's agent names the server, and is wired the way a start wires it."""
    deps = app.runtime.default
    deps.profile = replace(deps.agent, mcp=("notion",))
    app.runtime.mcp = hub
    app.runtime.wire_delegation()


async def with_notion(served, script, **settings) -> tuple[Served, FakeMcp]:
    app, fake = served(script), FakeMcp()
    hub = make_hub(fake, server(**settings))
    await hub.connect()
    use(app, hub)
    return app, fake


async def say(app: Served, text: str = "làm đi") -> list[dict]:
    return parse_sse((await app.client.post(app.messages, json={"text": text})).text)


def declared(app: Served, call: int = 0) -> list[str]:
    return [spec.name for spec in app.provider.requests[call].tools]


async def test_a_tool_the_owner_says_only_reads_runs_unasked_and_its_text_is_the_result(served):
    script = [completion(tool_calls=[SEARCH]), completion("Có một trang.")]
    app, fake = await with_notion(served, script, read_only=["search"])

    events = await say(app)

    kinds = [event["type"] for event in events]
    assert "approval_required" not in kinds and kinds[-1] == "done"
    [result] = [event for event in events if event["type"] == "tool_result"]
    assert (result["name"], result["ok"], result["output"]) == (SEARCH_NAME, True, "ran search")
    assert fake.calls == [("search", {"query": "kế hoạch"})]
    assert history(app)[-2:] == [("tool", "ran search"), ("assistant", "Có một trang.")]


async def test_any_other_tool_waits_for_a_person_and_reaches_the_server_once_allowed(served):
    script = [completion(tool_calls=[CREATE]), completion("Đã tạo.")]
    app, fake = await with_notion(served, script, read_only=["search"])

    *_, pause = await say(app)

    assert (pause["type"], pause["name"]) == ("approval_required", CREATE_NAME)
    assert pause["arguments"] == {"title": "Báo cáo"} and pause["reason"] == ""
    assert fake.calls == []  # nothing has left for the server yet
    url = f"{app.detail}/approvals/{pause['approval_id']}"
    resumed = parse_sse((await app.client.post(url, json={"approve": True})).text)

    assert resumed[-1]["type"] == "done"
    assert fake.calls == [("create-page", {"title": "Báo cáo"})]
    assert history(app)[-2:] == [("tool", "ran create-page"), ("assistant", "Đã tạo.")]


async def test_a_call_a_person_refuses_never_reaches_the_server(served):
    script = [completion(tool_calls=[CREATE]), completion("Vậy thôi.")]
    app, fake = await with_notion(served, script)

    *_, pause = await say(app)
    url = f"{app.detail}/approvals/{pause['approval_id']}"
    resumed = parse_sse((await app.client.post(url, json={"approve": False})).text)

    assert resumed[-1]["type"] == "done" and fake.calls == []
    assert "tools/call" not in fake.methods()


async def test_a_server_that_only_says_its_tool_reads_does_not_get_it_run_unasked(served):
    """`search` comes with `readOnlyHint`. The owner has not said so, so it asks."""
    app, fake = await with_notion(served, [completion(tool_calls=[SEARCH])])

    *_, pause = await say(app)

    assert (pause["type"], pause["name"]) == ("approval_required", SEARCH_NAME)
    assert fake.calls == []


async def test_the_model_is_told_only_of_the_tools_let_in_directly(served):
    script = [completion(tool_calls=[SEARCH]), completion("xong")]
    app, fake = await with_notion(
        served, script, read_only=["search"], tool_exposure={"create-page": "direct"}
    )
    own = [name for name in app.runtime.default.tools.names() if not name.startswith("mcp__")]

    await say(app)

    # `search` is held back, and still ran when the model named it: being told of a tool
    # and being allowed to use it are two things.
    assert declared(app) == [*own, CREATE_NAME]
    assert declared(app, 1) == declared(app)
    assert fake.calls == [("search", {"query": "kế hoạch"})]
    system = app.provider.requests[0].messages[0].content
    assert CREATE_NAME in system and SEARCH_NAME not in system


async def test_wiring_the_crew_again_leaves_each_tool_once_and_where_it_was(served):
    app, _ = await with_notion(served, [])
    deps = app.runtime.default
    before = deps.tools.names()
    assert before[-2:] == [SEARCH_NAME, CREATE_NAME]

    app.runtime.wire_delegation()
    app.runtime.wire_delegation()

    assert deps.tools.names() == before
    # Work handed to this agent by another is done with the same servers.
    child = app.runtime.deps_for_child(deps.agent.id).tools.names()
    assert child == [name for name in before if name != DELEGATE_TOOL_NAME]

    deps.profile = replace(deps.agent, mcp=())
    app.runtime.wire_delegation()
    assert not [name for name in deps.tools.names() if name.startswith("mcp__")]


async def cut_while_the_server_answers(app: Served, fake: FakeMcp) -> None:
    """Sends a message whose turn calls the server, and takes the app down while that call
    is still on its way: the server never got to run it."""
    await app.client.patch(app.detail, json={"autonomous": True})
    fake.delay, sent = 30.0, len(fake.fetched)
    sender = asyncio.create_task(app.client.post(app.messages, json={"text": "làm đi"}))
    await until(lambda: len(fake.fetched) > sent)
    await go_down(app.runtime)
    await asyncio.wait_for(sender, 2)
    fake.delay = 0.0
    assert stored_run(app).status == RUNNING and fake.calls == []


async def test_a_call_a_restart_cut_is_not_made_again_unless_the_tool_only_reads(served):
    """Nobody knows whether the server ran it. A page made twice is worse than a model
    told to look first."""
    first, fake = await with_notion(served, [completion(tool_calls=[CREATE])])
    hub = first.runtime.mcp
    await cut_while_the_server_answers(first, fake)

    second = next_server(served, first, [completion("Đã kiểm tra lại.")])
    use(second, hub)
    run = await carried_on(second)

    assert run.status == DONE and fake.calls == []
    assert history(second)[-2:] == [
        ("tool", texts.RESTART_CUT_TOOL),
        ("assistant", "Đã kiểm tra lại."),
    ]


async def test_a_cut_call_to_a_tool_that_only_reads_is_simply_made_again(served):
    first, fake = await with_notion(served, [completion(tool_calls=[SEARCH])], read_only=["search"])
    hub = first.runtime.mcp
    await cut_while_the_server_answers(first, fake)

    second = next_server(served, first, [completion("Có một trang.")])
    use(second, hub)
    run = await carried_on(second)

    assert run.status == DONE and fake.calls == [("search", {"query": "kế hoạch"})]
    assert history(second)[-2:] == [("tool", "ran search"), ("assistant", "Có một trang.")]
