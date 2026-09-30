"""`MessageStore.tool_results`: the tool messages a given call id produced, scoped to one
conversation. `tools/output_read.py` uses the row count to tell an ordinary single result
from a duplicate id it must refuse to guess between, rather than trust a bare id alone."""

from __future__ import annotations

from my_agent_crew.llm.types import Message
from my_agent_crew.store import Store


def _tool(call_id: str, content: str) -> Message:
    return Message(role="tool", content=content, tool_call_id=call_id, name="workspace_read")


def test_finds_the_one_tool_message_with_this_call_id() -> None:
    store = Store(":memory:")
    conv = store.create()
    store.append(conv.id, _tool("c1", "một"))

    rows = store.messages.tool_results(conv.id, "c1")

    assert [r.message.content for r in rows] == ["một"]


def test_an_unknown_call_id_finds_nothing() -> None:
    store = Store(":memory:")
    conv = store.create()
    store.append(conv.id, _tool("c1", "một"))

    assert store.messages.tool_results(conv.id, "c2") == []


def test_a_non_tool_message_with_the_same_id_field_is_never_returned() -> None:
    """Only role == 'tool' rows count; an assistant message happens to carry no
    tool_call_id of its own, but a mismatched role must not slip through regardless."""
    store = Store(":memory:")
    conv = store.create()
    store.append(conv.id, Message(role="user", content="c1"))

    assert store.messages.tool_results(conv.id, "c1") == []


def test_is_scoped_to_its_own_conversation() -> None:
    store = Store(":memory:")
    one, other = store.create(), store.create()
    store.append(one.id, _tool("c1", "của một"))
    store.append(other.id, _tool("c1", "của other"))

    rows = store.messages.tool_results(one.id, "c1")

    assert [r.message.content for r in rows] == ["của một"]


def test_a_reused_id_returns_every_row_in_seq_order_up_to_the_limit() -> None:
    """The id collided (see openai_compat's uuid fix and the approval-mismatch guard): both
    rows exist in the log, and the caller — not this method — decides that two rows means
    it cannot tell which one a bare id means."""
    store = Store(":memory:")
    conv = store.create()
    store.append(conv.id, _tool("c1", "đầu"))
    store.append(conv.id, _tool("c1", "sau"))

    rows = store.messages.tool_results(conv.id, "c1")

    assert [r.message.content for r in rows] == ["đầu", "sau"]


def test_the_limit_caps_how_many_rows_come_back() -> None:
    store = Store(":memory:")
    conv = store.create()
    store.append(conv.id, _tool("c1", "một"))
    store.append(conv.id, _tool("c1", "hai"))
    store.append(conv.id, _tool("c1", "ba"))

    rows = store.messages.tool_results(conv.id, "c1", limit=2)

    assert [r.message.content for r in rows] == ["một", "hai"]
