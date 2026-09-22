"""Approval deadlines and history, runtime job switches, and the usage ledger."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store import Store
from my_agent_crew.store.approvals import EXPIRED, PENDING

CALL = ToolCall("c1", "shell_run", {"command": "ls"})


def test_an_unanswered_approval_becomes_overdue_and_closes_as_expired(store: Store):
    conv = store.create()
    msg = store.append(conv.id, Message(role="assistant", content="", tool_calls=(CALL,)))
    approval = store.approvals.create(conv.id, msg.id, CALL, ttl_seconds=60)
    created = datetime.fromisoformat(approval.created_at)
    assert datetime.fromisoformat(approval.expires_at) == created + timedelta(seconds=60)
    assert store.approvals.overdue(created + timedelta(seconds=59)) == []
    assert [a.id for a in store.approvals.overdue(created + timedelta(seconds=60))] == [approval.id]

    expired = store.approvals.resolve(approval.id, approve=False, status=EXPIRED)
    assert expired.status == EXPIRED and expired.resolved_at is not None
    assert store.approvals.pending(conv.id) is None
    assert store.approvals.overdue(created + timedelta(days=1)) == []


def test_a_row_written_before_deadlines_existed_never_expires(store: Store):
    conv = store.create()
    store._conn.execute(
        "INSERT INTO approvals (id, conversation_id, message_id, tool_call_id, tool_name,"
        " arguments, status, created_at) VALUES ('old', ?, 1, 'c9', 't', '{}', ?, '2020-01-01')",
        (conv.id, PENDING),
    )
    assert store.approvals.overdue(datetime.now(UTC)) == []
    assert store.approvals.get("old").expires_at is None


def test_history_lists_decided_approvals_newest_first_and_skips_pending(store: Store):
    conv = store.create()
    msg = store.append(conv.id, Message(role="assistant", content=""))
    first = store.approvals.create(conv.id, msg.id, ToolCall("a", "t", {}))
    second = store.approvals.create(conv.id, msg.id, ToolCall("b", "t", {}))
    store.approvals.create(conv.id, msg.id, ToolCall("c", "t", {}))
    store.approvals.resolve(first.id, approve=True)
    store.approvals.resolve(second.id, approve=False)
    history = store.approvals.recent()
    assert [a.id for a in history] == [second.id, first.id]
    assert [a.status for a in history] == ["denied", "approved"]
    assert store.approvals.recent(limit=1)[0].id == second.id


def test_one_conversations_history_is_not_crowded_out_by_a_busier_one(store: Store):
    """The limit must count the conversation's own rows, or a quiet chat looks like it
    never asked for anything once other chats fill the page."""
    quiet = store.create()
    busy = store.create()
    for n, conv in enumerate((quiet, busy, busy, busy)):
        msg = store.append(conv.id, Message(role="assistant", content=""))
        approval = store.approvals.create(conv.id, msg.id, ToolCall(f"call{n}", "t", {}))
        store.approvals.resolve(approval.id, approve=True)

    history = store.approvals.recent(limit=2, conversation_id=quiet.id)

    assert [a.conversation_id for a in history] == [quiet.id]


def test_auto_approve_is_stored_as_a_list_and_defaults_empty(store: Store):
    conv = store.create()
    assert conv.auto_approve == () and conv.to_dict()["auto_approve"] == []
    updated = store.update(conv.id, auto_approve=("shell_run", "workspace_write"))
    assert updated.auto_approve == ("shell_run", "workspace_write")
    assert store.get(conv.id).to_dict()["auto_approve"] == ["shell_run", "workspace_write"]


def test_an_older_database_gains_the_new_columns(tmp_path: Path):
    import sqlite3

    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE approvals (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,"
        " message_id INTEGER NOT NULL, tool_call_id TEXT NOT NULL, tool_name TEXT NOT NULL,"
        " arguments TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);"
        "INSERT INTO approvals VALUES ('x', 'c', 1, 't1', 'tool', '{}', 'approved', '2020');"
    )
    conn.commit()
    conn.close()
    store = Store(path)
    old = store.approvals.get("x")
    assert old.expires_at is None and old.resolved_at is None
    conv = store.create()
    assert conv.auto_approve == ()
    msg = store.append(conv.id, Message(role="user", content="hi"))
    assert msg.prompt_tokens is None
    store.close()


def test_job_state_overrides_survive_reopen(tmp_path: Path):
    path = tmp_path / "jobs.sqlite3"
    store = Store(path)
    assert store.jobs.enabled("coach/brief") is None
    store.jobs.set_enabled("coach/brief", False, "2026-09-20T00:00:00+00:00")
    assert store.jobs.enabled("coach/brief") is False
    store.jobs.set_enabled("coach/brief", True, "2026-09-20T00:01:00+00:00")
    store.close()
    reopened = Store(path)
    assert reopened.jobs.enabled("coach/brief") is True
    assert reopened.jobs.enabled("coach/other") is None
    reopened.close()


@pytest.fixture
def ledger(store: Store) -> Store:
    conv = store.create()

    def call(stamp: str, model: str, cost: float | None, tokens: tuple[int, int]) -> None:
        store.messages.append(
            conv.id,
            Message(role="assistant", content="ok"),
            stamp,
            "openrouter",
            model,
            cost,
            *tokens,
        )

    call("2026-09-18T10:00:00+00:00", "m1", 0.10, (100, 20))
    call("2026-09-20T09:00:00+00:00", "m1", 0.05, (50, 10))
    call("2026-09-20T10:00:00+00:00", "m2", None, (30, 5))
    store.messages.append(conv.id, Message(role="user", content="hi"), "2026-09-20T11:00:00+00:00")
    store.append(conv.id, Message(role="tool", content="out", tool_call_id="c", name="t"))
    return store


def test_usage_by_day_fills_empty_days_and_counts_only_model_calls(ledger: Store):
    today = datetime(2026, 9, 20, 12, tzinfo=UTC)
    days = ledger.usage.by_day(3, today=today)
    assert [d["day"] for d in days] == ["2026-09-18", "2026-09-19", "2026-09-20"]
    assert days[0] == {
        "day": "2026-09-18",
        "calls": 1,
        "cost_usd": 0.10,
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "unknown_cost_calls": 0,
    }
    assert days[1]["calls"] == 0 and days[1]["cost_usd"] == 0.0
    assert days[2]["calls"] == 2 and days[2]["unknown_cost_calls"] == 1
    assert days[2]["prompt_tokens"] == 80 and days[2]["completion_tokens"] == 15
    assert days[2]["cost_usd"] == pytest.approx(0.05)


def test_usage_by_day_buckets_by_the_persons_zone_not_the_utc_stamp(ledger: Store):
    """A call at 18:30 UTC on the 18th is a call on the 19th in Vietnam."""
    from zoneinfo import ZoneInfo

    saigon = ZoneInfo("Asia/Ho_Chi_Minh")
    ledger.messages.append(
        ledger.list()[0].id,
        Message(role="assistant", content="ok"),
        "2026-09-18T18:30:00+00:00",
        "openrouter",
        "m1",
        0.02,
        10,
        2,
    )
    days = ledger.usage.by_day(3, today=datetime(2026, 9, 20, 12, tzinfo=UTC), zone=saigon)
    assert [d["day"] for d in days] == ["2026-09-18", "2026-09-19", "2026-09-20"]
    assert days[0]["calls"] == 1 and days[1]["calls"] == 1 and days[2]["calls"] == 2
    assert days[1]["cost_usd"] == pytest.approx(0.02)
    # Just before midnight UTC on the 20th is already the 21st in Vietnam: out of range.
    ledger.messages.append(
        ledger.list()[0].id,
        Message(role="assistant", content="ok"),
        "2026-09-20T23:30:00+00:00",
        "openrouter",
        "m1",
        0.5,
        1,
        1,
    )
    assert ledger.usage.by_day(3, today=datetime(2026, 9, 20, 12, tzinfo=UTC), zone=saigon) == days


def test_usage_by_model_sums_tokens_and_orders_by_spend(ledger: Store):
    models = ledger.usage.by_model()
    assert [m["model"] for m in models] == ["openrouter:m1", "openrouter:m2"]
    assert models[0]["calls"] == 2 and models[0]["cost_usd"] == pytest.approx(0.15)
    assert models[0]["prompt_tokens"] == 150 and models[0]["completion_tokens"] == 30
    assert models[1] == {
        "model": "openrouter:m2",
        "calls": 1,
        "cost_usd": 0.0,
        "prompt_tokens": 30,
        "completion_tokens": 5,
        "unknown_cost_calls": 1,
    }


def test_token_counts_round_trip_through_the_message_log(store: Store):
    conv = store.create()
    stored = store.append(
        conv.id,
        Message(role="assistant", content="x"),
        provider="p",
        model="m",
        cost_usd=0.01,
        prompt_tokens=12,
        completion_tokens=3,
    )
    assert (stored.prompt_tokens, stored.completion_tokens) == (12, 3)
    payload = store.history(conv.id)[0].to_dict()
    assert payload["prompt_tokens"] == 12 and payload["completion_tokens"] == 3
