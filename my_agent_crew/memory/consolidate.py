"""Rewriting an agent's `MEMORY.md` from its own daily notes.

Memory grows by appending, so it drifts towards a long list of things that were true
once. Consolidation asks the model to rewrite the file: keep what still holds, merge
repeats, drop what only mattered for a day. The result is a proposal rather than a write,
because a rewrite can lose something and nobody is watching a scheduled job. What happens
to that proposal — applied straight away or left for a person — is decided by
`rewrite_proposal.submit_rewrite`, from the two texts rather than the model's own account
of what it did. For the master, and only when the person has facts recorded, a second
model call reviews those facts too; unlike the memory rewrite, its proposals never
auto-apply, since the facts it touches are shared by the whole crew.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.events import AssistantMessageEvent
from my_agent_crew.agents.context import MAX_SECTION_CHARS
from my_agent_crew.llm.metered_chain import MeteredChain
from my_agent_crew.llm.types import Completion, Message
from my_agent_crew.memory import agent_store, fact_dates
from my_agent_crew.memory.fact_review import review_for_master
from my_agent_crew.memory.rewrite_proposal import JOB_SOURCE, submit_rewrite
from my_agent_crew.store.memory_proposals import MemoryProposal
from my_agent_crew.store.runs import DONE, FAILED, RunRecord

if TYPE_CHECKING:  # the loop imports memory, not the other way round
    from my_agent_crew.agent.loop import AgentDeps

logger = logging.getLogger(__name__)

MAX_NOTES = 7
MAX_INPUT_CHARS = 40000


def recent_notes(memory_dir: Path, limit: int = MAX_NOTES) -> list[tuple[str, str]]:
    """The newest days first, as `(day, text)`. Empty notes are left out.

    The limit counts calendar days, not files: an agent that writes several notes a day
    would otherwise get a handful of hours instead of a week of them.
    """
    kept: list[tuple[str, str]] = []
    days: set[str] = set()
    for note in agent_store.list_notes(memory_dir):
        if note.date not in days and len(days) == limit:
            break
        text = agent_store.read_note(memory_dir, note.day).strip()
        if text:
            kept.append((note.day, text))
            days.add(note.date)
    return kept


def notes_text(notes: list[tuple[str, str]], budget: int) -> str:
    """Newest days fit first; the oldest are dropped when the budget runs out, since a
    truncated old note is worth less to the rewrite than a whole recent one."""
    kept: list[str] = []
    for day, text in notes:
        block = f"## {day}\n{text}"
        budget -= len(block)
        if budget < 0:
            break
        kept.append(block)
    return "\n\n".join(kept)


def has_newer_notes(memory_file: Path, memory_dir: Path) -> bool:
    """Nothing written since the last rewrite means nothing to fold in."""
    if not memory_file.is_file():
        return bool(agent_store.list_notes(memory_dir))
    cutoff = memory_file.stat().st_mtime
    return any(
        (memory_dir / f"{note.day}.md").stat().st_mtime > cutoff
        for note in agent_store.list_notes(memory_dir)
    )


def _review_block(lines: list[str], more: int) -> str:
    if not lines:
        return texts.REVIEW_NONE
    block = "\n".join(lines)
    return f"{block}\n{texts.REVIEW_MORE.format(count=more)}" if more else block


async def _ask_model(deps: AgentDeps, memory: str, notes: str, today: date) -> Completion | None:
    review = fact_dates.review_list(memory, today)
    prompt = Message(
        role="user",
        content=texts.CONSOLIDATE_PROMPT.format(
            memory=memory,
            notes=notes,
            today=today.isoformat(),
            undated=_review_block(review.undated, review.more_undated),
            stale=_review_block(review.stale, review.more_stale),
        ),
    )
    # Upkeep belongs to no conversation; the run keeps a copy for the activity rail only.
    chain = MeteredChain(deps.chain, deps.store, deps.agent.id, "consolidate")
    completion: Completion | None = None
    async for item in chain.stream([prompt], []):
        if isinstance(item, Completion):
            completion = item
    return completion


async def consolidate_memory(
    deps: AgentDeps, hub: ActivityHub, source: str = JOB_SOURCE
) -> MemoryProposal | None:
    """Rewrite one agent's `MEMORY.md`, as a run so its cost and outcome are visible.

    `source` is the scheduled job's own when a job asked, so the job shows its last run.
    Returns the proposal it created, or `None` when there was nothing worth rewriting.
    """
    profile = deps.agent
    run = hub.start(
        profile.id, source, texts.CONSOLIDATE_RUN_TITLE.format(agent=profile.name), None
    )
    try:
        return await _consolidate(deps, hub, run)
    except Exception as exc:  # a failed rewrite leaves the file exactly as it was
        logger.exception("consolidation failed for agent %s", profile.id)
        hub.finish(run, status=FAILED, summary=str(exc)[:160])
        raise


async def _consolidate(deps: AgentDeps, hub: ActivityHub, run: RunRecord) -> MemoryProposal | None:
    profile = deps.agent
    if not has_newer_notes(profile.memory_file, profile.memory_dir):
        hub.finish(run, status=DONE, summary=texts.CONSOLIDATE_NOTHING_NEW)
        return None

    today = date.today()
    current = agent_store.read_memory_md(profile.memory_file).strip()
    notes = recent_notes(profile.memory_dir)
    notes_block = notes_text(notes, MAX_INPUT_CHARS - len(current))
    completion = await _ask_model(deps, current, notes_block, today)
    if completion is None:
        hub.finish(run, status=FAILED, summary=texts.CONSOLIDATE_EMPTY)
        return None

    hub.record(
        run,
        AssistantMessageEvent(
            message_id=0,
            content=completion.message.content,
            tool_calls=[],
            provider=completion.provider,
            model=completion.model,
            cost_usd=completion.usage.cost_usd,
        ),
        time.monotonic(),
    )
    # Reasons are split off before anything is truncated: a long reasons list must not eat
    # into the memory body's own character budget.
    raw_body, reasons = fact_dates.split_reasons(completion.message.content.strip())
    new_memory = raw_body[:MAX_SECTION_CHARS]
    proposal: MemoryProposal | None = None
    if not new_memory or new_memory == current:
        summary = texts.CONSOLIDATE_UNCHANGED
    else:
        outcome = await submit_rewrite(deps, current, new_memory, reasons, notes, today)
        summary = outcome.summary
        proposal = outcome.proposal

    addendum = await review_for_master(deps, notes_block, today)
    hub.finish(run, status=DONE, summary=f"{summary} {addendum}".strip())
    return proposal
