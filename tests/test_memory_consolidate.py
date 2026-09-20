"""Rewriting MEMORY.md from the daily notes: when it runs, and what it refuses to do."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.memory import agent_store
from my_agent_crew.memory.consolidate import (
    JOB_SOURCE,
    consolidate_memory,
    has_newer_notes,
    notes_text,
    recent_notes,
)
from my_agent_crew.memory.proposals_apply import apply_proposal
from my_agent_crew.store.memory_proposals import AGENT_MEMORY_REWRITE, APPROVED, PENDING
from my_agent_crew.store.runs import DONE, FAILED

CONSOLIDATED = "- Sếp ngủ trước 23h.\n- Sếp thích trà."


def write_memory(deps, text: str) -> Path:
    path = deps.agent.memory_file
    agent_store.write_memory_md(path, text)
    return path


def write_note(deps, day: str, text: str, *, newer_than: Path | None = None) -> None:
    agent_store.write_note(deps.agent.memory_dir, day, text)
    if newer_than is not None:
        stamp = newer_than.stat().st_mtime + 10
        os.utime(deps.agent.memory_dir / f"{day}.md", (stamp, stamp))


@pytest.fixture
def hub(store) -> ActivityHub:
    return ActivityHub(store)


async def test_no_notes_newer_than_the_memory_never_asks_the_model(deps_factory, hub):
    deps = deps_factory(script=[completion(CONSOLIDATED)])
    note_path = deps.agent.memory_dir / "2026-09-19.md"
    agent_store.write_note(deps.agent.memory_dir, "2026-09-19", "Đã chạy bản tin.")
    memory = write_memory(deps, "- Sếp thích trà.")
    stamp = note_path.stat().st_mtime + 10
    os.utime(memory, (stamp, stamp))

    assert await consolidate_memory(deps, hub) is None
    run = hub.recent(5)[0]
    assert run.status == DONE and run.summary == texts.CONSOLIDATE_NOTHING_NEW
    assert deps.store.proposals.list() == []


async def test_a_rewrite_waits_for_approval_and_leaves_the_file_alone(deps_factory, hub):
    deps = deps_factory(script=[completion(CONSOLIDATED)])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Sếp ngủ trước 23h.", newer_than=memory)

    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None
    assert proposal.kind == AGENT_MEMORY_REWRITE and proposal.status == PENDING
    assert proposal.body == CONSOLIDATED and proposal.previous_body == "- Sếp thích trà."
    assert proposal.source == JOB_SOURCE
    # Nothing is written until someone decides, so a bad rewrite costs nothing.
    assert agent_store.read_memory_md(memory) == "- Sếp thích trà."

    run = hub.recent(5)[0]
    assert run.status == DONE and run.summary == texts.CONSOLIDATE_PROPOSED
    assert run.source == JOB_SOURCE and run.conversation_id is None
    assert run.spent_usd == pytest.approx(0.001)


async def test_approving_a_rewrite_replaces_the_file_rather_than_appending(deps_factory, hub):
    deps = deps_factory(script=[completion(CONSOLIDATED)])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Sếp ngủ trước 23h.", newer_than=memory)
    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None

    apply_proposal(
        deps.store,
        proposal.id,
        approve=True,
        user_dir=deps.settings.user_dir,
        memory_files={deps.agent.id: memory},
    )
    assert agent_store.read_memory_md(memory) == CONSOLIDATED


async def test_an_autonomous_agent_writes_the_rewrite_straight_away(deps_factory, hub):
    deps = deps_factory(script=[completion(CONSOLIDATED)], autonomous_default=True)
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Sếp ngủ trước 23h.", newer_than=memory)

    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None and proposal.status == APPROVED
    assert agent_store.read_memory_md(memory) == CONSOLIDATED
    assert hub.recent(5)[0].summary == texts.CONSOLIDATE_APPLIED
    # The previous text is kept, which is what makes the write undoable.
    assert proposal.previous_body == "- Sếp thích trà."


async def test_a_rewrite_that_changes_nothing_is_not_worth_a_proposal(deps_factory, hub):
    deps = deps_factory(script=[completion("- Sếp thích trà.")])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Sếp thích trà.", newer_than=memory)

    assert await consolidate_memory(deps, hub) is None
    assert hub.recent(5)[0].summary == texts.CONSOLIDATE_UNCHANGED
    assert deps.store.proposals.list() == []


async def test_a_provider_that_gives_nothing_back_fails_the_run_and_writes_nothing(
    deps_factory, hub
):
    deps = deps_factory(script=[])  # the scripted provider raises when its script is empty
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Sếp ngủ trước 23h.", newer_than=memory)

    with pytest.raises(ProviderError):
        await consolidate_memory(deps, hub)
    assert hub.recent(5)[0].status == FAILED
    assert agent_store.read_memory_md(memory) == "- Sếp thích trà."
    assert deps.store.proposals.list() == []


async def test_an_agent_with_no_memory_file_yet_still_consolidates(deps_factory, hub):
    deps = deps_factory(script=[completion(CONSOLIDATED)])
    agent_store.write_note(deps.agent.memory_dir, "2026-09-19", "Sếp ngủ trước 23h.")

    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None and proposal.previous_body == ""


def test_the_oldest_notes_are_dropped_first_when_the_budget_runs_out():
    notes = [("2026-09-19", "a" * 40), ("2026-09-18", "b" * 40)]
    text = notes_text(notes, budget=60)
    assert "2026-09-19" in text and "2026-09-18" not in text
    assert notes_text(notes, budget=200).count("##") == 2


def test_only_the_newest_days_with_something_in_them_are_read(deps_factory):
    deps = deps_factory()
    for day in ("2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"):
        agent_store.write_note(deps.agent.memory_dir, day, f"note {day}")
    agent_store.write_note(deps.agent.memory_dir, "2026-09-19", "   ")

    days = [day for day, _ in recent_notes(deps.agent.memory_dir, limit=2)]
    assert days == ["2026-09-18", "2026-09-17"]


def test_an_agent_with_no_notes_at_all_has_nothing_to_fold_in(deps_factory):
    deps = deps_factory()
    assert not has_newer_notes(deps.agent.memory_file, deps.agent.memory_dir)


async def test_the_prompt_carries_the_memory_and_the_notes(deps_factory, hub):
    deps = deps_factory(script=[completion(CONSOLIDATED)])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Sếp ngủ trước 23h.", newer_than=memory)
    await consolidate_memory(deps, hub)

    provider = deps.chain.providers["scripted"]
    sent = provider.requests[0].messages[0].content
    assert "- Sếp thích trà." in sent and "Sếp ngủ trước 23h." in sent
    assert "2026-09-19" in sent
    # No tools: the model is asked for text, not for a turn it could act in.
    assert provider.requests[0].tools == ()
