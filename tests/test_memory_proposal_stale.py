"""A second consolidation must not let an approval overwrite work done in between: the
newer rewrite proposal supersedes the older one, and approving a rewrite whose file moved
under it is refused rather than silently overwritten."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from my_agent_crew import texts
from my_agent_crew.config import Route
from my_agent_crew.memory import agent_store, user_store
from my_agent_crew.memory.proposals_apply import StaleProposal, apply_proposal
from my_agent_crew.memory.rewrite_proposal import submit_rewrite
from my_agent_crew.server import create_app
from my_agent_crew.store.memory_proposals import (
    AGENT_MEMORY_REWRITE,
    APPROVED,
    PENDING,
    SUPERSEDED,
    USER_FACT,
    USER_FORGET,
)

TODAY = date(2026, 9, 30)


@pytest.fixture
def deps(deps_factory):
    return deps_factory(routes=(Route("fake", "echo"),))


@pytest.fixture
def client(deps):
    with TestClient(create_app(deps, schedule=False), base_url="http://127.0.0.1") as c:
        yield c


# --- store.supersede / find_pending -------------------------------------------------------


def test_supersede_requires_at_least_one_filter(store):
    with pytest.raises(ValueError):
        store.proposals.supersede("default")


def test_supersede_flips_pending_rows_of_the_same_agent_and_kind(store):
    first = store.proposals.create(agent_id="default", kind=AGENT_MEMORY_REWRITE, body="a")
    second = store.proposals.create(agent_id="default", kind=AGENT_MEMORY_REWRITE, body="b")

    changed = store.proposals.supersede("default", kind=AGENT_MEMORY_REWRITE, keep_id=second.id)
    assert changed == 1
    assert store.proposals.get(first.id).status == SUPERSEDED
    assert store.proposals.get(first.id).resolved_at is not None
    assert store.proposals.get(second.id).status == PENDING


def test_supersede_never_touches_another_agents_proposals(store):
    store.proposals.create(agent_id="coach", kind=AGENT_MEMORY_REWRITE, body="a")
    changed = store.proposals.supersede("default", kind=AGENT_MEMORY_REWRITE)
    assert changed == 0


def test_find_pending_matches_on_agent_kind_name_and_body(store):
    store.proposals.create(agent_id="default", kind=USER_FACT, name="a", body="x")
    found = store.proposals.find_pending("default", USER_FACT, "a", "x")
    assert found is not None
    assert store.proposals.find_pending("default", USER_FACT, "a", "khác") is None


def test_supersede_never_touches_a_pending_proposal_of_another_kind(store):
    from_chat = store.proposals.create(agent_id="default", kind=USER_FACT, name="a", body="x")
    assert store.proposals.supersede("default", kind=AGENT_MEMORY_REWRITE) == 0
    assert store.proposals.get(from_chat.id).status == PENDING


def test_supersede_never_relabels_a_decided_proposal(store):
    decided = store.proposals.create(agent_id="default", kind=AGENT_MEMORY_REWRITE, body="a")
    store.proposals.resolve(decided.id, approve=True)
    assert store.proposals.supersede("default", kind=AGENT_MEMORY_REWRITE) == 0
    assert store.proposals.get(decided.id).status == APPROVED


def test_find_pending_ignores_a_proposal_already_decided(store):
    rejected = store.proposals.create(agent_id="default", kind=USER_FORGET, name="a", body="x")
    store.proposals.resolve(rejected.id, approve=False)
    assert store.proposals.find_pending("default", USER_FORGET, "a", "x") is None


# --- proposals_apply.StaleProposal / _write -----------------------------------------------


def test_approving_a_rewrite_whose_file_has_since_changed_raises_stale(deps):
    memory = deps.agent.memory_file
    agent_store.write_memory_md(memory, "- Cũ.")
    proposal = deps.store.proposals.create(
        agent_id=deps.agent.id,
        kind=AGENT_MEMORY_REWRITE,
        body="- Mới.",
        previous_body="- Bản khác với tệp hiện tại.",
    )

    with pytest.raises(StaleProposal):
        apply_proposal(
            deps.store,
            proposal.id,
            approve=True,
            user_dir=deps.settings.user_dir,
            memory_files={deps.agent.id: memory},
        )
    assert agent_store.read_memory_md(memory) == "- Cũ."
    assert deps.store.proposals.get(proposal.id).status == SUPERSEDED


def test_a_matching_previous_body_applies_normally(deps):
    memory = deps.agent.memory_file
    agent_store.write_memory_md(memory, "- Cũ.")
    proposal = deps.store.proposals.create(
        agent_id=deps.agent.id, kind=AGENT_MEMORY_REWRITE, body="- Mới.", previous_body="- Cũ."
    )

    applied = apply_proposal(
        deps.store,
        proposal.id,
        approve=True,
        user_dir=deps.settings.user_dir,
        memory_files={deps.agent.id: memory},
    )
    assert applied.status == "approved"
    assert agent_store.read_memory_md(memory) == "- Mới."


# --- the route: 409 for a stale approval, and for an already-superseded proposal ----------


def test_approving_a_stale_rewrite_over_http_is_409_and_leaves_the_file(client, deps):
    memory = deps.agent.memory_file
    agent_store.write_memory_md(memory, "- Ghi thêm trong lúc chạy.")
    proposal = deps.store.proposals.create(
        agent_id=deps.agent.id,
        kind=AGENT_MEMORY_REWRITE,
        body="- Mới.",
        previous_body="- Bản cũ trước khi model chạy.",
    )

    decided = client.post(f"/api/memory/proposals/{proposal.id}", json={"approve": True})
    assert decided.status_code == 409
    assert "stale" in decided.json()["detail"]
    assert agent_store.read_memory_md(memory) == "- Ghi thêm trong lúc chạy."
    assert deps.store.proposals.get(proposal.id).status == SUPERSEDED


def test_approving_an_already_superseded_proposal_is_409_stale(client, deps):
    proposal = deps.store.proposals.create(
        agent_id=deps.agent.id, kind=AGENT_MEMORY_REWRITE, body="- Mới.", previous_body="- Cũ."
    )
    deps.store.proposals.supersede(deps.agent.id, kind=AGENT_MEMORY_REWRITE)

    decided = client.post(f"/api/memory/proposals/{proposal.id}", json={"approve": True})
    assert decided.status_code == 409
    assert "stale" in decided.json()["detail"]


def test_a_second_consolidation_supersedes_the_first_pending_rewrite(client, deps):
    first = deps.store.proposals.create(
        agent_id=deps.agent.id, kind=AGENT_MEMORY_REWRITE, body="- Bản một.", previous_body=""
    )
    second = deps.store.proposals.create(
        agent_id=deps.agent.id, kind=AGENT_MEMORY_REWRITE, body="- Bản hai.", previous_body=""
    )
    deps.store.proposals.supersede(deps.agent.id, kind=AGENT_MEMORY_REWRITE, keep_id=second.id)

    pending_ids = {p["id"] for p in client.get("/api/memory/proposals").json()["proposals"]}
    assert pending_ids == {second.id}
    approving_the_old_one = client.post(f"/api/memory/proposals/{first.id}", json={"approve": True})
    assert approving_the_old_one.status_code == 409
    still_pending = client.post(f"/api/memory/proposals/{second.id}", json={"approve": True})
    assert still_pending.status_code == 200


# --- submit_rewrite: the newer rewrite wins, and a race with a hand edit is named ---------


async def test_a_new_rewrite_supersedes_the_waiting_one_and_nothing_else(deps):
    from_chat = deps.store.proposals.create(
        agent_id=deps.agent.id, kind=USER_FACT, name="a", body="ghi trong chat", source="chat"
    )
    older = await submit_rewrite(deps, "- A.", "- A.\n- B.", "", [], TODAY)
    newer = await submit_rewrite(deps, "- A.", "- A.\n- C.", "", [], TODAY)

    assert deps.store.proposals.get(older.proposal.id).status == SUPERSEDED
    assert deps.store.proposals.get(newer.proposal.id).status == PENDING
    assert deps.store.proposals.get(from_chat.id).status == PENDING


async def test_a_hand_edit_during_an_autonomous_rewrite_is_reported_stale(deps_factory):
    deps = deps_factory(autonomous_default=True)
    memory = deps.agent.memory_file
    # Written by hand while the model was still working from "- A.".
    agent_store.write_memory_md(memory, "- A.\n- Ghi tay.")

    outcome = await submit_rewrite(deps, "- A.", "- A.\n- B.", "", [], TODAY)

    assert outcome.summary == texts.CONSOLIDATE_STALE
    assert outcome.proposal.status == SUPERSEDED
    assert agent_store.read_memory_md(memory) == "- A.\n- Ghi tay."


def test_undo_writes_directly_and_is_not_blocked_by_the_gate(client, deps):
    """The web's undo goes through the plain memory-write route, not `_write`, so a
    superseded or stale proposal never stops a person from reverting by hand."""
    memory = deps.agent.memory_file
    agent_store.write_memory_md(memory, "- Sau khi áp dụng.")
    restored = client.put(f"/api/agents/{deps.agent.id}/memory", json={"memory_md": "- Bản cũ."})
    assert restored.status_code == 200
    assert agent_store.read_memory_md(memory) == "- Bản cũ."


# --- GET /memory/user stale field -----------------------------------------------------------


def test_get_user_memory_reports_stale_against_the_ninety_day_threshold(client, deps):
    now = datetime.now()
    user_store.write_fact(
        deps.settings.user_dir,
        "moi",
        "Mới",
        "preference",
        "x",
        "owner",
        "chat",
        now=now - timedelta(days=10),
    )
    user_store.write_fact(
        deps.settings.user_dir,
        "cu",
        "Cũ",
        "preference",
        "y",
        "owner",
        "chat",
        now=now - timedelta(days=100),
    )

    body = client.get("/api/memory/user").json()
    stale_by_name = {f["name"]: f["stale"] for f in body["facts"]}
    assert stale_by_name["moi"] is False
    assert stale_by_name["cu"] is True
