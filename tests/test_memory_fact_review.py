"""Reviewing the shared user facts alongside a memory rewrite: a second model call, made
only for the master and only when there is at least one fact, whose output always waits
for approval no matter how the agent is configured."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agents.profile import WORK
from my_agent_crew.llm.fake import completion
from my_agent_crew.memory import agent_store, user_store
from my_agent_crew.memory.consolidate import consolidate_memory
from my_agent_crew.memory.fact_review import review_user_facts
from my_agent_crew.store.memory_proposals import PENDING, USER_FACT, USER_FORGET

REWRITE_REPLY = "- Sếp thích trà.\n---LÝ DO---\n- Không có gì để đổi."


def write_memory(deps, text: str) -> Path:
    path = deps.agent.memory_file
    agent_store.write_memory_md(path, text)
    return path


def write_note(deps, day: str, text: str, *, newer_than: Path | None = None) -> None:
    agent_store.write_note(deps.agent.memory_dir, day, text)
    if newer_than is not None:
        stamp = newer_than.stat().st_mtime + 10
        os.utime(deps.agent.memory_dir / f"{day}.md", (stamp, stamp))


def write_fact(deps, name: str, **overrides):
    fields = {
        "description": name,
        "type": "preference",
        "body": "thân fact",
        "written_by": "owner",
        "source": "chat",
        **overrides,
    }
    return user_store.write_fact(deps.settings.user_dir, name, **fields)


def non_master(deps, agent_id: str = "coach"):
    return replace(deps, profile=replace(deps.profile, id=agent_id, name=agent_id, mode=WORK))


@pytest.fixture
def hub(store) -> ActivityHub:
    return ActivityHub(store)


# --- review_user_facts: the pure function, given facts directly ---


async def test_forget_and_update_actions_become_pending_proposals(deps_factory):
    json_reply = (
        '[{"action": "forget", "name": "ngu-som", "reason": "đã đổi thói quen"},'
        ' {"action": "update", "name": "tra", "body": "Sếp thích trà xanh.",'
        ' "reason": "ghi chép mới"}]'
    )
    deps = deps_factory(script=[completion(json_reply)])
    facts = [
        write_fact(deps, "ngu-som", description="Ngủ sớm", body="Ngủ trước 23h."),
        write_fact(deps, "tra", description="Thích trà", body="Sếp thích trà đen."),
    ]

    review = await review_user_facts(deps, facts, notes=[], today=date(2026, 9, 30))
    assert review.created == 2 and review.skipped == 0 and not review.errored

    proposals = deps.store.proposals.list(status=PENDING)
    kinds = {p.name: p.kind for p in proposals}
    assert kinds == {"ngu-som": USER_FORGET, "tra": USER_FACT}
    updated = next(p for p in proposals if p.name == "tra")
    assert updated.body == "Sếp thích trà xanh."
    assert updated.description == "Thích trà"  # kept from the existing fact, not the model
    assert updated.type == "preference"
    assert updated.reasons == "ghi chép mới"


async def test_an_unknown_name_is_skipped(deps_factory):
    json_reply = '[{"action": "forget", "name": "khong-ton-tai", "reason": "lạ"}]'
    deps = deps_factory(script=[completion(json_reply)])
    facts = [write_fact(deps, "ton-tai")]

    review = await review_user_facts(deps, facts, notes=[], today=date(2026, 9, 30))
    assert review.created == 0 and review.skipped == 1
    assert deps.store.proposals.list(status=PENDING) == []


async def test_an_update_with_no_body_or_an_unchanged_body_is_skipped(deps_factory):
    json_reply = (
        '[{"action": "update", "name": "a", "body": "", "reason": "rỗng"},'
        ' {"action": "update", "name": "b", "body": "y hệt thân hiện tại", "reason": "trùng"}]'
    )
    deps = deps_factory(script=[completion(json_reply)])
    facts = [
        write_fact(deps, "a", body="thân a"),
        write_fact(deps, "b", body="y hệt thân hiện tại"),
    ]

    review = await review_user_facts(deps, facts, notes=[], today=date(2026, 9, 30))
    assert review.created == 0 and review.skipped == 2


async def test_more_than_ten_actions_are_truncated(deps_factory):
    actions = ",".join(f'{{"action": "forget", "name": "f{i}", "reason": "r"}}' for i in range(12))
    deps = deps_factory(script=[completion(f"[{actions}]")])
    facts = [write_fact(deps, f"f{i}") for i in range(12)]

    review = await review_user_facts(deps, facts, notes=[], today=date(2026, 9, 30))
    assert review.created == 10


async def test_broken_json_creates_no_proposals_and_is_reported_as_an_error(deps_factory):
    deps = deps_factory(script=[completion("không phải JSON gì cả")])
    facts = [write_fact(deps, "a")]

    review = await review_user_facts(deps, facts, notes=[], today=date(2026, 9, 30))
    assert review.created == 0 and review.errored is True
    assert deps.store.proposals.list(status=PENDING) == []


async def test_each_review_call_records_a_side_call_with_purpose_consolidate(deps_factory):
    deps = deps_factory(script=[completion('[{"action": "forget", "name": "a", "reason": "x"}]')])
    facts = [write_fact(deps, "a")]

    await review_user_facts(deps, facts, notes=[], today=date(2026, 9, 30))
    rows = deps.store._conn.execute(
        "SELECT purpose FROM side_calls WHERE purpose = 'consolidate'"
    ).fetchall()
    assert len(rows) == 1


# --- Wired into consolidate_memory: master + facts, autonomy, dedupe ---


async def test_master_with_facts_gets_pending_proposals_even_when_autonomous(deps_factory, hub):
    json_reply = '[{"action": "forget", "name": "ngu-som", "reason": "đã đổi"}]'
    deps = deps_factory(
        script=[completion(REWRITE_REPLY), completion(json_reply)], autonomous_default=True
    )
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Cập nhật.", newer_than=memory)
    write_fact(deps, "ngu-som", description="Ngủ sớm", body="Ngủ trước 23h.")

    await consolidate_memory(deps, hub)

    fact_proposals = deps.store.proposals.list(status=PENDING)
    assert any(p.kind == USER_FORGET and p.status == PENDING for p in fact_proposals)


async def test_a_non_master_agent_makes_no_second_model_call(deps_factory, hub):
    deps = deps_factory(script=[completion(REWRITE_REPLY)])
    write_fact(deps, "ngu-som", description="Ngủ sớm", body="Ngủ trước 23h.")
    child = non_master(deps)
    memory = write_memory(child, "- Việc của coach.")
    write_note(child, "2026-09-19", "Cập nhật.", newer_than=memory)

    # Only one script entry was provided; a second model call would exhaust it and raise.
    await consolidate_memory(child, hub)


async def test_fact_review_still_runs_when_the_rewrite_step_is_unchanged(deps_factory, hub):
    json_reply = '[{"action": "forget", "name": "ngu-som", "reason": "đã đổi"}]'
    unchanged_reply = "- Sếp thích trà.\n---LÝ DO---\n- Không đổi gì."
    deps = deps_factory(script=[completion(unchanged_reply), completion(json_reply)])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Sếp thích trà.", newer_than=memory)
    write_fact(deps, "ngu-som", description="Ngủ sớm", body="Ngủ trước 23h.")

    await consolidate_memory(deps, hub)

    assert any(p.kind == USER_FORGET for p in deps.store.proposals.list(status=PENDING))


async def test_a_fact_review_error_does_not_lose_the_rewrite_proposal(deps_factory, hub):
    changed_reply = "- Sếp thích trà.\n- Sếp thích cà phê.\n---LÝ DO---\n- Ghi thêm."
    deps = deps_factory(script=[completion(changed_reply), completion("JSON hỏng")])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Cập nhật.", newer_than=memory)
    write_fact(deps, "ngu-som", description="Ngủ sớm", body="Ngủ trước 23h.")

    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None


async def test_an_identical_pending_proposal_is_not_duplicated(deps_factory):
    json_reply = '[{"action": "forget", "name": "a", "reason": "r"}]'
    deps = deps_factory(script=[completion(json_reply), completion(json_reply)])
    facts = [write_fact(deps, "a")]

    await review_user_facts(deps, facts, notes=[], today=date(2026, 9, 30))
    await review_user_facts(deps, facts, notes=[], today=date(2026, 9, 30))

    assert len(deps.store.proposals.list(status=PENDING)) == 1


async def test_a_different_body_supersedes_the_old_pending_hygiene_proposal(deps_factory):
    first = '[{"action": "update", "name": "a", "body": "thân một", "reason": "r1"}]'
    second = '[{"action": "update", "name": "a", "body": "thân hai", "reason": "r2"}]'
    deps = deps_factory(script=[completion(first), completion(second)])
    facts = [write_fact(deps, "a", body="thân gốc")]

    await review_user_facts(deps, facts, notes=[], today=date(2026, 9, 30))
    await review_user_facts(deps, facts, notes=[], today=date(2026, 9, 30))

    all_proposals = deps.store.proposals.list(status=None)
    pending = [p for p in all_proposals if p.status == PENDING]
    assert len(pending) == 1 and pending[0].body == "thân hai"
    superseded = [p for p in all_proposals if p.status == "superseded"]
    assert len(superseded) == 1 and superseded[0].body == "thân một"
