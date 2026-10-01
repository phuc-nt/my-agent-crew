"""A tool call whose arguments are not a JSON object becomes a failed tool result, and the
turn carries on: the model reads where its JSON broke and sends the call again. It used to
end the whole run with a provider error, which a long document in the arguments made
likely. The broken text itself is never stored or sent back, only where it broke and the
few characters around that spot."""

from __future__ import annotations

import json
from typing import Any

from my_agent_crew import texts
from my_agent_crew.agent.events import ApprovalRequiredEvent, DoneEvent, ToolResultEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.openai_compat import ToolCallBuffer, to_wire
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store import Store
from my_agent_crew.tools.ask_user import ASK_USER_TOOL_NAME
from my_agent_crew.tools.registry import Tool, ToolResult
from tests.conftest import collect


def _parsed(raw: str, name: str = "artifact_create") -> ToolCall:
    buffer = ToolCallBuffer()
    buffer.feed([{"index": 0, "id": "c1", "function": {"name": name, "arguments": raw}}])
    [call] = buffer.calls()
    return call


def test_truncated_arguments_become_an_invalid_call_instead_of_an_error():
    raw = json.dumps({"title": "Kế hoạch", "content": "dòng\n" * 3000})[:-40]
    call = _parsed(raw)
    assert (call.id, call.name, call.arguments) == ("c1", "artifact_create", {})
    assert f"{len(raw)} chars" in call.invalid
    assert f"char {len(raw)}" in call.invalid
    assert raw[-20:].replace("\n", "\\n") in call.invalid


def test_the_detail_points_at_the_character_where_the_json_broke():
    raw = '{"content": "một\ndòng hai", "title": "x"}'
    call = _parsed(raw)
    broke_at = raw.index("\n")
    assert f"Invalid control character at char {broke_at}" in call.invalid
    # The raw line break is spelled out: shown as `\n` it would look like the fix.
    assert '"một<U+000A>dòng' in call.invalid
    assert len(call.invalid) < 200


def test_a_document_cut_off_inside_a_string_is_reported_where_it_stopped():
    """Python names where the unfinished string began, here char 26 of thousands."""
    raw = json.dumps({"title": "x", "content": "abc def " * 500})[:-7]
    call = _parsed(raw)
    assert f"cut off at char {len(raw)}" in call.invalid
    assert "char 26" not in call.invalid
    assert call.invalid.endswith(raw[-60:])


def test_a_bad_escape_near_the_end_is_not_mistaken_for_a_cut_off():
    raw = '{"a": "\\uZZZZ"}'
    assert "Invalid \\uXXXX escape at char 8" in _parsed(raw).invalid
    assert "cut off" not in _parsed(raw).invalid
    assert "cut off at char 12" in _parsed('{"a": "\\u00f').invalid


def test_json_that_is_not_an_object_is_named_by_its_type():
    assert "array" in _parsed('["a", "b"]').invalid
    assert "string" in _parsed('"{\\"title\\": \\"x\\"}"').invalid
    assert _parsed('["a"]').arguments == {}


def test_good_arguments_and_none_at_all_are_not_invalid():
    assert _parsed('{"title": "x"}') == ToolCall("c1", "artifact_create", {"title": "x"})
    assert _parsed("").invalid == ""
    assert _parsed("").arguments == {}


def test_the_wire_never_carries_the_invalid_detail():
    call = ToolCall("c1", "artifact_create", {}, invalid="12 chars; Expecting value at char 0")
    [item] = to_wire([Message(role="assistant", tool_calls=(call,))])
    assert item["tool_calls"] == [
        {"id": "c1", "type": "function", "function": {"name": "artifact_create", "arguments": "{}"}}
    ]


def test_an_invalid_call_round_trips_through_the_store_and_old_rows_still_load(store: Store):
    conv = store.create()
    broken = ToolCall("c1", "artifact_create", {}, invalid="9 chars; Expecting value at char 0")
    store.append(conv.id, Message(role="assistant", tool_calls=(broken, ToolCall("c2", "x", {}))))
    [stored] = store.history(conv.id)
    assert stored.message.tool_calls == (broken, ToolCall("c2", "x", {}))
    # An ordinary call keeps the row shape it always had, so a server rolled back past
    # this field still reads every conversation that never had a broken call.
    [row] = store._conn.execute("SELECT tool_calls FROM messages WHERE id = ?", (stored.id,))
    assert json.loads(row[0])[1] == {"id": "c2", "name": "x", "arguments": {}}
    assert stored.to_dict()["tool_calls"][1] == {"id": "c2", "name": "x", "arguments": {}}

    store._conn.execute(
        "UPDATE messages SET tool_calls = ? WHERE id = ?",
        (json.dumps([{"id": "c3", "name": "x", "arguments": {"a": 1}}]), stored.id),
    )
    store._conn.commit()
    [old] = store.history(conv.id)
    assert old.message.tool_calls == (ToolCall("c3", "x", {"a": 1}),)


class _Recorder:
    """A tool that only counts its runs, gated for approval when asked to be."""

    def __init__(self, name: str, requires_approval: bool = False):
        self.runs: list[dict[str, Any]] = []
        schema = {"type": "object", "properties": {"path": {"type": "string"}}}
        self.tool = Tool(name, "Ghi.", schema, self._run, requires_approval)

    async def _run(self, args: dict[str, Any]) -> ToolResult:
        self.runs.append(args)
        return ToolResult(ok=True, output="đã ghi")


BROKEN = "40 chars; Unterminated string starting at char 12"


async def test_an_invalid_call_fails_without_running_and_the_turn_carries_on(deps_factory):
    recorder = _Recorder("note")
    broken = ToolCall("c1", "note", {}, invalid=BROKEN)
    provider = ScriptedProvider([completion(tool_calls=[broken]), completion("đã sửa xong")])
    deps = deps_factory(providers={"scripted": provider}, extra_tools=[recorder.tool])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "ghi giúp tôi"))

    [result] = [e for e in events if isinstance(e, ToolResultEvent)]
    assert (result.tool_call_id, result.ok) == ("c1", False)
    assert result.output == texts.TOOL_ARGS_INVALID.format(name="note", detail=BROKEN)
    assert recorder.runs == []
    assert isinstance(events[-1], DoneEvent)
    assert deps.store.history(conv.id)[-1].message.content == "đã sửa xong"
    second = provider.requests[1]
    assert second.messages[-1].content == result.output


async def test_an_invalid_call_to_a_gated_tool_asks_nobody(deps_factory):
    """Asking a person to approve a call with no arguments would show them nothing to
    decide on, and approving it could still run nothing."""
    recorder = _Recorder("write", requires_approval=True)
    ask = ToolCall("q1", ASK_USER_TOOL_NAME, {}, invalid=BROKEN)
    write = ToolCall("c1", "write", {}, invalid=BROKEN)
    script = [completion(tool_calls=[ask, write]), completion("thôi")]
    deps = deps_factory(script=script, extra_tools=[recorder.tool])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "ghi giúp tôi"))

    assert not [e for e in events if isinstance(e, ApprovalRequiredEvent)]
    assert deps.store.approvals.find_for_call(conv.id, "q1") is None
    assert deps.store.approvals.find_for_call(conv.id, "c1") is None
    results = [(e.tool_call_id, e.ok) for e in events if isinstance(e, ToolResultEvent)]
    assert results == [("q1", False), ("c1", False)]
    assert recorder.runs == []
    assert isinstance(events[-1], DoneEvent)
