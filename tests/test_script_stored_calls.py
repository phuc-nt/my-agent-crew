"""A script's result is stored with what the script called and its two measures, beside the
output the model reads: the chat card lists them after a reload, when the run that showed
them may be gone, and no model is ever sent them (`agent/tool_events.py`,
`agent/tool_calls.py`, `agent/payload_trim.py`, `store/message_models.py`)."""

from __future__ import annotations

import json
from textwrap import dedent

from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.activity.trajectory import build
from my_agent_crew.agent.events import ToolResultEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.payload_trim import attach_canvas_notes
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.script.tool import SCRIPT_TOOL, script_tool
from my_agent_crew.store import StoredMessage
from my_agent_crew.texts_canvas import CANVAS_NOTE_STUB
from my_agent_crew.tools import Tool
from tests.conftest import collect

SCHEMA = {"type": "object", "properties": {"row": {"type": "integer"}}}
READS = """
    first = tools.row_read(row=1)
    tools.row_read(row=2)
    print("đọc xong")
    """


def scripted(source: str = READS, call_id: str = "p1") -> ToolCall:
    return ToolCall(call_id, SCRIPT_TOOL, {"script": dedent(source)})


def a_turn(deps_factory, script):
    """Deps whose agent holds `row_read`, which only reads, and `tool_script`."""

    async def row_read(arguments: dict) -> str:
        return f"dòng {arguments.get('row', 0)}"

    tools = [Tool("row_read", "Đọc một dòng.", SCHEMA, row_read, replay_safe=True)]
    deps = deps_factory(script=script, extra_tools=tools)
    deps.tools.register(script_tool(lambda: deps.tools, []))
    return deps


def tool_messages(deps, conv_id: str) -> list[StoredMessage]:
    return [m for m in deps.store.history(conv_id) if m.message.role == "tool"]


def sent(deps) -> list[list[str]]:
    """What each call of the model was sent, as the text of every message."""
    return [[m.content for m in r.messages] for r in deps.chain.providers["scripted"].requests]


async def test_a_script_result_is_stored_with_what_it_called_and_its_measures(deps_factory):
    deps = a_turn(deps_factory, [completion(tool_calls=[scripted()]), completion("Xong.")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đọc hai dòng"))

    [result] = [event for event in events if isinstance(event, ToolResultEvent)]
    [stored] = tool_messages(deps, conv.id)
    kept = json.loads(stored.context)
    assert set(kept) == {"calls", "received_chars", "printed_chars"}
    assert kept["calls"] == result.calls and len(kept["calls"]) == 2
    shown = [(c["name"], c["arguments"], c["ok"], c["output"]) for c in kept["calls"]]
    assert shown == [
        ("row_read", {"row": 1}, True, "dòng 1"),
        ("row_read", {"row": 2}, True, "dòng 2"),
    ]
    assert (kept["received_chars"], kept["printed_chars"]) == (12, 8)
    # The words stay as written: the web reads this as it is.
    assert '"output": "dòng 1"' in stored.context
    # The content is the output and nothing more, and the web is handed both.
    assert stored.message.content == result.output == "đọc xong"
    handed = stored.to_dict()
    assert (handed["content"], handed["context"]) == ("đọc xong", stored.context)


async def test_the_model_is_sent_the_output_and_none_of_what_is_kept_beside_it(deps_factory):
    deps = a_turn(deps_factory, [completion(tool_calls=[scripted()]), completion("Xong.")])
    conv = deps.store.create()

    await collect(run_turn(deps, conv.id, "đọc hai dòng"))

    _, after = sent(deps)
    assert after[-1] == "đọc xong"
    assert not any("received_chars" in text or "dòng 1" in text for text in after)
    assert tool_messages(deps, conv.id)[0].canvas_note == ""


async def test_a_later_turn_is_sent_no_note_in_front_of_a_script_result(deps_factory):
    """A canvas note older than the turn is read as a stub; what a script kept is no note."""
    script = [completion(tool_calls=[scripted()]), completion("Xong."), completion("Vẫn vậy.")]
    deps = a_turn(deps_factory, script)
    conv = deps.store.create()
    await collect(run_turn(deps, conv.id, "đọc hai dòng"))

    await collect(run_turn(deps, conv.id, "còn gì không"))

    later = sent(deps)[2]
    assert later[1:] == ["đọc hai dòng", "", "đọc xong", "Xong.", "còn gì không"]
    assert not any(CANVAS_NOTE_STUB in text or "received_chars" in text for text in later)


async def test_whichever_turn_reads_it_a_script_result_is_the_very_message_stored(deps_factory):
    deps = a_turn(deps_factory, [completion(tool_calls=[scripted()]), completion("Xong.")])
    conv = deps.store.create()
    await collect(run_turn(deps, conv.id, "đọc hai dòng"))
    history = deps.store.history(conv.id)
    messages = [stored.message for stored in history]
    assert [bool(stored.context) for stored in history] == [False, False, True, False]

    for turn_start in (None, history[0].seq, history[-1].seq + 1):
        attached = attach_canvas_notes(history, messages, turn_start)
        assert all(new is old for new, old in zip(attached, messages, strict=True))


async def test_a_script_that_called_nothing_keeps_its_measures_all_the_same(deps_factory):
    alone = scripted('print("xin chào")')
    deps = a_turn(deps_factory, [completion(tool_calls=[alone]), completion("Xong.")])
    conv = deps.store.create()

    await collect(run_turn(deps, conv.id, "chào"))

    [stored] = tool_messages(deps, conv.id)
    assert json.loads(stored.context) == {"calls": [], "received_chars": 0, "printed_chars": 8}


async def test_no_other_result_keeps_anything_beside_its_output(deps_factory):
    asked = [ToolCall("r1", "row_read", {"row": 3}), ToolCall("x1", "no_such_tool", {})]
    deps = a_turn(deps_factory, [completion(tool_calls=asked), completion("Xong.")])
    conv = deps.store.create()

    await collect(run_turn(deps, conv.id, "đọc dòng ba"))

    read, unknown = tool_messages(deps, conv.id)
    assert (read.message.content, read.context) == ("dòng 3", "")
    assert unknown.context == ""


def test_what_a_result_keeps_is_empty_unless_a_script_set_it():
    plain = ToolResultEvent("r1", "row_read", True, "dòng 3")
    counted = ToolResultEvent("p1", SCRIPT_TOOL, True, "x", received_chars=0, printed_chars=0)
    call = {"name": "row_read", "arguments": {}, "ok": False, "output": "hỏng", "ms": 4}
    listed = ToolResultEvent("p1", SCRIPT_TOOL, False, "x", calls=[call])

    assert plain.stored_context() == ""
    assert json.loads(counted.stored_context()) == {
        "calls": [],
        "received_chars": 0,
        "printed_chars": 0,
    }
    assert json.loads(listed.stored_context()) == {
        "calls": [call],
        "received_chars": None,
        "printed_chars": None,
    }


async def test_a_fork_copies_what_the_script_called(deps_factory):
    deps = a_turn(deps_factory, [completion(tool_calls=[scripted()]), completion("Xong.")])
    conv = deps.store.create()
    await collect(run_turn(deps, conv.id, "đọc hai dòng"))
    at = deps.store.append(conv.id, Message(role="user", content="đọc lại")).id

    fork, _ = deps.store.fork(conv.id, at, autonomous=False)

    [source] = tool_messages(deps, conv.id)
    [copied] = tool_messages(deps, fork.id)
    assert copied.context == source.context != ""


async def test_a_run_written_out_says_what_the_model_read_and_no_more(deps_factory):
    """The run's own steps list the calls; a message's `context` there is a canvas note."""
    deps = a_turn(deps_factory, [completion(tool_calls=[scripted()]), completion("Xong.")])
    hub = ActivityHub(deps.store)
    conv = deps.store.create()
    turn = tracked(hub, run_turn(deps, conv.id, "đọc hai dòng"), "default", "chat", "t", conv.id)
    await collect(turn)

    data = build(deps.store, deps.store.runs.latest_for_conversation(conv.id))

    [result] = [m for m in data["messages"] if m["role"] == "tool"]
    assert result["content"] == "đọc xong" and "context" not in result
    [step] = [s for s in data["run"]["steps"] if s.get("name") == SCRIPT_TOOL]
    assert [c["output"] for c in step["calls"]] == ["dòng 1", "dòng 2"]
