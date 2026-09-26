from pathlib import Path

import pytest

from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store import Store
from my_agent_crew.store.models import AWAITING_APPROVAL


def test_create_get_list_update_delete(store: Store):
    a = store.create(title="A")
    b = store.create(title="B", autonomous=True, cost_cap_usd=1.0, skills=("x",))
    assert [c.id for c in store.list()] == [b.id, a.id]
    assert b.autonomous and b.skills == ("x",)
    updated = store.update(a.id, title="A2", status=AWAITING_APPROVAL)
    assert (updated.title, updated.status) == ("A2", AWAITING_APPROVAL)
    store.delete(a.id)
    with pytest.raises(KeyError):
        store.get(a.id)


def test_update_rejects_non_mutable_fields(store: Store):
    conv = store.create()
    with pytest.raises(ValueError):
        store.update(conv.id, spent_usd=99)


def test_messages_keep_order_and_tool_calls(store: Store):
    conv = store.create()
    store.append(conv.id, Message(role="user", content="hi"))
    call = ToolCall("c1", "workspace_read", {"path": "a"})
    store.append(conv.id, Message(role="assistant", tool_calls=(call,)), provider="p", model="m")
    reply = Message(role="tool", content="x", tool_call_id="c1", name="workspace_read")
    store.append(conv.id, reply)
    history = store.history(conv.id)
    assert [m.seq for m in history] == [1, 2, 3]
    assert history[1].message.tool_calls == (call,)
    assert history[1].provider == "p"
    assert history[2].message.tool_call_id == "c1"
    assert history[1].to_dict()["tool_calls"][0]["arguments"] == {"path": "a"}


def test_spend_tracks_known_and_unknown_cost_separately(store: Store):
    conv = store.create(cost_cap_usd=0.01)
    store.add_spend(conv.id, 0.004)
    store.add_spend(conv.id, None)
    conv = store.add_spend(conv.id, 0.006)
    assert conv.spent_usd == pytest.approx(0.01)
    assert conv.unknown_cost_calls == 1
    assert conv.over_budget


def test_zero_cap_means_unlimited(store: Store):
    conv = store.create(cost_cap_usd=0)
    conv = store.add_spend(conv.id, 100)
    assert not conv.over_budget


def test_approvals_lifecycle(store: Store):
    conv = store.create()
    msg = store.append(conv.id, Message(role="assistant", tool_calls=(ToolCall("c1", "t", {}),)))
    approval = store.approvals.create(conv.id, msg.id, ToolCall("c1", "t", {"k": 1}))
    assert store.approvals.pending(conv.id).id == approval.id
    assert store.approvals.find_for_call(conv.id, "c1").arguments == {"k": 1}
    resolved = store.approvals.resolve(approval.id, approve=False)
    assert resolved.status == "denied"
    assert store.approvals.pending(conv.id) is None
    with pytest.raises(KeyError):
        store.approvals.resolve(approval.id, approve=True)


def test_data_persists_on_disk(tmp_path: Path):
    path = tmp_path / "db.sqlite3"
    first = Store(path)
    conv = first.create(title="kept")
    first.append(conv.id, Message(role="user", content="hello"))
    first.close()
    second = Store(path)
    assert second.get(conv.id).title == "kept"
    assert second.history(conv.id)[0].message.content == "hello"


def test_conversations_carry_an_agent_id_and_filter_by_it(store: Store):
    a = store.create(agent_id="coach")
    b = store.create()
    assert store.get(a.id).agent_id == "coach" and b.agent_id == "default"
    assert [c.id for c in store.list("coach")] == [a.id]
    assert [c.id for c in store.list()] == [b.id, a.id]
    assert a.to_dict()["agent_id"] == "coach"


def test_runs_store_round_trips_steps_and_marks_interrupted(store: Store):
    from my_agent_crew.store.runs import DONE, FAILED, RUNNING, RunRecord

    run = RunRecord("r1", "coach", None, "job:coach/x", "t", RUNNING, "2026-09-19T08:00:00")
    run.steps.append({"kind": "tool", "name": "shell_run", "ok": True})
    store.runs.save(run)
    run.spent_usd = 0.01
    store.runs.save(run)
    loaded = store.runs.get("r1")
    assert loaded.steps == run.steps and loaded.spent_usd == 0.01
    assert [r.id for r in store.runs.recent(source_prefix="job:")] == ["r1"]
    assert store.runs.recent(source_prefix="chat") == []
    assert store.runs.latest_for_conversation("c-none") is None
    later = RunRecord("r2", "coach", "c1", "chat", "t", DONE, "2026-09-19T09:00:00")
    store.runs.save(RunRecord("r1b", "coach", "c1", "chat", "t", DONE, "2026-09-19T08:30:00"))
    store.runs.save(later)
    assert store.runs.latest_for_conversation("c1").id == "r2"
    assert store.runs.mark_interrupted("2026-09-19T09:00:00") == 1
    marked = store.runs.get("r1")
    assert marked.status == FAILED and marked.finished_at == "2026-09-19T09:00:00"
    with pytest.raises(KeyError):
        store.runs.get("nope")


def test_agent_id_column_is_added_to_an_older_database(tmp_path: Path):
    import sqlite3

    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL,"
        " status TEXT NOT NULL,"
        " autonomous INTEGER NOT NULL DEFAULT 0, cost_cap_usd REAL NOT NULL DEFAULT 0,"
        " spent_usd REAL NOT NULL DEFAULT 0, unknown_cost_calls INTEGER NOT NULL DEFAULT 0,"
        " skills TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"
        "INSERT INTO conversations VALUES ('c1','old','idle',0,0,0,0,'[]','t','t');"
    )
    conn.commit()
    conn.close()
    store = Store(path)
    assert store.get("c1").agent_id == "default" and store.get("c1").channel == ""
    assert store.get("c1").summary == ""


def test_conversations_carry_a_channel_and_the_latest_per_channel_is_found(store: Store):
    web = store.create(agent_id="coach")
    first = store.create(agent_id="coach", channel="telegram:42")
    second = store.create(agent_id="coach", channel="telegram:42")
    assert web.channel == "" and first.to_dict()["channel"] == "telegram:42"
    assert store.latest_for_channel("coach", "telegram:42").id == second.id
    assert store.latest_for_channel("coach", "telegram:1") is None
    assert store.latest_for_channel("default", "telegram:42") is None


def test_a_summary_is_stored_on_the_conversation_it_recaps(store: Store):
    conv = store.create(agent_id="coach")
    assert conv.summary == ""
    updated = store.update(conv.id, summary="Đã đặt lịch chạy bộ.")
    assert updated.summary == "Đã đặt lịch chạy bộ."
    assert store.get(conv.id).to_dict()["summary"] == "Đã đặt lịch chạy bộ."


def test_the_conversation_before_another_is_found_per_agent_and_channel(store: Store):
    first = store.create(agent_id="coach", channel="telegram:42")
    second = store.create(agent_id="coach", channel="telegram:42")
    third = store.create(agent_id="coach", channel="telegram:42")
    other_agent = store.create(agent_id="pong", channel="telegram:42")
    assert store.previous_for_channel("coach", "telegram:42", third.id).id == second.id
    assert store.previous_for_channel("coach", "telegram:42", second.id).id == first.id
    assert store.previous_for_channel("coach", "telegram:42", first.id) is None
    assert store.previous_for_channel("pong", "telegram:42", other_agent.id) is None


def test_a_delegated_child_is_not_the_conversation_before_the_next_web_chat(store: Store):
    """Children open with an empty channel, like web chats; the chat after a delegation
    must still be told about the previous chat, not about the child in between."""
    chat = store.create(agent_id="coach", channel="")
    store.create(agent_id="coach", channel="", parent_call_id="call-1")
    later = store.create(agent_id="coach", channel="")
    assert store.previous_for_channel("coach", "", later.id).id == chat.id
    store.create(agent_id="coach", channel="", parent_call_id="call-2")
    assert store.latest_for_channel("coach", "").id == later.id


def test_a_job_proposal_stays_pending_until_it_is_decided(store: Store):
    proposal = store.proposals.create(
        agent_id="coach",
        kind="user_fact",
        name="ngu-som",
        description="Ngủ sớm",
        type="preference",
        body="Đi ngủ trước 23h.",
    )
    assert proposal.status == "pending" and proposal.resolved_at is None
    assert [p.id for p in store.proposals.list()] == [proposal.id]
    resolved = store.proposals.resolve(proposal.id, True)
    assert resolved.status == "approved" and resolved.resolved_at
    assert store.proposals.list() == []
    assert [p.id for p in store.proposals.list(status=None)] == [proposal.id]


def test_rejecting_a_proposal_keeps_it_for_the_record(store: Store):
    proposal = store.proposals.create(agent_id="coach", kind="user_forget", name="cu")
    assert store.proposals.resolve(proposal.id, False).status == "rejected"
    assert [p.id for p in store.proposals.list(status="rejected")] == [proposal.id]


def test_a_proposal_cannot_be_decided_twice(store: Store):
    proposal = store.proposals.create(agent_id="coach", kind="user_fact", name="abc")
    store.proposals.resolve(proposal.id, True)
    with pytest.raises(KeyError):
        store.proposals.resolve(proposal.id, True)
    with pytest.raises(KeyError):
        store.proposals.resolve("khong-co", True)


def test_a_conversation_remembers_the_tool_call_that_opened_it(store: Store):
    """How a delegating turn finds the child it already started, instead of a second one."""
    child = store.create(parent_call_id="call-1", agent_id="worker")
    plain = store.create()

    assert store.get(child.id).parent_call_id == "call-1"
    assert plain.parent_call_id == ""
    assert store.for_parent_call("call-1").id == child.id
    assert store.for_parent_call("nobody") is None
    assert store.for_parent_call("") is None


def test_children_of_lists_what_a_turn_delegated_oldest_first(store: Store):
    first = store.create(parent_call_id="call-1")
    second = store.create(parent_call_id="call-2")
    store.create(parent_call_id="other")

    assert [c.id for c in store.children_of(("call-1", "call-2"))] == [first.id, second.id]
    assert store.children_of(()) == []
