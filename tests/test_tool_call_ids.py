"""A provider that omits a tool call's id must not hand out the same one twice: two calls,
two messages or two streams that all come back bare would otherwise collide wherever a
call id is used as a lookup key, such as finding a delegated child by its parent's call."""

from __future__ import annotations

from my_agent_crew.llm.openai_compat import ToolCallBuffer


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
