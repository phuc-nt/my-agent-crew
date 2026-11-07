"""A weekly rewrite of an agent's memory that the gate held for the person is told to the
agent's channel once, by the run that held it (`scheduler/proposal_notice.py`): nothing else
said a rewrite waited, and the next week's superseded it unread. A rewrite the gate let
through, one an earlier run left waiting, and a run that failed are not told this way."""

from __future__ import annotations

from datetime import datetime

from my_agent_crew import texts
from my_agent_crew import texts_job_failure as words
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agents.profile import consolidate_schedule
from my_agent_crew.scheduler import Scheduler
from my_agent_crew.store.memory_proposals import AGENT_MEMORY_REWRITE, APPROVED, PENDING
from my_agent_crew.store.runs import DONE
from tests.test_memory_validity import rewrite
from tests.test_scheduler import with_schedules

JOB = "default/memory-consolidate"


class Chat:
    def __init__(self) -> None:
        self.said: list[tuple[str, str]] = []

    async def __call__(self, agent_id: str, text: str) -> bool:
        self.said.append((agent_id, text))
        return True


def clock_for(deps) -> tuple[Scheduler, Chat]:
    with_schedules(deps, consolidate_schedule("30 3 * * 0"))
    chat = Chat()
    sched = Scheduler(
        {"default": deps}, ActivityHub(deps.store), clock=lambda: datetime(2026, 11, 8), notify=chat
    )
    return sched, chat


async def test_a_held_rewrite_is_told_once_to_the_agents_channel(deps_factory):
    deps = rewrite(deps_factory, "- Sếp thích trà.\n- Sếp ngủ trước 23h.", "- Sếp thích trà.")
    sched, chat = clock_for(deps)

    run = await sched.run_job(JOB)

    [proposal] = deps.store.proposals.list()
    assert (run.status, proposal.status, proposal.kind) == (DONE, PENDING, AGENT_MEMORY_REWRITE)
    held = texts.CONSOLIDATE_HELD.format(why=texts.HELD_REMOVED.format(count=1))
    assert run.summary.startswith(held)
    told = words.MEMORY_HELD.format(agent=deps.agent.name, why=run.summary)
    assert chat.said == [("default", told)]


async def test_a_rewrite_the_gate_let_through_is_not_told(deps_factory):
    deps = rewrite(deps_factory, "- Sếp thích trà.", "- Sếp thích trà.\n- Sếp ngủ trước 23h.")
    sched, chat = clock_for(deps)

    await sched.run_job(JOB)

    assert [p.status for p in deps.store.proposals.list(None)] == [APPROVED]
    assert chat.said == []


async def test_a_rewrite_an_earlier_run_left_waiting_is_not_told_again(deps_factory):
    deps = rewrite(deps_factory, "- Sếp thích trà.", "- Sếp thích trà.")
    deps.store.proposals.create(
        agent_id="default", kind=AGENT_MEMORY_REWRITE, body="- x", previous_body="- Sếp thích trà."
    )
    with deps.store.proposals._lock:  # made before this run started
        deps.store.proposals._conn.execute(
            "UPDATE memory_proposals SET created_at = '2026-11-01T03:30:00+00:00'"
        )
    sched, chat = clock_for(deps)

    run = await sched.run_job(JOB)

    assert run.summary.startswith(texts.CONSOLIDATE_UNCHANGED)
    assert chat.said == []
