from __future__ import annotations

import asyncio
from datetime import UTC

import pytest

from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agent.prompt import system_prompt_for
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message
from my_agent_crew.memory.session_summary import (
    MAX_SUMMARY_CHARS,
    schedule_summary,
    summarize_conversation,
    transcript_text,
)
from my_agent_crew.store import Store
from my_agent_crew.store.runs import DONE, RunRecord


def talked(
    deps: AgentDeps, conv_id: str, user: str = "Nhắc tôi chạy bộ", reply: str = "Đã ghi"
) -> None:
    deps.store.append(conv_id, Message(role="user", content=user))
    deps.store.append(conv_id, Message(role="assistant", content=reply))


async def test_a_finished_conversation_is_recapped_and_the_cost_is_charged_to_it(deps_factory):
    deps = deps_factory(
        script=[completion("Người dùng nhờ nhắc chạy bộ; đã đặt lịch.", cost_usd=0.02)]
    )
    conv = deps.store.create(agent_id="default", channel="telegram:42")
    talked(deps, conv.id)

    summary = await summarize_conversation(deps, conv.id)

    assert summary == "Người dùng nhờ nhắc chạy bộ; đã đặt lịch."
    assert deps.store.get(conv.id).summary == summary
    assert deps.store.get(conv.id).spent_usd == pytest.approx(0.02)


async def test_an_existing_summary_is_reused_unless_the_caller_forces_a_new_one(deps_factory):
    deps = deps_factory(script=[completion("Bản đầu"), completion("Bản sau")])
    conv = deps.store.create()
    talked(deps, conv.id)

    assert await summarize_conversation(deps, conv.id) == "Bản đầu"
    assert await summarize_conversation(deps, conv.id) == "Bản đầu"
    assert await summarize_conversation(deps, conv.id, force=True) == "Bản sau"
    assert deps.store.get(conv.id).summary == "Bản sau"


async def test_a_conversation_the_agent_never_answered_is_not_recapped(deps_factory):
    deps = deps_factory(script=[completion("không nên được gọi")])
    conv = deps.store.create()
    deps.store.append(conv.id, Message(role="user", content="Chào"))

    assert await summarize_conversation(deps, conv.id) == ""
    assert deps.store.get(conv.id).summary == ""


async def test_a_scheduled_brief_is_not_recapped(deps_factory):
    deps = deps_factory(script=[completion("không nên được gọi")])
    conv = deps.store.create()
    talked(deps, conv.id)
    deps.store.runs.save(
        RunRecord(
            "r1", "default", conv.id, "job:default/morning", "brief", DONE, "2026-09-20T07:00:00"
        )
    )

    assert await summarize_conversation(deps, conv.id) == ""
    assert deps.store.get(conv.id).summary == ""


async def test_a_long_recap_is_cut_to_the_budget_and_collapsed_to_one_line(deps_factory):
    deps = deps_factory(script=[completion("x " * 800)])
    conv = deps.store.create()
    talked(deps, conv.id)

    summary = await summarize_conversation(deps, conv.id)

    assert len(summary) == MAX_SUMMARY_CHARS and "\n" not in summary


async def test_a_failing_summary_never_breaks_the_conversation_that_replaced_it(deps_factory):
    deps = deps_factory(script=[])  # an exhausted script raises inside the task
    conv = deps.store.create()
    talked(deps, conv.id)
    kept: list[asyncio.Task[None]] = []

    schedule_summary(kept.append, deps, conv.id)
    await asyncio.gather(*kept)

    assert deps.store.get(conv.id).summary == ""


def test_only_spoken_turns_reach_the_transcript_and_the_tail_is_kept(store: Store):
    conv = store.create()
    store.append(conv.id, Message(role="user", content="  đầu tiên  "))
    store.append(conv.id, Message(role="assistant", content="trả lời"))
    store.append(conv.id, Message(role="tool", content="kết quả công cụ", tool_call_id="t1"))
    store.append(conv.id, Message(role="assistant", content="   "))

    at(store, "2026-09-24T16:30:00+00:00")
    text = transcript_text(store.history(conv.id), UTC)

    assert text == "[24/9 16:30] user: đầu tiên\n[24/9 16:30] assistant: trả lời"
    assert transcript_text(store.history(conv.id), UTC, limit=8) == text[-8:]


def at(store: Store, stamp: str) -> None:
    store._conn.execute("UPDATE messages SET created_at = ?", (stamp,))


async def test_the_recap_is_asked_for_in_dates_of_the_persons_zone(deps_factory):
    """A recap that says "tonight" is read the next day as a different night."""
    deps = deps_factory(script=[completion("24/9: nhắc chạy bộ.")], timezone="Asia/Ho_Chi_Minh")
    conv = deps.store.create()
    talked(deps, conv.id, user="tối nay tôi uống 2 lon bia")
    at(deps.store, "2026-09-24T16:30:00+00:00")

    await summarize_conversation(deps, conv.id)

    [request] = deps.chain.providers["scripted"].requests
    asked = request.messages[0].content
    assert "[24/9 23:30] user: tối nay tôi uống 2 lon bia" in asked
    assert "không viết 'hôm nay', 'hôm qua', 'tối nay'" in asked


def test_the_next_conversation_reads_when_the_previous_one_ended(deps_factory):
    deps = deps_factory(timezone="Asia/Ho_Chi_Minh")
    first = deps.store.create(agent_id="default", channel="telegram:42")
    deps.store.update(first.id, summary="Người dùng ghi 2 lon bia ngày 24/9.")
    deps.store._conn.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        ("2026-09-24T16:30:00+00:00", first.id),
    )
    second = deps.store.create(agent_id="default", channel="telegram:42")

    prompt = system_prompt_for(deps, deps.store.get(second.id))

    assert "## Cuộc trước (lần cuối 24/9 23:30)\nNgười dùng ghi 2 lon bia ngày 24/9." in prompt
