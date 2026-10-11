"""A turn of an agent whose scripts may change things (`script_calls: gated`), on the app.

A call the approval gate let run is marked wherever the calls of a script are listed: as it
ends, on the script's result, on the run and beside the stored result. A script the gate
stopped has made nothing of that call; the model makes it directly instead, and there the
turn waits for a person (`tools/result.py`, `agent/tool_run.py`, `agent/tool_calls.py` and
`activity/tool_steps.py` over `script/nested.py`). What the gate says of one call is in
`test_script_gate.py`."""

from __future__ import annotations

import json
from textwrap import dedent

from my_agent_crew import texts_script as t
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.script.scope import SCRIPT_TOOL
from my_agent_crew.tools import Tool
from my_agent_crew.tools.shell import SHELL_TOOL_NAME
from tests.queue_helpers import Served
from tests.restart_helpers import history, stored_run
from tests.test_mcp_turns import say
from tests.test_script_gate import Shell
from tests.test_script_tool import halted, unfinished
from tests.test_script_turns import the_result, the_step
from tests.test_server_api import parse_sse
from tests.test_tool_replay import changing

ROW = {"type": "object", "properties": {"row": {"type": "integer"}}}
# Line 2 reads, line 3 changes things.
WORK = """
    print(tools.row_read(row=1))
    print(tools.shell_run(command="ls -la"))
    """
PRINTED = "dòng 1\nđã chạy 1"
# What a call kept of a script holds when it only read: as it was before a script could
# do more, so that nothing that reads one has to know of the mark.
KEPT = {"name", "arguments", "ok", "output", "ms", "cost_usd", "metered"}
DIRECT = ToolCall("d1", SHELL_TOOL_NAME, {"command": "ls -la"})


def working(source: str = WORK) -> ToolCall:
    return ToolCall("p1", SCRIPT_TOOL, {"script": dedent(source)})


def row_tool() -> Tool:
    async def row_read(arguments: dict) -> str:
        return f"dòng {arguments.get('row', 0)}"

    return Tool("row_read", "Đọc một dòng.", ROW, row_read, replay_safe=True)


def an_app(served, script, gated: bool = True) -> tuple[Served, Shell]:
    """The app's agent with a tool that reads and a shell that only keeps what it was
    handed, wired the way a start wires it. Its scripts may change things when `gated`."""
    app, shell = served(script, extra_tools=[row_tool()]), Shell()
    deps = app.runtime.default
    deps.tools = deps.tools.without(SHELL_TOOL_NAME)
    deps.tools.register(shell.tool)
    if gated:
        changing(app)
    else:
        app.runtime.wire_delegation()
    return app, shell


async def left_to_itself(app: Served) -> None:
    await app.client.patch(app.detail, json={"autonomous": True})


def stored_calls(app: Served) -> list[dict]:
    """The calls kept beside the stored result of the turn's one script."""
    kept = [m for m in app.runtime.store.history(app.conv.id) if m.context]
    [stored] = kept
    assert (stored.message.role, stored.message.tool_call_id) == ("tool", "p1")
    return json.loads(stored.context)["calls"]


async def test_a_call_the_gate_let_run_is_marked_wherever_a_script_lists_its_calls(served):
    app, shell = an_app(served, [completion(tool_calls=[working()]), completion("Xong.")])
    await left_to_itself(app)

    events = await say(app)

    kinds = [event["type"] for event in events]
    assert "approval_required" not in kinds and kinds[-1] == "done"
    assert shell.ran == ["ls -la"]
    result = the_result(events)
    assert (result["name"], result["ok"], result["output"]) == (SCRIPT_TOOL, True, PRINTED)
    read, changed = result["calls"]
    assert (read["name"], read["ok"], read["output"]) == ("row_read", True, "dòng 1")
    shown = (changed["name"], changed["arguments"], changed["ok"], changed["output"])
    assert shown == (SHELL_TOOL_NAME, {"command": "ls -la"}, True, "đã chạy 1")
    # Written only where it is set: the call that read is kept as one always was.
    assert changed["gated"] is True and set(changed) == KEPT | {"gated"}
    assert set(read) == KEPT
    # As each call ended, on the run, and beside the result the conversation keeps.
    assert [event["call"] for event in events if event["type"] == "nested_call"] == [read, changed]
    assert the_step(app)["calls"] == [read, changed]
    assert stored_calls(app) == [read, changed]
    assert history(app)[-2:] == [("tool", PRINTED), ("assistant", "Xong.")]


async def test_a_batch_marks_the_calls_that_went_through_the_gate_and_no_other(served):
    source = """
        answers = tools.batch([
            {"tool": "shell_run", "args": {"command": "ls một"}},
            {"tool": "row_read", "args": {"row": 2}},
            {"tool": "shell_run", "args": {"command": "ls hai"}},
        ])
        print([answer["ok"] for answer in answers])
        """
    app, shell = an_app(served, [completion(tool_calls=[working(source)]), completion("Xong.")])
    await left_to_itself(app)

    events = await say(app)

    assert the_result(events)["output"] == "[True, True, True]"
    # One at a time, as written: the second command found what the first left.
    assert shell.ran == ["ls một", "ls hai"]
    marks = [(call["name"], call.get("gated", False)) for call in the_result(events)["calls"]]
    assert marks == [(SHELL_TOOL_NAME, True), ("row_read", False), (SHELL_TOOL_NAME, True)]
    assert the_step(app)["calls"] == stored_calls(app) == the_result(events)["calls"]
    assert [set(call) - KEPT for call in stored_calls(app)] == [{"gated"}, set(), {"gated"}]


async def test_an_agent_left_as_it_was_has_no_call_to_mark(served):
    """Its script may not call the shell at all: that is refused before the gate is asked
    anything, and the calls it did make are kept as they always were."""
    script = [completion(tool_calls=[working()]), completion("Không được.")]
    app, shell = an_app(served, script, gated=False)
    await left_to_itself(app)

    events = await say(app)

    result = the_result(events)
    refusal = t.SCRIPT_ASKS_FIRST.format(name=SHELL_TOOL_NAME, instead=t.SCRIPT_CALL_DIRECTLY)
    assert (result["ok"], result["output"]) == (False, unfinished("dòng 1", halted(3, refusal)))
    assert shell.ran == []
    [read] = result["calls"]
    assert read["name"] == "row_read" and set(read) == KEPT
    assert the_step(app)["calls"] == stored_calls(app) == [read]


async def test_a_script_the_gate_stopped_leaves_the_call_to_be_made_directly_and_asked_about(
    served,
):
    """Nobody said this conversation may act unasked. The script ends on the call instead
    of waiting; the same call made directly is the one a person is asked about."""
    script = [
        completion(tool_calls=[working()]),
        completion(tool_calls=[DIRECT]),
        completion("Đã chạy."),
    ]
    app, shell = an_app(served, script)

    *events, pause = await say(app)

    stopped = the_result(events)
    refusal = t.SCRIPT_GATE_ASKS.format(name=SHELL_TOOL_NAME)
    assert (stopped["name"], stopped["ok"]) == (SCRIPT_TOOL, False)
    assert stopped["output"] == unfinished("dòng 1", halted(3, refusal))
    # The call that read was made and is listed; the one refused was never a call.
    assert [call["name"] for call in stopped["calls"]] == ["row_read"]
    assert not any("gated" in call for call in stopped["calls"])
    assert shell.ran == []
    # The model read the refusal, and made the call where a person can be asked.
    assert history(app)[2] == ("tool", stopped["output"])
    assert (pause["type"], pause["name"]) == ("approval_required", SHELL_TOOL_NAME)
    assert pause["arguments"] == {"command": "ls -la"}

    url = f"{app.detail}/approvals/{pause['approval_id']}"
    resumed = parse_sse((await app.client.post(url, json={"approve": True})).text)

    assert resumed[-1]["type"] == "done" and shell.ran == ["ls -la"]
    assert history(app)[-2:] == [("tool", "đã chạy 1"), ("assistant", "Đã chạy.")]
    # A call made directly is a step of its own, and no script's.
    direct = [step for step in stored_run(app).steps if step.get("name") == SHELL_TOOL_NAME]
    assert [("calls" in step, step["ok"]) for step in direct] == [(False, True)]
