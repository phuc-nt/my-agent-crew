"""Telling the person that a rewrite of an agent's memory waits for them.

A rewrite the gate held (a line dropped, a date from nowhere, over budget) sits as a
pending proposal until someone decides it, and nothing else said so: the rewrite of the
next week superseded it unread. So the run that held one tells the agent's channel once,
in the same way a failed job is told (`failure_notice.say`).
"""

from __future__ import annotations

from my_agent_crew import texts_job_failure as words
from my_agent_crew.activity.step_previews import preview
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.scheduler.failure_notice import Notify, say
from my_agent_crew.scheduler.jobs import Job
from my_agent_crew.store.memory_proposals import AGENT_MEMORY_REWRITE
from my_agent_crew.store.runs import DONE, RunRecord


def held_rewrite(deps: AgentDeps, run: RunRecord) -> bool:
    """Whether this run left a rewrite of the agent's memory waiting: one still pending
    and made no earlier than the run started. A rewrite the gate let through is approved
    by now, and one an earlier run left is not this run's to tell."""
    if run.status != DONE:
        return False
    return any(
        p.agent_id == run.agent_id
        and p.kind == AGENT_MEMORY_REWRITE
        and p.created_at >= run.started_at
        for p in deps.store.proposals.list()
    )


async def tell_held(job: Job, deps: AgentDeps, run: RunRecord, notify: Notify | None) -> bool:
    """Says a held rewrite to the agent's channel: whether the channel took it."""
    if not held_rewrite(deps, run):
        return False
    text = words.MEMORY_HELD.format(agent=preview(deps.agent.name), why=preview(run.summary))
    return await say(job, text, notify)
