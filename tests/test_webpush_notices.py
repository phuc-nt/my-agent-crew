"""Which messages of the activity stream wake a phone, and that what it shows says nothing
of the work itself."""

from __future__ import annotations

from typing import Any

import pytest

from my_agent_crew import texts_push
from my_agent_crew.store.db import Store
from my_agent_crew.webpush.notices import INBOX_URL, LONG_TURN_SECONDS, notice_for

START = "2026-11-01T08:00:00+00:00"
LATE = "2026-11-01T08:05:00+00:00"
SOON = "2026-11-01T08:00:10+00:00"


def run(**fields: Any) -> dict[str, Any]:
    base = {
        "id": "r1",
        "agent_id": "default",
        "conversation_id": "c1",
        "source": "job:brief",
        "title": "Bản tin",
        "status": "done",
        "started_at": START,
        "finished_at": LATE,
        "summary": "Hôm nay có 3 cuộc họp.",
    }
    return {"type": "run", "run": base | fields}


def request(kind: str = "tool") -> dict[str, Any]:
    event = {
        "type": "approval_required",
        "approval_id": "ap1",
        "name": "send_email",
        "arguments": {"to": "someone"},
        "kind": kind,
    }
    return {
        "type": "event",
        "run_id": "r1",
        "conversation_id": "c1",
        "status": "awaiting_approval",
        "event": event,
    }


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


def test_a_request_to_allow_and_a_question_each_open_the_inbox(store):
    tool = notice_for(request(), store)
    question = notice_for(request("question"), store)
    assert (tool.title, tool.url, tool.tag) == (texts_push.APPROVAL_TITLE, INBOX_URL, "request")
    assert question.title == texts_push.QUESTION_TITLE


def test_a_notice_carries_none_of_the_work(store):
    payload = request()
    shown = " ".join(notice_for(payload, store).payload().values())
    assert "send_email" not in shown and "someone" not in shown
    shown = " ".join(notice_for(run(), store).payload().values())
    assert "Bản tin" not in shown and "cuộc họp" not in shown


def test_a_job_that_reported_or_failed_is_told(store):
    assert notice_for(run(), store).title == texts_push.JOB_RESULT_TITLE
    failed = notice_for(run(status="error", conversation_id=None), store)
    assert failed.title == texts_push.JOB_FAILED_TITLE


@pytest.mark.parametrize("summary", ["OK", "ok.", " OK! ", ""])
def test_a_job_with_nothing_to_report_is_not(store, summary):
    assert notice_for(run(summary=summary), store) is None


def test_a_job_that_went_well_without_a_turn_is_not(store):
    """A command's output is its summary, and no answer: the chat is not sent it either."""
    assert notice_for(run(conversation_id=None, summary="synced 0"), store) is None


def test_a_run_still_going_or_another_message_is_not(store):
    assert notice_for(run(status="running", finished_at=None), store) is None
    assert notice_for(run(status="awaiting_approval"), store) is None
    assert notice_for({"type": "snapshot", "runs": []}, store) is None
    other = request() | {"event": {"type": "tool_result"}}
    assert notice_for(other, store) is None


def test_a_long_turn_on_the_web_is_told_where_its_answer_is(store):
    conv = store.create()
    notice = notice_for(run(source="web", conversation_id=conv.id), store)
    assert notice.title == texts_push.REPLY_TITLE
    assert notice.url == f"/#/chat/{conv.id}"


def test_a_short_turn_was_watched_and_is_not(store):
    conv = store.create()
    assert LONG_TURN_SECONDS > 10
    assert notice_for(run(source="web", conversation_id=conv.id, finished_at=SOON), store) is None


def test_a_telegram_chat_or_a_delegated_child_is_not_pushed_its_answer(store):
    chat = store.create(channel="telegram:1")
    parent = store.create()
    child = store.create(parent_call_id="call1", root_id=parent.id)
    for conv in (chat, child):
        assert notice_for(run(source="web", conversation_id=conv.id), store) is None
    assert notice_for(run(source="web", conversation_id="gone"), store) is None
    assert notice_for(run(source="web", conversation_id=parent.id, status="error"), store) is None
