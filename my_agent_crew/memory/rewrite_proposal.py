"""The one place a `MEMORY.md` rewrite becomes a proposal.

Creating the row is not the interesting part; deciding whether it is safe to apply without
a person looking at it first is. That decision is made here, from the two texts alone —
never from the model's own claim about what it did — so an `autonomous` agent cannot talk
its way past the gate by simply not mentioning that it dropped a line.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from my_agent_crew import texts
from my_agent_crew.memory import fact_dates
from my_agent_crew.memory.proposals_apply import StaleProposal, apply_proposal
from my_agent_crew.store.memory_proposals import AGENT_MEMORY_REWRITE, MemoryProposal

if TYPE_CHECKING:  # the loop imports memory, not the other way round
    from datetime import date

    from my_agent_crew.agent.loop import AgentDeps

JOB_SOURCE = "memory:consolidate"


@dataclass(frozen=True)
class RewriteOutcome:
    """What `submit_rewrite` did: the proposal in its final state (pending, approved by the
    gate, or superseded by a race with a hand edit) and the one-line run summary for it."""

    proposal: MemoryProposal
    summary: str


async def submit_rewrite(
    deps: AgentDeps,
    current: str,
    new_memory: str,
    reasons: str,
    notes: list[tuple[str, str]],
    today: date,
) -> RewriteOutcome:
    """Create the rewrite proposal, gate it, and act on the gate's answer.

    A rewrite that only adds lines, or only changes a date suffix, still auto-applies for
    an `autonomous` agent, matching what a person reviewing the same diff would wave
    through. A rewrite that drops or rephrases anything, or names a date that traces back
    to neither the previous text, a note fed into the prompt, nor today, always waits for
    approval — the model's own stated reason for dropping a line is shown on the card, but
    it never buys the line skipping review.
    """
    removed = fact_dates.removed_lines(current, new_memory)
    invented = fact_dates.invented_dates(current, notes, new_memory, today)
    if invented:
        note = texts.CONSOLIDATE_INVENTED_DATES.format(dates=", ".join(invented))
        reasons = f"{reasons}\n{note}" if reasons else note

    profile = deps.agent
    proposal = deps.store.proposals.create(
        agent_id=profile.id,
        kind=AGENT_MEMORY_REWRITE,
        name=profile.memory_file.name,
        description=texts.CONSOLIDATE_JOB_NAME,
        body=new_memory,
        source=JOB_SOURCE,
        previous_body=current,
        reasons=reasons,
    )
    deps.store.proposals.supersede(profile.id, kind=AGENT_MEMORY_REWRITE, keep_id=proposal.id)

    if not profile.settings.autonomous_default:
        return RewriteOutcome(proposal, texts.CONSOLIDATE_PROPOSED)
    held = [texts.HELD_REMOVED.format(count=len(removed))] if removed else []
    if invented:
        held.append(texts.HELD_INVENTED.format(count=len(invented)))
    if held:
        return RewriteOutcome(proposal, texts.CONSOLIDATE_HELD.format(why=", ".join(held)))

    try:
        # Off the event loop, as the web decides: the lock may be held by a decision there.
        applied = await asyncio.to_thread(
            apply_proposal,
            deps.store,
            proposal.id,
            approve=True,
            user_dir=profile.settings.user_dir,
            memory_files={profile.id: profile.memory_file},
        )
    except StaleProposal:
        # `apply_proposal` already marked it superseded before re-raising.
        return RewriteOutcome(deps.store.proposals.get(proposal.id), texts.CONSOLIDATE_STALE)
    return RewriteOutcome(applied, texts.CONSOLIDATE_APPLIED)
