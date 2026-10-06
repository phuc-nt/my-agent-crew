"""A turn that runs a script: nobody is asked, the model reads only what the script
printed, each call the script made is kept on the run and charged when it paid a model,
and a script a restart cut is run again (`agent/tool_calls.py`, `activity/steps.py` and
`agent/replay.py` over `script/tool.py`)."""

from __future__ import annotations

from textwrap import dedent
from typing import Any

import pytest

from my_agent_crew import texts_script as t
from my_agent_crew.activity.steps import apply_event
from my_agent_crew.agent.events import ToolCallEvent, ToolResultEvent
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.mcp.tool_search import SEARCH_TOOL
from my_agent_crew.script.tool import SCRIPT_TOOL
from my_agent_crew.store.runs import DONE, RUNNING, RunRecord
from my_agent_crew.tools import Tool, ToolResult
from tests.mcp_fakes import FakeMcp, make_hub, server
from tests.queue_helpers import Served
from tests.restart_helpers import carried_on, history, next_server, stored_run
from tests.test_mcp_turns import (
    CREATE,
    CREATE_NAME,
    SEARCH_NAME,
    cut_while_the_server_answers,
    declared,
    say,
    use,
)

OPENED = {"read_only": ["search"], "tool_exposure": {"search": "codemode"}}
SOURCE = dedent(
    """
    found = tools.mcp__notion__search(query="kế hoạch")
    again = tools.mcp__notion__search(query="báo cáo")
    print("tìm được:", found, "|", again)
    """
)
PRINTED = "tìm được: ran search | ran search"
RUN = ToolCall("p1", SCRIPT_TOOL, {"script": SOURCE})
BOTH = [("search", {"query": "kế hoạch"}), ("search", {"query": "báo cáo"})]


def running(source: str) -> ToolCall:
    return ToolCall("p1", SCRIPT_TOOL, {"script": source})


async def scripting(served, script, extra_tools=(), **opened) -> tuple[Served, FakeMcp]:
    """The app's agent with a server whose `search` is opened for scripts."""
    app, fake = served(script, extra_tools=extra_tools), FakeMcp()
    hub = make_hub(fake, server(**(opened or OPENED)))
    await hub.connect()
    use(app, hub)
    return app, fake


def the_result(events: list[dict]) -> dict:
    [result] = [event for event in events if event["type"] == "tool_result"]
    return result


def the_step(app: Served) -> dict:
    [step] = [step for step in stored_run(app).steps if step.get("name") == SCRIPT_TOOL]
    return step


def reading(name: str, **paid: Any) -> Tool:
    """A tool that only reads, and says it paid a model what `paid` says."""

    async def run(arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(ok=True, output=name, **paid)

    return Tool(name, f"Đọc {name}.", {"type": "object", "properties": {}}, run, replay_safe=True)


async def test_a_script_runs_unasked_and_the_model_reads_only_what_it_printed(served):
    app, fake = await scripting(served, [completion(tool_calls=[RUN]), completion("Có hai trang.")])

    events = await say(app)

    kinds = [event["type"] for event in events]
    assert "approval_required" not in kinds and kinds[-1] == "done"
    result = the_result(events)
    assert (result["name"], result["ok"], result["output"]) == (SCRIPT_TOOL, True, PRINTED)
    assert fake.calls == BOTH
    # What the server answered was the script's to read. The conversation holds one call
    # and one result, and so does what the model is sent next.
    assert history(app) == [
        ("user", "làm đi"),
        ("assistant", ""),
        ("tool", PRINTED),
        ("assistant", "Có hai trang."),
    ]
    sent = app.provider.requests[1].messages
    assert [message.content for message in sent if message.role == "tool"] == [PRINTED]


async def test_the_run_keeps_each_call_the_script_made(served):
    app, _ = await scripting(served, [completion(tool_calls=[RUN]), completion("Xong.")])

    result = the_result(await say(app))

    step = the_step(app)
    assert (step["ok"], step["output"]) == (True, PRINTED)
    assert step["calls"] == result["calls"]
    assert [{**call, "ms": 0} for call in step["calls"]] == [
        {
            "name": SEARCH_NAME,
            "arguments": arguments,
            "ok": True,
            "output": "ran search",
            "ms": 0,
            "cost_usd": None,
            "metered": False,
        }
        for _, arguments in BOTH
    ]
    assert all(type(call["ms"]) is int and 0 <= call["ms"] < 2000 for call in step["calls"])
    # A call the script made is a row under the script, never a step of its own.
    tools = [step["name"] for step in stored_run(app).steps if step["kind"] == "tool"]
    assert tools == [SCRIPT_TOOL]


def test_a_step_keeps_the_calls_of_a_script_and_bills_the_ones_that_paid_a_model():
    run = RunRecord("r1", "default", "c1", "chat", "t", RUNNING, "2026-10-06T08:00:00")
    made = [
        {"name": "paid_read", "ok": True, "cost_usd": 0.004, "metered": True},
        {"name": "paid_read", "ok": False, "cost_usd": 0.002, "metered": True},
        {"name": "unpriced_read", "ok": True, "cost_usd": None, "metered": True},
        {"name": "free_read", "ok": True, "cost_usd": 0.5, "metered": False},
    ]
    apply_event(run, ToolCallEvent("p1", SCRIPT_TOOL, {"script": "…"}), 10.0)
    apply_event(run, ToolResultEvent("p1", SCRIPT_TOOL, True, "xong", calls=made), 11.0)
    apply_event(run, ToolCallEvent("c2", "workspace_list", {}), 11.1)
    apply_event(run, ToolResultEvent("c2", "workspace_list", True, "a.txt"), 11.2)

    script, plain = run.steps
    assert script["calls"] == made and "calls" not in plain
    # The script paid nothing itself, so its step shows no price of its own.
    assert "cost_usd" not in script
    assert run.spent_usd == pytest.approx(0.006) and run.unknown_cost_calls == 1


async def test_each_call_of_a_script_that_paid_a_model_is_charged_like_one_made_directly(served):
    source = "print(tools.paid_read(), tools.paid_read(), tools.unpriced_read(), tools.free_read())"
    held = [
        reading("paid_read", cost_usd=0.004, metered=True),
        reading("unpriced_read", metered=True),
        reading("free_read", cost_usd=0.5),
    ]
    script = [completion(tool_calls=[running(source)]), completion("Xong.")]
    app, _ = await scripting(served, script, extra_tools=held)

    result = the_result(await say(app))

    assert result["output"] == "paid_read paid_read unpriced_read free_read"
    assert (result["cost_usd"], result["metered"]) == (None, False)
    # Two answers of the model at 0.001 each, and the two reads that named their price.
    conv, run = app.runtime.store.get(app.conv.id), stored_run(app)
    assert conv.spent_usd == pytest.approx(0.010) and conv.unknown_cost_calls == 1
    assert run.spent_usd == pytest.approx(0.010) and run.unknown_cost_calls == 1
    step = the_step(app)
    assert "cost_usd" not in step
    assert [(call["name"], call["cost_usd"], call["metered"]) for call in step["calls"]] == [
        ("paid_read", 0.004, True),
        ("paid_read", 0.004, True),
        ("unpriced_read", None, True),
        ("free_read", None, False),
    ]


async def test_the_model_is_told_of_the_script_tool_and_not_of_the_tools_it_calls(served):
    app, _ = await scripting(served, [completion(tool_calls=[RUN]), completion("Xong.")])
    own = [name for name in app.runtime.default.tools.names() if not name.startswith("mcp__")]

    await say(app)

    assert own[-2:] == [SEARCH_TOOL, SCRIPT_TOOL]
    # Neither of the server's tools is told up front, and running a script loads none.
    assert declared(app) == own and declared(app, 1) == own
    [spec] = [spec for spec in app.provider.requests[0].tools if spec.name == SCRIPT_TOOL]
    assert f"- {SEARCH_NAME}(query: string): [MCP notion] Find pages by words." in spec.description
    assert spec.parameters["required"] == ["script"]


async def test_a_call_a_script_may_not_make_never_reaches_the_server_and_asks_nobody(served):
    source = "print('trước')\ntools.mcp__notion__create_page(title='Báo cáo')\nprint('sau')"
    script = [completion(tool_calls=[running(source)]), completion(tool_calls=[CREATE])]
    app, fake = await scripting(served, script)

    events = await say(app)

    result = the_result(events)
    reason = t.SCRIPT_ASKS_FIRST.format(name=CREATE_NAME, instead=t.SCRIPT_LOAD_THEN_CALL)
    refused = "trước\n" + t.SCRIPT_HALTED.format(line=2, reason=reason)
    assert (result["name"], result["ok"], result["output"]) == (SCRIPT_TOOL, False, refused)
    assert result["calls"] == []
    assert history(app)[-2] == ("tool", refused)
    # The same call made by the model itself waits for a person, as it always did.
    pause = events[-1]
    assert (pause["type"], pause["name"]) == ("approval_required", CREATE_NAME)
    assert [event["type"] for event in events].count("approval_required") == 1
    assert fake.calls == [] and "tools/call" not in fake.methods()


async def test_a_script_that_fails_tells_the_model_what_it_printed_and_why(served):
    source = "print(tools.mcp__notion__search(query='kế hoạch'))\nundefined_name"
    script = [completion(tool_calls=[running(source)]), completion("Để tôi sửa.")]
    app, fake = await scripting(served, script)

    result = the_result(await say(app))

    why = t.SCRIPT_ERROR.format(line=2, error=t.SCRIPT_NO_NAME.format(name="undefined_name"))
    assert (result["ok"], result["output"]) == (False, f"ran search\n{why}")
    assert history(app)[-2:] == [("tool", f"ran search\n{why}"), ("assistant", "Để tôi sửa.")]
    # The call it made before failing was made, and the run says so.
    assert fake.calls == [("search", {"query": "kế hoạch"})]
    step = the_step(app)
    assert step["ok"] is False and [call["name"] for call in step["calls"]] == [SEARCH_NAME]


async def test_a_script_a_restart_cut_is_run_again_from_its_start(served):
    first, fake = await scripting(served, [completion(tool_calls=[RUN])])
    hub = first.runtime.mcp
    await cut_while_the_server_answers(first, fake)

    second = next_server(served, first, [completion("Có hai trang.")])
    use(second, hub)
    run = await carried_on(second)

    # Every call a script makes only reads, so nothing is lost by making them all again.
    assert run.status == DONE and fake.calls == BOTH
    assert history(second)[-2:] == [("tool", PRINTED), ("assistant", "Có hai trang.")]
    [step] = [step for step in run.steps if step.get("name") == SCRIPT_TOOL]
    assert [call["arguments"] for call in step["calls"]] == [arguments for _, arguments in BOTH]
