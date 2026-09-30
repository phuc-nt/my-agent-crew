"""`for_parent_call`'s optional `source`: a bare tool call id is only unique within the
parent that made it up, so two different parents could hand out the same one — before
`llm/openai_compat.py`'s uuid fix, or still, from a row written before that fix shipped.
Passing the parent's own run source narrows the search to the child that parent actually
opened, so a same-id child belonging to someone else's conversation is never returned."""

from __future__ import annotations

import pytest

from my_agent_crew.store import Store
from my_agent_crew.store.runs import RunRecord

CALL = "d1"


def _run(run_id: str, conv_id: str, source: str) -> RunRecord:
    return RunRecord(
        id=run_id,
        agent_id="worker",
        conversation_id=conv_id,
        source=source,
        title="",
        status="done",
        started_at="2026-01-01T00:00:00+00:00",
    )


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


def test_two_parents_sharing_a_call_id_each_find_only_their_own_child(store: Store) -> None:
    """The exact collision this exists for: parent A and parent B both delegate, and by
    chance (or because the ids predate the uuid fix) both calls are named "d1"."""
    parent_a = store.create()
    parent_b = store.create()
    child_a = store.create(parent_call_id=CALL)
    child_b = store.create(parent_call_id=CALL)
    store.runs.save(_run("run-a", child_a.id, f"delegate:{parent_a.id}"))
    store.runs.save(_run("run-b", child_b.id, f"delegate:{parent_b.id}"))

    found_a = store.for_parent_call(CALL, f"delegate:{parent_a.id}")
    found_b = store.for_parent_call(CALL, f"delegate:{parent_b.id}")

    assert found_a is not None and found_a.id == child_a.id
    assert found_b is not None and found_b.id == child_b.id


def test_an_unknown_source_finds_nothing(store: Store) -> None:
    child = store.create(parent_call_id=CALL)
    store.runs.save(_run("run-1", child.id, "delegate:some-parent"))

    assert store.for_parent_call(CALL, "delegate:a-different-parent") is None


def test_a_child_with_no_run_yet_is_not_found_by_source(store: Store) -> None:
    """The child row exists (`_open_child` writes it first), but its `_run_child` task has
    not run far enough to record a run row yet. Scoped by source, it is invisible until it
    does; the caller's own `have_ids` guard is what decides whether to open a second child
    in the meantime, not this lookup."""
    store.create(parent_call_id=CALL)

    assert store.for_parent_call(CALL, "delegate:parent-1") is None


def test_the_one_argument_form_still_searches_by_id_alone(store: Store) -> None:
    """Callers with nothing to scope by — or old rows from before runs carried a
    conversation-specific source — keep the original, unscoped behaviour."""
    child = store.create(parent_call_id=CALL)

    assert store.for_parent_call(CALL) is not None
    assert store.for_parent_call(CALL).id == child.id


def test_a_delegate_resumed_after_interruption_finds_only_its_own_child(store: Store) -> None:
    """The ordinary, non-colliding case: one parent, one child, the run already recorded by
    the time the parent's turn is interrupted and resumed."""
    parent = store.create()
    child = store.create(parent_call_id=CALL)
    store.runs.save(_run("run-1", child.id, f"delegate:{parent.id}"))

    again = store.for_parent_call(CALL, f"delegate:{parent.id}")

    assert again is not None and again.id == child.id
