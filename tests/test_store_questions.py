"""Question rows: the agent asking the person something, stored beside tool approvals.

A question shares the approval table because it pauses a turn the same way and is answered
through the same endpoint. What it does not share is the approve/deny axis: the useful
outcome is the text that came back, so it closes as `answered` and carries that text.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store import Store
from my_agent_crew.store.approvals import ANSWERED, EXPIRED, PENDING
from my_agent_crew.store.models import QUESTION, TOOL

ASKING = ToolCall("q1", "ask_user", {"question": "Dời hạn sang thứ sáu?", "default": "không"})


def ask(store: Store, conv_id: str, options: list[str] | None = None, **kwargs):
    message = store.append(conv_id, Message(role="assistant", content="", tool_calls=(ASKING,)))
    return store.approvals.create(
        conv_id, message.id, ASKING, kind=QUESTION, options=options or [], **kwargs
    )


def test_a_question_keeps_what_was_asked_and_what_was_offered(store: Store):
    conv = store.create()
    approval = ask(store, conv.id, options=["có", "không"])
    assert approval.kind == QUESTION
    assert approval.options == ["có", "không"]
    assert approval.question == "Dời hạn sang thứ sáu?"
    assert approval.answer is None and approval.status == PENDING


def test_answering_closes_the_question_and_keeps_the_words(store: Store):
    conv = store.create()
    approval = ask(store, conv.id)
    answered = store.approvals.answer(approval.id, "có, dời sang thứ sáu")
    assert answered.status == ANSWERED
    assert answered.answer == "có, dời sang thứ sáu"
    assert answered.resolved_at is not None
    assert store.approvals.pending_question(conv.id) is None


def test_an_answered_question_cannot_be_answered_twice(store: Store):
    """Two people on two channels can reach the same question; the second must not
    overwrite the first, or the agent's answer changes after it already read it."""
    conv = store.create()
    approval = ask(store, conv.id)
    store.approvals.answer(approval.id, "đầu tiên")
    with pytest.raises(KeyError):
        store.approvals.answer(approval.id, "thứ hai")
    assert store.approvals.get(approval.id).answer == "đầu tiên"


def test_a_tool_approval_is_never_answerable_as_a_question(store: Store):
    """`answer` must not be a way to close a tool approval without deciding it: that would
    let a tool run, or not run, on the strength of a sentence."""
    conv = store.create()
    call = ToolCall("t1", "shell_run", {"command": "ls"})
    message = store.append(conv.id, Message(role="assistant", content="", tool_calls=(call,)))
    approval = store.approvals.create(conv.id, message.id, call)
    assert approval.kind == TOOL
    with pytest.raises(KeyError):
        store.approvals.answer(approval.id, "ừ chạy đi")
    assert store.approvals.get(approval.id).status == PENDING


def test_the_open_question_of_a_conversation_is_found_and_scoped_to_it(store: Store):
    """Telegram reads a plain message as an answer only while a question is waiting, so
    'is there one, and is it this conversation's' has to be a single honest lookup."""
    asking = store.create()
    quiet = store.create()
    approval = ask(store, asking.id)
    assert store.approvals.pending_question(asking.id).id == approval.id
    assert store.approvals.pending_question(quiet.id) is None


def test_a_pending_tool_approval_is_not_mistaken_for_an_open_question(store: Store):
    conv = store.create()
    call = ToolCall("t2", "shell_run", {"command": "ls"})
    message = store.append(conv.id, Message(role="assistant", content="", tool_calls=(call,)))
    store.approvals.create(conv.id, message.id, call)
    assert store.approvals.pending_question(conv.id) is None


def test_an_unanswered_question_goes_overdue_like_any_other_approval(store: Store):
    """A question asked by a night job must not hold the turn open until morning."""
    conv = store.create()
    approval = ask(store, conv.id, ttl_seconds=60)
    created = datetime.fromisoformat(approval.created_at)
    assert [a.id for a in store.approvals.overdue(created + timedelta(seconds=60))] == [approval.id]
    expired = store.approvals.resolve(approval.id, approve=False, status=EXPIRED)
    assert expired.status == EXPIRED and expired.answer is None


def test_questions_appear_in_history_with_their_answer(store: Store):
    conv = store.create()
    approval = ask(store, conv.id, options=["có", "không"])
    store.approvals.answer(approval.id, "có")
    row = store.approvals.recent(conversation_id=conv.id)[0]
    assert row.kind == QUESTION and row.answer == "có" and row.options == ["có", "không"]


def test_a_row_written_before_questions_existed_reads_as_a_tool(store: Store):
    """The migration adds the columns; rows already in the file must still load, and must
    not suddenly look like questions."""
    conv = store.create()
    store._conn.execute(
        "INSERT INTO approvals (id, conversation_id, message_id, tool_call_id, tool_name,"
        " arguments, status, created_at) VALUES ('old', ?, 1, 'c9', 'shell_run', '{}', ?, ?)",
        (conv.id, PENDING, datetime.now(UTC).isoformat()),
    )
    old = store.approvals.get("old")
    assert old.kind == TOOL and old.options == [] and old.answer is None
    assert store.approvals.pending_question(conv.id) is None
