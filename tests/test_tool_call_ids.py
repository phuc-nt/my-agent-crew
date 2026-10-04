"""A provider that omits a tool call's id must not hand out the same one twice: two calls,
two messages or two streams that all come back bare would otherwise collide wherever a
call id is used as a lookup key, such as finding a delegated child by its parent's call.

The buffer also hands back each piece of arguments as it takes it in, named with what it has
assembled of that call so far, so a reader can follow a call that is still being written."""

from __future__ import annotations

from my_agent_crew.llm.tool_call_buffer import ToolCallBuffer
from my_agent_crew.llm.types import ToolCall, ToolCallDelta


def _delta(index: int, name: str = "delegate", args: str = "{}") -> dict:
    return {"index": index, "function": {"name": name, "arguments": args}}


def test_a_call_with_no_id_still_gets_one() -> None:
    buffer = ToolCallBuffer()
    buffer.feed([_delta(0)])

    [call] = buffer.calls()

    assert call.id


def test_two_bare_calls_in_the_same_message_get_different_ids() -> None:
    buffer = ToolCallBuffer()
    buffer.feed([_delta(0, name="delegate"), _delta(1, name="delegate")])

    first, second = buffer.calls()

    assert first.id != second.id


def test_two_bare_calls_in_different_messages_get_different_ids() -> None:
    one = ToolCallBuffer()
    one.feed([_delta(0)])
    other = ToolCallBuffer()
    other.feed([_delta(0)])

    [first] = one.calls()
    [second] = other.calls()

    assert first.id != second.id


def test_two_bare_calls_in_different_streams_get_different_ids() -> None:
    """Same shape as two messages, named separately because this is the scenario the fix
    exists for: two conversations, each streaming its own reply, both providers silent
    about the id, must never end up naming each other's call."""
    stream_one = ToolCallBuffer()
    stream_one.feed([_delta(0)])
    stream_two = ToolCallBuffer()
    stream_two.feed([_delta(0)])

    [call_one] = stream_one.calls()
    [call_two] = stream_two.calls()

    assert call_one.id != call_two.id


def test_a_call_with_its_own_id_keeps_it() -> None:
    buffer = ToolCallBuffer()
    buffer.feed([{"index": 0, "id": "call_abc", "function": {"name": "delegate", "args": "{}"}}])

    [call] = buffer.calls()

    assert call.id == "call_abc"


def test_each_piece_of_arguments_comes_back_named_with_the_call_it_belongs_to() -> None:
    """The name arrives once, in the first delta; a later piece of the same call still says
    which tool is being written, and the call assembled at the end is what it always was."""
    buffer = ToolCallBuffer()
    opening = {"index": 0, "id": "c1", "function": {"name": "artifact_create", "arguments": '{"ti'}}

    first = buffer.feed([opening])
    later = buffer.feed([{"index": 0, "function": {"arguments": 'tle": "A"}'}}])

    assert first == [ToolCallDelta(index=0, name="artifact_create", chunk='{"ti')]
    assert later == [ToolCallDelta(index=0, name="artifact_create", chunk='tle": "A"}')]
    assert buffer.calls() == (ToolCall("c1", "artifact_create", {"title": "A"}),)


def test_a_delta_that_brings_no_arguments_is_not_a_piece() -> None:
    buffer = ToolCallBuffer()

    assert buffer.feed([{"index": 0, "id": "c1", "function": {"name": "artifact_create"}}]) == []
    assert buffer.feed([{"index": 0, "function": {"arguments": ""}}]) == []
    assert buffer.feed([{"index": 0, "function": {"arguments": None}}]) == []
    assert buffer.feed([{"index": 0}]) == []
    assert buffer.feed([]) == []

    # The name those deltas brought is not lost: the first real piece carries it.
    assert buffer.feed([{"index": 0, "function": {"arguments": "{}"}}]) == [
        ToolCallDelta(index=0, name="artifact_create", chunk="{}")
    ]


def test_arguments_sent_ahead_of_the_name_come_back_with_no_name_yet() -> None:
    buffer = ToolCallBuffer()

    early = buffer.feed([{"index": 0, "function": {"arguments": '{"a"'}}])
    named = buffer.feed(
        [{"index": 0, "function": {"name": "artifact_create", "arguments": ": 1}"}}]
    )

    assert early == [ToolCallDelta(index=0, name="", chunk='{"a"')]
    assert named == [ToolCallDelta(index=0, name="artifact_create", chunk=": 1}")]


def test_pieces_of_two_calls_keep_their_own_index_and_name_in_the_order_they_came() -> None:
    buffer = ToolCallBuffer()

    opened = buffer.feed(
        [
            _delta(0, name="artifact_create", args='{"a"'),
            _delta(1, name="workspace_write", args='{"b"'),
        ]
    )
    closed = buffer.feed(
        [
            {"index": 1, "function": {"arguments": ": 2}"}},
            {"index": 0, "function": {"arguments": ": 1}"}},
        ]
    )

    assert opened == [
        ToolCallDelta(index=0, name="artifact_create", chunk='{"a"'),
        ToolCallDelta(index=1, name="workspace_write", chunk='{"b"'),
    ]
    assert closed == [
        ToolCallDelta(index=1, name="workspace_write", chunk=": 2}"),
        ToolCallDelta(index=0, name="artifact_create", chunk=": 1}"),
    ]
    assert [(call.name, call.arguments) for call in buffer.calls()] == [
        ("artifact_create", {"a": 1}),
        ("workspace_write", {"b": 2}),
    ]


def test_a_delta_that_states_no_index_is_a_piece_of_the_first_call() -> None:
    buffer = ToolCallBuffer()

    pieces = buffer.feed([{"function": {"name": "artifact_create", "arguments": "{}"}}])

    assert pieces == [ToolCallDelta(index=0, name="artifact_create", chunk="{}")]
