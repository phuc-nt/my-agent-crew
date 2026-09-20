"""Rewriting an agent's `MEMORY.md` from its own daily notes.

Memory grows by appending, so it drifts towards a long list of things that were true
once. Consolidation asks the model to rewrite the file: keep what still holds, merge
repeats, drop what only mattered for a day. The result is a proposal rather than a write,
because a rewrite can lose something and nobody is watching a scheduled job. An agent
marked `autonomous` applies it immediately, and the proposal keeps the previous text so
one step back is always possible.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.events import AssistantMessageEvent
from my_agent_crew.agents.context import MAX_SECTION_CHARS
from my_agent_crew.llm.types import Completion, Message
from my_agent_crew.memory import agent_store
from my_agent_crew.memory.proposals_apply import apply_proposal
from my_agent_crew.store.memory_proposals import AGENT_MEMORY_REWRITE, MemoryProposal
from my_agent_crew.store.runs import DONE, FAILED, RunRecord

if TYPE_CHECKING:  # the loop imports memory, not the other way round
    from my_agent_crew.agent.loop import AgentDeps

logger = logging.getLogger(__name__)

MAX_NOTES = 7
MAX_INPUT_CHARS = 40000
JOB_SOURCE = "memory:consolidate"


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


async def _ask_model(deps: AgentDeps, memory: str, notes: str) -> Completion | None:
    prompt = Message(
        role="user", content=texts.CONSOLIDATE_PROMPT.format(memory=memory, notes=notes)
    )
    completion: Completion | None = None
    async for item in deps.chain.stream([prompt], []):
        if isinstance(item, Completion):
            completion = item
    return completion


async def consolidate_memory(deps: AgentDeps, hub: ActivityHub) -> MemoryProposal | None:
    """Rewrite one agent's `MEMORY.md`, as a run so its cost and outcome are visible.

    Returns the proposal it created, or `None` when there was nothing worth rewriting.
    """
    profile = deps.agent
    run = hub.start(
        profile.id, JOB_SOURCE, texts.CONSOLIDATE_RUN_TITLE.format(agent=profile.name), None
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

    current = agent_store.read_memory_md(profile.memory_file).strip()
    notes = notes_text(recent_notes(profile.memory_dir), MAX_INPUT_CHARS - len(current))
    completion = await _ask_model(deps, current, notes)
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
    new_memory = completion.message.content.strip()[:MAX_SECTION_CHARS]
    if not new_memory or new_memory == current:
        hub.finish(run, status=DONE, summary=texts.CONSOLIDATE_UNCHANGED)
        return None

    proposal = deps.store.proposals.create(
        agent_id=profile.id,
        kind=AGENT_MEMORY_REWRITE,
        name=profile.memory_file.name,
        description=texts.CONSOLIDATE_JOB_NAME,
        body=new_memory,
        source=JOB_SOURCE,
        previous_body=current,
    )
    if profile.settings.autonomous_default:
        proposal = apply_proposal(
            deps.store,
            proposal.id,
            approve=True,
            user_dir=profile.settings.user_dir,
            memory_files={profile.id: profile.memory_file},
        )
        hub.finish(run, status=DONE, summary=texts.CONSOLIDATE_APPLIED)
    else:
        hub.finish(run, status=DONE, summary=texts.CONSOLIDATE_PROPOSED)
    return proposal
