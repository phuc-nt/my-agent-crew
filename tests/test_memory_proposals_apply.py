"""Deciding a proposal: approving writes the memory, rejecting only records the decision."""

from __future__ import annotations

import pytest

from my_agent_crew.memory import user_store
from my_agent_crew.memory.proposals_apply import apply_proposal
from my_agent_crew.store import Store
from my_agent_crew.store.memory_proposals import (
    AGENT_MEMORY,
    APPROVED,
    REJECTED,
    USER_FACT,
    USER_FORGET,
)


def propose_fact(store: Store, **overrides):
    args = {
        "agent_id": "coach",
        "kind": USER_FACT,
        "name": "ngu-som",
        "description": "Ngủ trước 23h",
        "type": "preference",
        "body": "Người dùng muốn ngủ trước 23h.",
    }
    return store.proposals.create(**{**args, **overrides})


def test_approving_writes_the_fact_and_credits_the_agent_that_asked(tmp_path, store: Store):
    user_dir = tmp_path / "owner"
    proposal = propose_fact(store)

    decided = apply_proposal(store, proposal.id, approve=True, user_dir=user_dir)

    assert decided.status == APPROVED and decided.resolved_at
    (fact,) = user_store.list_facts(user_dir)
    assert fact.name == "ngu-som" and fact.body == "Người dùng muốn ngủ trước 23h."
    assert fact.written_by == "coach" and fact.source == "web"
    assert "ngu-som.md" in user_store.read_index(user_dir)


def test_rejecting_changes_only_the_status(tmp_path, store: Store):
    user_dir = tmp_path / "owner"
    proposal = propose_fact(store)

    decided = apply_proposal(store, proposal.id, approve=False, user_dir=user_dir)

    assert decided.status == REJECTED
    assert user_store.list_facts(user_dir) == []


def test_approving_a_forget_removes_the_fact(tmp_path, store: Store):
    user_dir = tmp_path / "owner"
    user_store.write_fact(
        user_dir,
        name="ngu-som",
        description="cũ",
        type="preference",
        body="cũ",
        written_by="coach",
        source="chat",
    )
    proposal = store.proposals.create(agent_id="coach", kind=USER_FORGET, name="ngu-som")

    apply_proposal(store, proposal.id, approve=True, user_dir=user_dir)

    assert user_store.list_facts(user_dir) == []


def test_approving_an_agent_memory_appends_a_line(tmp_path, store: Store):
    memory_file = tmp_path / "coach" / "MEMORY.md"
    proposal = store.proposals.create(
        agent_id="coach", kind=AGENT_MEMORY, name="tien-do", body="Đã xong vòng 1."
    )

    apply_proposal(
        store,
        proposal.id,
        approve=True,
        user_dir=tmp_path / "owner",
        memory_files={"coach": memory_file},
    )

    assert memory_file.read_text(encoding="utf-8") == "- Đã xong vòng 1.\n"


def test_appending_keeps_what_the_file_already_had(tmp_path, store: Store):
    memory_file = tmp_path / "coach" / "MEMORY.md"
    memory_file.parent.mkdir(parents=True)
    memory_file.write_text("- Điều cũ", encoding="utf-8")
    proposal = store.proposals.create(agent_id="coach", kind=AGENT_MEMORY, body="Điều mới")

    apply_proposal(
        store,
        proposal.id,
        approve=True,
        user_dir=tmp_path / "owner",
        memory_files={"coach": memory_file},
    )

    assert memory_file.read_text(encoding="utf-8") == "- Điều cũ\n- Điều mới\n"


def test_a_failed_write_leaves_the_proposal_pending_for_another_look(tmp_path, store: Store):
    """Resolving after the write means a failure is reviewable, not silently marked done."""
    proposal = store.proposals.create(agent_id="coach", kind=AGENT_MEMORY, body="x")

    with pytest.raises(KeyError):
        apply_proposal(store, proposal.id, approve=True, user_dir=tmp_path, memory_files={})

    assert [p.id for p in store.proposals.list()] == [proposal.id]


def test_an_unknown_kind_is_refused(tmp_path, store: Store):
    proposal = store.proposals.create(agent_id="coach", kind="nonsense", name="x")

    with pytest.raises(ValueError):
        apply_proposal(store, proposal.id, approve=True, user_dir=tmp_path)

    assert [p.id for p in store.proposals.list()] == [proposal.id]


def test_deciding_twice_is_refused(tmp_path, store: Store):
    proposal = propose_fact(store)
    apply_proposal(store, proposal.id, approve=False, user_dir=tmp_path / "owner")

    with pytest.raises(KeyError):
        apply_proposal(store, proposal.id, approve=True, user_dir=tmp_path / "owner")
