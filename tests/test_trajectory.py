"""A run written out whole: the messages it wrote into its conversation, the children it
delegated to, and a Markdown copy a person can read."""

import json

from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.activity.trajectory import RESULT_LIMIT, build, to_markdown
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.resume import resolve_approval
from my_agent_crew.config import Route
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store import Store
from my_agent_crew.store.db import new_id, now_iso
from my_agent_crew.store.runs import DONE, RunRecord
from my_agent_crew.texts import TRAJECTORY_NOTICE
from tests.conftest import collect


async def turn(hub: ActivityHub, deps, conv_id: str, text: str) -> RunRecord:
    await collect(tracked(hub, run_turn(deps, conv_id, text), "default", "chat", "t", conv_id))
    return deps.store.runs.latest_for_conversation(conv_id)


def contents(data: dict) -> list[str]:
    return [m["content"] for m in data["messages"]]


async def test_each_run_notes_where_its_conversation_stood_and_keeps_to_its_own_messages(
    deps_factory,
):
    deps = deps_factory(script=[completion("một"), completion("hai")])
    hub = ActivityHub(deps.store)
    conv = deps.store.create()

    first = await turn(hub, deps, conv.id, "a")
    second = await turn(hub, deps, conv.id, "b")

    assert (first.after_seq, second.after_seq) == (0, 2)
    assert deps.store.runs.get(second.id).after_seq == 2
    assert contents(build(deps.store, first)) == ["a", "một"]
    assert contents(build(deps.store, second)) == ["b", "hai"]
    assert build(deps.store, second)["slice"] == "by_seq"


async def test_a_run_resumed_after_an_approval_keeps_where_it_began(deps_factory):
    deps = deps_factory(routes=(Route("fake", "echo"),))
    hub = ActivityHub(deps.store)
    conv = deps.store.create()
    await turn(hub, deps, conv.id, "chào")
    command = '/tool shell_run {"command": "echo 1"}'
    paused = await collect(
        tracked(hub, run_turn(deps, conv.id, command), "default", "chat", "t", conv.id)
    )
    [run] = hub.live()

    resumed = resolve_approval(deps, conv.id, paused[-1].approval_id, True)
    await collect(tracked(hub, resumed, "default", "chat", "t", conv.id))

    stored = deps.store.runs.get(run.id)
    assert stored.after_seq == 2 and stored.status == DONE
    data = build(deps.store, stored)
    # The whole turn, from the command through the pause to the answer after it.
    assert data["messages"][0]["content"] == command
    assert [m["seq"] for m in data["messages"]] == [
        m.seq for m in deps.store.history(conv.id) if m.seq > 2
    ]
    assert any(m["role"] == "tool" and m["name"] == "shell_run" for m in data["messages"])


def test_a_run_recorded_before_runs_kept_their_start_is_sliced_by_time(store: Store):
    conv = store.create()
    said = [
        ("trước", "2026-09-20T08:00:00+00:00"),
        ("hỏi", "2026-09-20T09:00:00+00:00"),
        ("đáp", "2026-09-20T09:00:40+00:00"),
        ("sau", "2026-09-20T10:00:00+00:00"),
    ]
    for text, stamp in said:
        store.messages.append(conv.id, Message(role="user", content=text), stamp)
    old = RunRecord(
        "old",
        "default",
        conv.id,
        "chat",
        "t",
        DONE,
        "2026-09-20T09:00:00+00:00",
        finished_at="2026-09-20T09:01:00+00:00",
    )
    store.runs.save(old)

    data = build(store, store.runs.get("old"))

    assert data["slice"] == "by_time" and contents(data) == ["hỏi", "đáp"]


def delegating_turn(store: Store, conv_id: str, call_id: str, task: str) -> None:
    store.append(conv_id, Message(role="user", content=f"nhờ {task}"))
    call = ToolCall(call_id, "delegate", {"agent": "coach", "task": task})
    store.append(conv_id, Message(role="assistant", tool_calls=(call,)), "fake", "echo")
    result = f"conversation=x status=done spent=$0.0000 steps=1\noutcome=done\n{task} xong"
    store.append(
        conv_id, Message(role="tool", content=result, tool_call_id=call_id, name="delegate")
    )


def child_of(store: Store, parent_id: str, call_id: str, said: str) -> str:
    """A child as `_run_child` leaves it: its own conversation and a run whose source names
    the conversation that delegated."""
    child = store.create(agent_id="coach", parent_call_id=call_id)
    store.append(child.id, Message(role="user", content="việc được giao"))
    store.append(child.id, Message(role="assistant", content=said), "fake", "echo")
    source = f"delegate:{parent_id}"
    store.runs.save(
        RunRecord(new_id(), "coach", child.id, source, "t", DONE, now_iso(), after_seq=0)
    )
    return child.id


def run_from(store: Store, conv_id: str, after_seq: int) -> RunRecord:
    run = RunRecord(new_id(), "default", conv_id, "chat", "t", DONE, now_iso(), after_seq=after_seq)
    store.runs.save(run)
    return run


def test_a_child_comes_along_but_not_another_conversations_child_with_the_same_call_id(
    store: Store,
):
    """A provider that sends no call id gets `call_0`, `call_1`, … in every conversation, so
    the bare id can name another agent's child."""
    parent, other = store.create(), store.create()
    run = run_from(store, parent.id, 0)
    delegating_turn(store, parent.id, "call_0", "tóm tắt")
    mine = child_of(store, parent.id, "call_0", "Tóm tắt của tôi")
    delegating_turn(store, other.id, "call_0", "đọc nhật ký")
    child_of(store, other.id, "call_0", "Nhật ký riêng của người khác")

    data = build(store, run)

    [child] = data["children"]
    assert child["conversation_id"] == mine and child["tool_call_id"] == "call_0"
    assert child["agent_id"] == "coach"
    assert contents(child) == ["việc được giao", "Tóm tắt của tôi"]
    assert "Nhật ký riêng" not in json.dumps(data, ensure_ascii=False)


def test_only_the_children_this_run_opened_come_along(store: Store):
    conv = store.create()
    earlier = run_from(store, conv.id, 0)
    delegating_turn(store, conv.id, "call_a", "việc cũ")
    child_of(store, conv.id, "call_a", "đáp cũ")
    later = run_from(store, conv.id, store.messages.max_seq(conv.id))
    delegating_turn(store, conv.id, "call_b", "việc mới")
    new = child_of(store, conv.id, "call_b", "đáp mới")

    assert [c["conversation_id"] for c in build(store, later)["children"]] == [new]
    assert [c["tool_call_id"] for c in build(store, earlier)["children"]] == ["call_a"]


def test_a_run_with_no_conversation_exports_its_record_and_steps(store: Store):
    step = {"kind": "tool", "name": "shell", "ok": True, "output": "synced", "duration_ms": 12}
    run = RunRecord("job", "default", None, "job:sync", "Đồng bộ", DONE, now_iso(), steps=[step])

    data = build(store, run)
    markdown = to_markdown(data)

    assert data["slice"] == "none" and data["messages"] == [] and data["children"] == []
    assert data["run"]["steps"] == [step]
    assert "shell" in markdown and "synced" in markdown


def test_the_markdown_carries_every_tool_call_with_its_arguments_and_result(store: Store):
    conv = store.create()
    run = run_from(store, conv.id, 0)
    store.append(conv.id, Message(role="user", content="đọc notes.md"))
    call = ToolCall("t1", "read_file", {"path": "notes.md"})
    store.append(conv.id, Message(role="assistant", tool_calls=(call,)), "fake", "echo")
    result = "dòng một\n```\nkhối trong kết quả\n```"
    store.append(conv.id, Message(role="tool", content=result, tool_call_id="t1", name="read_file"))
    store.append(conv.id, Message(role="assistant", content="Đã đọc."), "fake", "echo")

    markdown = to_markdown(build(store, run))

    assert markdown.index(TRAJECTORY_NOTICE) < markdown.index("đọc notes.md")
    assert "read_file" in markdown and '"path": "notes.md"' in markdown
    assert "khối trong kết quả" in markdown and "Đã đọc." in markdown and "echo" in markdown
    # A result holding a fence of its own sits in a longer one, so it cannot close it early.
    assert f"````\n{result}\n````" in markdown


def test_a_long_tool_result_is_cut_and_says_how_long_it_was_unless_all_is_asked_for(
    store: Store,
):
    conv = store.create()
    run = run_from(store, conv.id, 0)
    long = "x" * 5000
    store.append(conv.id, Message(role="tool", content=long, tool_call_id="t1", name="read_file"))
    store.append(conv.id, Message(role="assistant", content="y" * 5000), "fake", "echo")

    cut, whole = build(store, run)["messages"], build(store, run, full=True)["messages"]

    assert cut[0]["content"].startswith("x" * RESULT_LIMIT)
    assert "x" * (RESULT_LIMIT + 1) not in cut[0]["content"] and "5000" in cut[0]["content"]
    # Only tool results are cut: what the agent said is what the person read.
    assert cut[1]["content"] == "y" * 5000
    assert whole[0]["content"] == long
