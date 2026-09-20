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
    from my_agent_crew.store.runs import FAILED, RUNNING, RunRecord

    run = RunRecord("r1", "coach", None, "job:coach/x", "t", RUNNING, "2026-09-19T08:00:00")
    run.steps.append({"kind": "tool", "name": "shell_run", "ok": True})
    store.runs.save(run)
    run.spent_usd = 0.01
    store.runs.save(run)
    loaded = store.runs.get("r1")
    assert loaded.steps == run.steps and loaded.spent_usd == 0.01
    assert [r.id for r in store.runs.recent(source_prefix="job:")] == ["r1"]
    assert store.runs.recent(source_prefix="chat") == []
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


def test_conversations_carry_a_channel_and_the_latest_per_channel_is_found(store: Store):
    web = store.create(agent_id="coach")
    first = store.create(agent_id="coach", channel="telegram:42")
    second = store.create(agent_id="coach", channel="telegram:42")
    assert web.channel == "" and first.to_dict()["channel"] == "telegram:42"
    assert store.latest_for_channel("coach", "telegram:42").id == second.id
    assert store.latest_for_channel("coach", "telegram:1") is None
    assert store.latest_for_channel("default", "telegram:42") is None


def test_a_channel_remembers_its_current_agent_across_reopen(tmp_path: Path):
    path = tmp_path / "agent.sqlite3"
    store = Store(path)
    assert store.channels.current_agent("telegram:1") is None
    store.set_current_agent("telegram:1", "coach")
    store.set_current_agent("telegram:1", "pong")
    store.set_current_agent("telegram:2", "coach")
    store.close()
    store = Store(path)
    assert store.channels.current_agent("telegram:1") == "pong"
    assert store.channels.current_agent("telegram:2") == "coach"
