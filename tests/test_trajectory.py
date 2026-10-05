"""A run written out whole: the messages it wrote into its conversation, the children it
delegated to, and a Markdown copy a person can read."""

import json

from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.activity.trajectory import RESULT_LIMIT, build
from my_agent_crew.activity.trajectory_markdown import to_markdown
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.resume import resolve_approval
from my_agent_crew.agent.turn_notes import render
from my_agent_crew.artifacts.diff import fenced
from my_agent_crew.config import Route
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store import Store
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import new_id, now_iso
from my_agent_crew.store.runs import DONE, HALTED, RUNNING, RunRecord
from my_agent_crew.texts import (
    TRAJECTORY_NOTICE,
    TRAJECTORY_REDACTED,
    TRAJECTORY_ROLES,
    TRAJECTORY_TITLE,
)
from tests.canvas_helpers import PLAN, say, seen_canvas
from tests.conftest import collect
from tests.trajectory_fake import child_of, delegate_call, delegating_turn, run_from


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
        ("cuối", "2026-09-20T09:01:00+00:00"),
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

    # Both ends are kept: a stamp has one-second resolution, as does the run's finish.
    assert data["slice"] == "by_time" and contents(data) == ["hỏi", "đáp", "cuối"]


def test_runs_that_began_in_the_same_second_are_told_apart_by_where_they_began(store: Store):
    conv = store.create()
    stamp = "2026-09-20T09:00:00+00:00"
    for text in ("a", "một", "b", "hai"):
        store.messages.append(conv.id, Message(role="user", content=text), stamp)
    first = RunRecord("first", "default", conv.id, "chat", "t", DONE, stamp, after_seq=0)
    second = RunRecord("second", "default", conv.id, "chat", "t", DONE, stamp, after_seq=2)
    store.runs.save(second)
    store.runs.save(first)

    assert contents(build(store, first)) == ["a", "một"]
    assert contents(build(store, second)) == ["b", "hai"]


def test_a_run_that_wrote_nothing_keeps_its_place_when_it_is_saved_again(store: Store):
    """Two runs that began in the same second where the conversation stood at the same seq
    are ordered by when each was created. Saving the first again as it ends must not move
    it after the second, or it would take the second's messages as its own."""
    conv = store.create()
    stamp = "2026-09-20T09:00:00+00:00"
    for text in ("a", "một"):
        store.messages.append(conv.id, Message(role="user", content=text), stamp)
    empty = RunRecord("empty", "default", conv.id, "chat", "t", RUNNING, stamp, after_seq=2)
    store.runs.save(empty)
    busy = RunRecord("busy", "default", conv.id, "chat", "t", DONE, stamp, after_seq=2)
    store.runs.save(busy)
    for text in ("b", "hai"):
        store.messages.append(conv.id, Message(role="user", content=text), stamp)
    empty.status, empty.finished_at = HALTED, stamp
    store.runs.save(empty)

    assert build(store, store.runs.get("empty"))["messages"] == []
    assert contents(build(store, store.runs.get("busy"))) == ["b", "hai"]
    assert store.runs.latest_for_conversation(conv.id).id == "busy"


def test_a_child_comes_along_but_not_another_conversations_child_with_the_same_call_id(
    store: Store,
):
    """A provider that sends no call id gets `call_0`, `call_1`, … in every conversation, so
    the bare id can name another agent's child."""
    parent, other = store.create(), store.create()
    run = run_from(store, parent.id, 0)
    mine = delegating_turn(store, parent.id, "call_0", "tóm tắt", "Tóm tắt của tôi")
    delegating_turn(store, other.id, "call_0", "đọc nhật ký", "Nhật ký riêng của người khác")

    data = build(store, run)

    [child] = data["children"]
    assert child["conversation_id"] == mine and child["tool_call_id"] == "call_0"
    assert child["agent_id"] == "coach"
    assert contents(child) == ["việc được giao", "Tóm tắt của tôi"]
    assert "Nhật ký riêng" not in json.dumps(data, ensure_ascii=False)


def test_only_the_children_this_run_opened_come_along(store: Store):
    conv = store.create()
    earlier = run_from(store, conv.id, 0)
    delegating_turn(store, conv.id, "call_a", "việc cũ", "đáp cũ")
    later = run_from(store, conv.id, store.messages.max_seq(conv.id))
    new = delegating_turn(store, conv.id, "call_b", "việc mới", "đáp mới")

    assert [c["conversation_id"] for c in build(store, later)["children"]] == [new]
    assert [c["tool_call_id"] for c in build(store, earlier)["children"]] == ["call_a"]


def test_two_runs_whose_calls_were_both_call_0_each_bring_only_their_own_child(store: Store):
    """A provider that sends no call id gets `call_0` again in every turn."""
    conv = store.create()
    first = run_from(store, conv.id, 0)
    one = delegating_turn(store, conv.id, "call_0", "việc một", "đáp một")
    second = run_from(store, conv.id, store.messages.max_seq(conv.id))
    two = delegating_turn(store, conv.id, "call_0", "việc hai", "đáp hai")

    assert [c["conversation_id"] for c in build(store, first)["children"]] == [one]
    assert [c["conversation_id"] for c in build(store, second)["children"]] == [two]


def test_a_call_still_waiting_brings_the_child_it_opened_while_the_run_went_on(store: Store):
    """With no result yet there is no line naming the child, only the call id: the child
    must have been opened during the run and by this conversation."""
    conv, other = store.create(), store.create()
    halted = RunRecord(
        "halted",
        "default",
        conv.id,
        "chat",
        "t",
        HALTED,
        "2020-01-01T08:00:00+00:00",
        finished_at="2020-01-01T08:05:00+00:00",
        after_seq=0,
    )
    store.runs.save(halted)
    delegate_call(store, conv.id, "call_0", "việc bỏ dở")
    running = run_from(store, conv.id, store.messages.max_seq(conv.id), RUNNING)
    delegate_call(store, conv.id, "call_0", "việc đang làm")
    child = child_of(store, conv.id, "call_0", "đang làm")
    delegate_call(store, other.id, "call_0", "việc của người khác")
    child_of(store, other.id, "call_0", "của người khác")

    assert [c["conversation_id"] for c in build(store, running)["children"]] == [child]
    assert build(store, halted)["children"] == []


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


def test_the_markdown_keeps_the_title_on_one_line_and_closes_a_block_left_open(store: Store):
    conv = store.create()
    run = RunRecord(
        new_id(),
        "default",
        conv.id,
        "chat",
        "Dòng một\n# Giả\n```",
        DONE,
        now_iso(),
        summary="xong\n## Giả",
        after_seq=0,
    )
    store.runs.save(run)
    store.append(conv.id, Message(role="user", content="viết code"))
    stopped = "Đây:\n```python\nprint(1)"
    store.append(conv.id, Message(role="assistant", content=stopped), "fake", "echo")
    store.append(conv.id, Message(role="user", content="Dùng ```x``` nhé:\n```\nok\n```"))
    store.append(conv.id, Message(role="assistant", content="Được."), "fake", "echo")

    markdown = to_markdown(build(store, run))

    assert markdown.splitlines()[0] == TRAJECTORY_TITLE.format(title="Dòng một # Giả ```")
    assert "\n## Giả" not in markdown and "xong ## Giả" in markdown
    # An answer stopped mid-block is closed before the next message's heading.
    assert "Đây:\n```python\nprint(1)\n```\n\n### #3" in markdown
    # A block that closes itself, and code written inline, are left as they were.
    assert "Dùng ```x``` nhé:\n```\nok\n```\n\n### #4" in markdown


def test_a_message_read_after_the_agents_memory_carries_it_with_secrets_covered(store: Store):
    """As the model read it: the block, then the canvas note, then the message. A message
    that told nothing has no such field."""
    conv = store.create()
    run = run_from(store, conv.id, 0)
    secret = "note-secret-" + "klmnopqrstuvwxyz" * 2
    section = {"key": "memory/2026-10-06.md", "title": "memory/2026-10-06.md", "mode": "whole"}
    section |= {"body": f"- 07:00 mật khẩu {secret}", "chars": 60, "digest": "0" * 16}
    raw = json.dumps({"sections": [section]}, ensure_ascii=False)
    store.append(conv.id, Message(role="user", content="tiếp nhé"), turn_notes=lambda: raw)
    nothing = '{"sections": []}'
    store.append(conv.id, Message(role="user", content="nữa"), turn_notes=lambda: nothing)

    data = build(store, run, secrets=[secret])

    block = render(raw).replace(secret, TRAJECTORY_REDACTED)
    first, second = data["messages"]
    assert secret in render(raw) and first["turn_notes"] == block
    assert first["content"] == "tiếp nhé" and "turn_notes" not in second
    heading = f"### #{first['seq']} · {TRAJECTORY_ROLES['user']}"
    assert f"{heading}\n\n{fenced(block)}\n\ntiếp nhé\n" in to_markdown(data)
    first["context"] = "ghi chú canvas"
    assert f"{fenced(block)}\n\n{fenced('ghi chú canvas')}\n\ntiếp nhé\n" in to_markdown(data)


def test_a_message_read_after_a_canvas_note_carries_the_note_with_secrets_covered(store: Store):
    """The Markdown puts the note ahead of the message, as the model read it. A message
    stored without a note has no such field."""
    conv = store.create()
    run = run_from(store, conv.id, 0)
    art = seen_canvas(store, conv)
    secret = "canvas-secret-" + "klmnopqrstuvwxyz" * 2
    store.artifacts.write(art, PLAN.replace("bơi", f"bơi {secret}"), USER, "")
    note = say(store, conv)
    store.append(conv.id, Message(role="assistant", content="Đã xem."), "fake", "echo")

    data = build(store, run, secrets=[secret])

    covered = note.replace(secret, TRAJECTORY_REDACTED)
    first, second = data["messages"]
    assert secret in note and first["context"] == covered and "context" not in second
    heading = f"### #{first['seq']} · {TRAJECTORY_ROLES['user']}"
    assert f"{heading}\n\n{fenced(covered)}\n\ntiếp nhé\n" in to_markdown(data)
