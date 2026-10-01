"""`Store.fork`: copying every message before a cut into a new conversation."""

from __future__ import annotations

import sqlite3

import pytest

from my_agent_crew import texts
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store import Store

CALL_A, CALL_B = ToolCall("a1", "slow", {}), ToolCall("b1", "slow", {})


def user(text: str) -> Message:
    return Message(role="user", content=text)


def assistant(text: str = "", *, tool_calls: tuple[ToolCall, ...] = ()) -> Message:
    return Message(role="assistant", content=text, tool_calls=tool_calls)


def tool(call: ToolCall, output: str = "xong") -> Message:
    return Message(role="tool", content=output, tool_call_id=call.id, name=call.name)


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


# --- copying the log -------------------------------------------------------------------


def test_copies_every_message_before_the_cut_with_its_columns(store: Store) -> None:
    conv = store.create()
    store.append(conv.id, user("một"))
    store.append(conv.id, assistant("trả lời một"))
    cut = store.append(conv.id, user("hai")).id
    store.append(conv.id, assistant("trả lời hai"))  # after the cut, never copied

    fork, draft = store.fork(conv.id, cut, autonomous=False)

    history = store.history(fork.id)
    assert draft == "hai"
    assert [(m.message.role, m.message.content) for m in history] == [
        ("user", "một"),
        ("assistant", "trả lời một"),
    ]
    assert [m.seq for m in history] == [1, 2]
    original = store.history(conv.id)[:2]
    for copy, source in zip(history, original, strict=True):
        assert copy.message.tool_calls == source.message.tool_calls
        assert copy.message.tool_call_id == source.message.tool_call_id
        assert copy.message.name == source.message.name
        assert copy.model == source.model
        assert copy.created_at == source.created_at


def test_only_the_source_conversations_own_messages_are_copied(store: Store) -> None:
    other = store.create()
    store.append(other.id, user("của hội thoại khác"))
    store.append(other.id, user("vẫn của hội thoại khác"))
    conv = store.create()
    store.append(conv.id, user("một"))
    cut = store.append(conv.id, user("hai")).id

    fork, _ = store.fork(conv.id, cut, autonomous=False)

    assert [m.message.content for m in store.history(fork.id)] == ["một"]


def test_cutting_at_the_first_user_message_makes_an_empty_fork_with_the_right_draft(
    store: Store,
) -> None:
    conv = store.create()
    cut = store.append(conv.id, user("chào")).id
    store.append(conv.id, assistant("chào bạn"))

    fork, draft = store.fork(conv.id, cut, autonomous=False)

    assert store.history(fork.id) == []
    assert draft == "chào"


def test_tool_calls_and_tool_messages_survive_the_copy(store: Store) -> None:
    conv = store.create()
    store.append(conv.id, user("làm đi"))
    store.append(conv.id, assistant(tool_calls=(CALL_A,)))
    store.append(conv.id, tool(CALL_A, "kết quả A"))
    cut = store.append(conv.id, user("tiếp")).id

    fork, _ = store.fork(conv.id, cut, autonomous=False)

    roles = [(m.message.role, m.message.tool_call_id) for m in store.history(fork.id)]
    assert roles == [("user", None), ("assistant", None), ("tool", "a1")]


# --- billing columns are not inherited ---------------------------------------------------


def test_provider_cost_and_token_columns_are_null_on_the_copy(store: Store) -> None:
    conv = store.create()
    store.append(conv.id, user("hỏi"))
    store.append(
        conv.id,
        assistant("trả lời"),
        provider="scripted",
        model="m",
        cost_usd=0.01,
        prompt_tokens=10,
        completion_tokens=5,
        reasoning_tokens=1,
        cached_tokens=2,
    )
    cut = store.append(conv.id, user("nữa")).id

    fork, _ = store.fork(conv.id, cut, autonomous=False)

    [copied] = [m for m in store.history(fork.id) if m.message.role == "assistant"]
    assert copied.provider is None
    assert copied.cost_usd is None
    assert (copied.prompt_tokens, copied.completion_tokens) == (None, None)
    assert (copied.reasoning_tokens, copied.cached_tokens) == (None, None)
    assert copied.model == "m"  # the label survives; only billing does not


def test_the_fork_has_zero_spend_and_zero_unknown_cost_calls(store: Store) -> None:
    conv = store.create()
    store.append(conv.id, user("hỏi"))
    store.append(conv.id, assistant("trả lời"), provider="scripted", model="m", cost_usd=0.02)
    store.add_spend(conv.id, 0.02)
    cut = store.append(conv.id, user("nữa")).id

    fork, _ = store.fork(conv.id, cut, autonomous=False)

    assert (fork.spent_usd, fork.unknown_cost_calls) == (0, 0)


def test_usage_totals_are_identical_before_and_after_forking(store: Store) -> None:
    conv = store.create()
    store.append(conv.id, user("hỏi"))
    store.append(conv.id, assistant("trả lời"), provider="scripted", model="m", cost_usd=0.05)
    store.add_spend(conv.id, 0.05)
    cut = store.append(conv.id, user("nữa")).id
    before = (store.usage.by_model(), store.usage.by_purpose(), store.usage.by_day())

    store.fork(conv.id, cut, autonomous=False)

    after = (store.usage.by_model(), store.usage.by_purpose(), store.usage.by_day())
    assert before == after


# --- configuration -----------------------------------------------------------------------


def test_agent_id_cost_cap_and_skills_are_copied_others_are_reset(store: Store) -> None:
    conv = store.create(
        agent_id="coach",
        cost_cap_usd=1.5,
        skills=("planning",),
        autonomous=True,
        channel="telegram:123",
    )
    conv = store.update(conv.id, auto_approve=("shell",))
    cut = store.append(conv.id, user("hỏi")).id

    fork, _ = store.fork(conv.id, cut, autonomous=False)

    assert (fork.agent_id, fork.cost_cap_usd, fork.skills) == ("coach", 1.5, ("planning",))
    assert (fork.channel, fork.parent_call_id, fork.summary) == ("", "", "")
    assert fork.forked_from == conv.id
    assert (fork.autonomous, fork.auto_approve) == (False, ())


def test_autonomous_follows_the_agent_default_not_the_source(store: Store) -> None:
    conv = store.create(autonomous=True)
    conv = store.update(conv.id, auto_approve=("shell",))
    cut = store.append(conv.id, user("hỏi")).id

    off, _ = store.fork(conv.id, cut, autonomous=False)
    on, _ = store.fork(conv.id, cut, autonomous=True)

    assert (off.autonomous, off.auto_approve) == (False, ())
    assert (on.autonomous, on.auto_approve) == (True, ())


# --- title ---------------------------------------------------------------------------


def test_the_suffix_is_added_once_and_not_doubled_on_a_fork_of_a_fork(store: Store) -> None:
    conv = store.create()
    conv = store.update(conv.id, title="Kế hoạch tuần")
    store.append(conv.id, user("một"))
    cut = store.append(conv.id, user("hỏi")).id

    fork, _ = store.fork(conv.id, cut, autonomous=False)
    assert fork.title == "Kế hoạch tuần (nhánh)"

    grandchild_cut = store.append(fork.id, user("hỏi tiếp")).id
    fork2, _ = store.fork(fork.id, grandchild_cut, autonomous=False)
    assert fork2.title == "Kế hoạch tuần (nhánh)"


def test_a_default_titled_source_stays_default_on_the_fork(store: Store) -> None:
    conv = store.create()
    assert conv.title == texts.CONVERSATION_TITLE_DEFAULT
    cut = store.append(conv.id, user("hỏi")).id

    fork, _ = store.fork(conv.id, cut, autonomous=False)

    assert fork.title == texts.CONVERSATION_TITLE_DEFAULT


# --- errors --------------------------------------------------------------------------


def test_cutting_at_an_assistant_or_tool_message_is_a_value_error(store: Store) -> None:
    conv = store.create()
    store.append(conv.id, user("hỏi"))
    assistant_id = store.append(conv.id, assistant("trả lời")).id
    tool_id = store.append(conv.id, tool(CALL_A)).id

    for message_id in (assistant_id, tool_id):
        with pytest.raises(ValueError):
            store.fork(conv.id, message_id, autonomous=False)


def test_a_message_of_another_conversation_is_a_key_error(store: Store) -> None:
    conv_a, conv_b = store.create(), store.create()
    other_message = store.append(conv_b.id, user("của hội thoại khác")).id

    with pytest.raises(KeyError):
        store.fork(conv_a.id, other_message, autonomous=False)


def test_an_unknown_message_id_is_a_key_error(store: Store) -> None:
    conv = store.create()
    store.append(conv.id, user("hỏi"))

    with pytest.raises(KeyError):
        store.fork(conv.id, 999999, autonomous=False)


def test_an_unknown_conversation_is_a_key_error(store: Store) -> None:
    with pytest.raises(KeyError):
        store.fork("khong-ton-tai", 1, autonomous=False)


def test_a_delegated_child_conversation_cannot_be_forked(store: Store) -> None:
    child = store.create(parent_call_id="call-1")
    cut = store.append(child.id, user("chào")).id

    with pytest.raises(ValueError):
        store.fork(child.id, cut, autonomous=False)


# --- the source is left untouched -----------------------------------------------------


def test_the_source_conversation_is_unchanged_after_forking(store: Store) -> None:
    conv = store.create()
    store.append(conv.id, user("một"))
    store.append(conv.id, assistant("trả lời"), provider="scripted", model="m", cost_usd=0.01)
    store.add_spend(conv.id, 0.01)
    cut = store.append(conv.id, user("hai")).id
    before_messages = store.history(conv.id)
    before = store.get(conv.id)

    store.fork(conv.id, cut, autonomous=False)

    after = store.get(conv.id)
    assert store.history(conv.id) == before_messages
    assert (after.updated_at, after.spent_usd) == (before.updated_at, before.spent_usd)


def test_a_pending_approval_on_the_source_survives_forking_at_an_earlier_point(
    store: Store,
) -> None:
    conv = store.create()
    store.append(conv.id, user("một"))
    cut = store.append(conv.id, user("hai")).id
    message_id = store.append(conv.id, assistant(tool_calls=(CALL_A,))).id
    approval = store.approvals.create(conv.id, message_id, CALL_A)

    store.fork(conv.id, cut, autonomous=False)

    assert store.approvals.get(approval.id).status == "pending"
    assert store.approvals.pending(conv.id) is not None


# --- a Telegram source ------------------------------------------------------------------


def test_forking_a_telegram_conversation_makes_a_web_fork_and_keeps_the_channel(
    store: Store,
) -> None:
    conv = store.create(channel="telegram:42")
    cut = store.append(conv.id, user("chào")).id

    fork, _ = store.fork(conv.id, cut, autonomous=False)

    assert fork.channel == ""
    latest = store.latest_for_channel(conv.agent_id, "telegram:42")
    assert latest is not None and latest.id == conv.id


# --- open tool calls at the cut ---------------------------------------------------------


def test_an_open_call_is_copied_still_open_ready_for_the_route_to_close_it(store: Store) -> None:
    """`Store.fork` copies history as-is; closing an open call is the route's job
    (`refuse_unanswered`), tested in `tests/test_api_fork.py`. This proves the raw copy
    ends on `tool(A)` with `B` left without a result, matching the key insight that a turn
    can be interrupted between two calls of one assistant message and resumed by a user
    message: `[assistant(A,B), tool(A), user]`."""
    conv = store.create()
    store.append(conv.id, user("một"))
    assistant_id = store.append(conv.id, assistant(tool_calls=(CALL_A, CALL_B))).id
    store.append(conv.id, tool(CALL_A, "kết quả A"))
    cut = store.append(conv.id, user("hai")).id

    fork, _ = store.fork(conv.id, cut, autonomous=False)

    history = store.history(fork.id)
    assert [m.message.role for m in history] == ["user", "assistant", "tool"]
    assert history[-1].message.tool_call_id == "a1"
    [copied_assistant] = [m for m in history if m.message.role == "assistant"]
    assert {c.id for c in copied_assistant.message.tool_calls} == {"a1", "b1"}
    assert assistant_id  # the source row exists; the copy is a new row with its own id


# --- atomicity ---------------------------------------------------------------------------


class _ConnectionProxy:
    """Delegates to a real connection, except that the one statement `blocks` starts with
    always fails. `sqlite3.Connection.execute` is a slot of a C type and cannot be patched
    on the instance or the class, so this stands in for it instead."""

    def __init__(self, real: sqlite3.Connection, blocks: str):
        self._real = real
        self._blocks = blocks

    def execute(self, sql: str, *args: object) -> sqlite3.Cursor:
        if sql.strip().startswith(self._blocks):
            raise sqlite3.OperationalError("chép hỏng")
        return self._real.execute(sql, *args)

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)


def _rows(store: Store) -> tuple[int, int]:
    """How many messages and canvas links the store holds in all."""
    count = "SELECT (SELECT COUNT(*) FROM messages), (SELECT COUNT(*) FROM conversation_artifacts)"
    return tuple(store._conn.execute(count).fetchone())


@pytest.mark.parametrize("blocks", ["INSERT INTO messages", "INSERT INTO conversation_artifacts"])
def test_a_failed_copy_leaves_no_fork_behind(
    store: Store, monkeypatch: pytest.MonkeyPatch, blocks: str
) -> None:
    """Copying the messages or the canvas links failing takes the fork and every row already
    copied into it away."""
    conv = store.create()
    store.append(conv.id, user("một"))
    cut = store.append(conv.id, user("hỏi")).id
    art = store.artifacts.create("Kế hoạch", "markdown", "", "user", "", "# Kế hoạch\n").id
    store.artifact_links.link(conv.id, art)
    before_ids, before_rows = {c.id for c in store.list()}, _rows(store)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_conn", _ConnectionProxy(store._conn, blocks))
        with pytest.raises(sqlite3.OperationalError):
            store.fork(conv.id, cut, autonomous=False)

    assert {c.id for c in store.list()} == before_ids
    assert _rows(store) == before_rows


# --- recap ---------------------------------------------------------------------------


def test_forked_from_marks_the_conversation_so_the_recap_can_be_skipped(store: Store) -> None:
    conv = store.create()
    store.update(conv.id, summary="tóm tắt gốc")
    cut = store.append(conv.id, user("hỏi")).id

    fork, _ = store.fork(conv.id, cut, autonomous=False)
    plain_after = store.create()  # opened after the fork, on the same channel

    assert fork.forked_from == conv.id
    previous_for_fork = store.previous_for_channel(fork.agent_id, fork.channel, fork.id)
    assert previous_for_fork is not None and previous_for_fork.id == conv.id
    previous_for_plain = store.previous_for_channel(
        plain_after.agent_id, plain_after.channel, plain_after.id
    )
    assert previous_for_plain is not None and previous_for_plain.id == fork.id


# --- deleting the source or the fork -----------------------------------------------------


def test_deleting_the_source_clears_forked_from_and_the_fork_keeps_its_messages(
    store: Store,
) -> None:
    conv = store.create()
    store.append(conv.id, user("một"))
    cut = store.append(conv.id, user("hai")).id
    fork, _ = store.fork(conv.id, cut, autonomous=False)

    store.delete(conv.id)

    assert store.get(fork.id).forked_from == ""
    assert len(store.history(fork.id)) == 1


def test_deleting_the_fork_does_not_touch_the_sources_delegate_children(store: Store) -> None:
    conv = store.create()
    cut = store.append(conv.id, user("hỏi")).id
    store.append(conv.id, assistant(tool_calls=(ToolCall("d1", "delegate", {}),)))
    child = store.create(parent_call_id="d1")
    fork, _ = store.fork(conv.id, cut, autonomous=False)

    store.delete(fork.id)

    assert store.get(child.id) is not None
    assert store.for_parent_call("d1") is not None


# --- search index ----------------------------------------------------------------------


def test_a_shared_line_finds_a_single_hit_belonging_to_the_fork(store: Store) -> None:
    conv = store.create()
    store.append(conv.id, user("câu chung trước điểm cắt"))
    cut = store.append(conv.id, user("tiếp tục")).id

    fork, _ = store.fork(conv.id, cut, autonomous=False)

    hits = store.search.find("câu chung trước điểm cắt")
    assert len(hits) == 1
    assert hits[0].conversation_id == fork.id
