"""Conversations as episodes: which ones count, when a recap is stale, and how the week's
recaps reach the nightly memory rewrite."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.turn_context import PRESENT_SOURCES
from my_agent_crew.clock import local_day
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message
from my_agent_crew.memory import agent_store
from my_agent_crew.memory.consolidate import consolidate_memory
from my_agent_crew.memory.episodes import Recalled, merge_with_notes
from my_agent_crew.memory.session_summary import summarize_conversation
from my_agent_crew.store import Store
from my_agent_crew.store.episodes import PERSON_ROOTS
from my_agent_crew.store.memory_proposals import APPROVED
from my_agent_crew.store.runs import DONE, RunRecord

CONSOLIDATED = "- Sếp thích trà.\n- Sếp ngủ trước 23h."
LONG_AGO = "2000-01-01T00:00:00+00:00"


def talked(store: Store, conv_id: str, user: str = "Đổi lịch chạy bộ sang 6h") -> None:
    store.append(conv_id, Message(role="user", content=user))
    store.append(conv_id, Message(role="assistant", content="Đã đổi"))


def spoken_at(store: Store, conv_id: str, stamp: str) -> None:
    store._conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (stamp, conv_id))


@pytest.fixture
def hub(store) -> ActivityHub:
    return ActivityHub(store)


def test_only_threads_that_began_with_a_person_are_episodes(store: Store):
    spoken = store.create(title="Chạy bộ", channel="telegram:1")
    talked(store, spoken.id)
    handed = store.create(parent_call_id="c1", root_id=spoken.id, root_source="telegram")
    talked(store, handed.id)
    from_a_job = store.create(parent_call_id="c2", root_id="x", root_source="job")
    talked(store, from_a_job.id)
    unknown_root = store.create(parent_call_id="c3")
    talked(store, unknown_root.id)
    brief = store.create()
    talked(store, brief.id)
    store.runs.save(RunRecord("r1", "default", brief.id, "job:default/brief", "b", DONE, "x"))
    store.create()  # nothing said in it yet
    other = store.create(agent_id="coach")
    talked(store, other.id)

    found = store.episodes.recent("default", LONG_AGO, 10)
    assert {e.conversation_id for e in found} == {spoken.id, handed.id}
    assert all(e.stale for e in found)


def test_a_person_root_is_any_source_a_person_speaks_through():
    # The store may not import the agent package, so it keeps its own copy of the list.
    assert set(PERSON_ROOTS) == set(PRESENT_SOURCES)


def test_threads_last_spoken_in_before_the_window_are_left_out(store: Store):
    old = store.create()
    talked(store, old.id)
    spoken_at(store, old.id, "2026-10-01T00:00:00+00:00")

    assert store.episodes.recent("default", "2026-10-20T00:00:00+00:00", 10) == []


async def test_a_recap_the_conversation_outgrew_is_written_again(deps_factory):
    deps = deps_factory(
        script=[completion("Đổi lịch sang 6h."), completion("Đổi sang 6h, rồi 7h.")]
    )
    conv = deps.store.create()
    talked(deps.store, conv.id)
    assert await summarize_conversation(deps, conv.id) == "Đổi lịch sang 6h."
    assert not deps.store.episodes.recent("default", LONG_AGO, 10)[0].stale

    talked(deps.store, conv.id, user="Thôi đổi sang 7h")
    assert deps.store.episodes.recent("default", LONG_AGO, 10)[0].stale
    assert await summarize_conversation(deps, conv.id) == "Đổi sang 6h, rồi 7h."
    assert deps.store.episodes.summarized_upto(conv.id) == 4


async def test_a_recap_from_before_its_reach_was_kept_is_taken_as_final(deps_factory):
    deps = deps_factory(script=[completion("không nên được gọi")])
    conv = deps.store.create()
    talked(deps.store, conv.id)
    deps.store.update(conv.id, touch=False, summary="Bản cũ")

    assert not deps.store.episodes.recent("default", LONG_AGO, 10)[0].stale
    assert await summarize_conversation(deps, conv.id) == "Bản cũ"


def test_recaps_sit_among_the_notes_by_day_with_the_agents_notes_first():
    notes = [("2026-10-28", "ghi chép 28"), ("2026-10-26", "ghi chép 26")]
    recalled = [
        Recalled("t", "2026-10-28 · trò chuyện «A»", "tóm tắt A"),
        Recalled("t", "2026-10-27 · trò chuyện «B»", "tóm tắt B"),
    ]
    days = [label for label, _ in merge_with_notes(notes, recalled)]
    assert days == [
        "2026-10-28",
        "2026-10-28 · trò chuyện «A»",
        "2026-10-27 · trò chuyện «B»",
        "2026-10-26",
    ]


def days_ago(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


async def test_a_conversation_with_no_note_still_reaches_the_rewrite(settings, deps_factory, hub):
    stamp = days_ago(1).isoformat(timespec="seconds")
    day = local_day(stamp, settings.zone)
    rewritten = f"- Sếp thích trà.\n- Sếp chạy bộ lúc 6h ({day})."
    deps = deps_factory(
        script=[completion("Sếp đổi lịch chạy bộ sang 6h."), completion(rewritten)],
        autonomous_default=True,
    )
    conv = deps.store.create(title="Chạy bộ")
    talked(deps.store, conv.id)
    spoken_at(deps.store, conv.id, stamp)
    agent_store.write_memory_md(deps.agent.memory_file, "- Sếp thích trà.")
    before = days_ago(2).timestamp()
    os.utime(deps.agent.memory_file, (before, before))

    proposal = await consolidate_memory(deps, hub)

    assert deps.store.get(conv.id).summary == "Sếp đổi lịch chạy bộ sang 6h."
    sent = deps.chain.providers["scripted"].requests[1].messages[0].content
    assert f"## {day} · trò chuyện «Chạy bộ»\nSếp đổi lịch chạy bộ sang 6h." in sent
    # The day came from the recap's heading, so the date check lets the rewrite through.
    assert proposal is not None and proposal.status == APPROVED
    assert agent_store.read_memory_md(deps.agent.memory_file) == rewritten


async def test_a_conversation_already_folded_in_is_nothing_new(deps_factory, hub):
    deps = deps_factory(script=[completion("không nên được gọi")])
    conv = deps.store.create()
    talked(deps.store, conv.id)
    deps.store.update(conv.id, touch=False, summary="Bản cũ")
    spoken_at(deps.store, conv.id, days_ago(2).isoformat(timespec="seconds"))
    agent_store.write_memory_md(deps.agent.memory_file, "- Sếp thích trà.")

    assert await consolidate_memory(deps, hub) is None
    assert hub.recent(5)[0].summary == texts.CONSOLIDATE_NOTHING_NEW


async def test_a_recap_that_fails_does_not_cost_the_rewrite(deps_factory, hub, monkeypatch):
    deps = deps_factory(script=[completion(CONSOLIDATED)])
    conv = deps.store.create()
    talked(deps.store, conv.id)
    agent_store.write_note(deps.agent.memory_dir, "2026-10-28", "Sếp ngủ trước 23h.")

    async def broken(*_args, **_kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("my_agent_crew.memory.episodes.summarize_conversation", broken)
    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None and proposal.body == CONSOLIDATED
