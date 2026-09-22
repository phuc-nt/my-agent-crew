"""Building wiki pages out of an agent's daily notes, as a scheduled job.

Consolidation rewrites `MEMORY.md` so it stays short. This does the other half: it gathers
what the notes say about each *thing* onto a page named after that thing, so a question
about the Eco Retreat deadline has one place to be answered from instead of eleven notes
to be ranked.

Like consolidation it produces a proposal rather than writing straight away, because
nobody is watching at three in the morning and a compile can get a page wrong. Unlike
consolidation the proposal carries many pages at once, as JSON in the same `body` column,
with what those pages said before in `previous_body` so an undo is still one step.

The model is never allowed to decide whether a page may exist without sources: that check
lives in `wiki_plan.plan_pages` and runs on the reply before anything is proposed.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.events import AssistantMessageEvent
from my_agent_crew.llm.types import Completion, Message
from my_agent_crew.memory import wiki_store
from my_agent_crew.memory.consolidate import MAX_INPUT_CHARS, notes_text, recent_notes
from my_agent_crew.memory.wiki_apply import WIKI_COMPILE, apply_wiki_proposal, capture_previous
from my_agent_crew.memory.wiki_plan import Planned, plan_pages
from my_agent_crew.store.memory_proposals import MemoryProposal
from my_agent_crew.store.runs import DONE, FAILED, RunRecord
from my_agent_crew.tools import wiki_texts as texts

if TYPE_CHECKING:  # the loop imports memory, not the other way round
    from my_agent_crew.agent.loop import AgentDeps

logger = logging.getLogger(__name__)

JOB_SOURCE = "memory:wiki"
#: Enough titles in the description to recognise the batch without reading the JSON.
TITLES_IN_DESCRIPTION = 5


def existing_titles(memory_dir: Path) -> str:
    """The vault as the prompt sees it: names only, so the model extends rather than
    duplicates. Bodies are left out; a compile that re-reads every page would spend its
    whole budget on what it already knows."""
    pages = wiki_store.list_pages(memory_dir)
    if not pages:
        return texts.WIKI_COMPILE_NO_PAGES
    return "\n".join(f"- {page.title} ({page.kind})" for page in pages)


def describe(planned: list[Planned]) -> str:
    titles = [page.title for page in planned[:TITLES_IN_DESCRIPTION]]
    if len(planned) > TITLES_IN_DESCRIPTION:
        titles.append("…")
    return texts.WIKI_COMPILE_DESCRIPTION.format(count=len(planned), titles=", ".join(titles))


async def _ask_model(deps: AgentDeps, pages: str, notes: str) -> Completion | None:
    prompt = Message(
        role="user", content=texts.WIKI_COMPILE_PROMPT.format(pages=pages, notes=notes)
    )
    completion: Completion | None = None
    async for item in deps.chain.stream([prompt], []):
        if isinstance(item, Completion):
            completion = item
    return completion


async def compile_wiki(deps: AgentDeps, hub: ActivityHub) -> MemoryProposal | None:
    """Compile one agent's vault from its notes, as a run so cost and outcome are visible."""
    profile = deps.agent
    run = hub.start(
        profile.id, JOB_SOURCE, texts.WIKI_COMPILE_RUN_TITLE.format(agent=profile.name), None
    )
    try:
        return await _compile(deps, hub, run)
    except Exception as exc:  # a failed compile leaves the vault exactly as it was
        logger.exception("wiki compile failed for agent %s", profile.id)
        hub.finish(run, status=FAILED, summary=str(exc)[:160])
        raise


async def _compile(deps: AgentDeps, hub: ActivityHub, run: RunRecord) -> MemoryProposal | None:
    profile = deps.agent
    notes = recent_notes(profile.memory_dir)
    if not notes:
        hub.finish(run, status=DONE, summary=texts.WIKI_COMPILE_NOTHING_NEW)
        return None

    pages = existing_titles(profile.memory_dir)
    completion = await _ask_model(deps, pages, notes_text(notes, MAX_INPUT_CHARS - len(pages)))
    if completion is None:
        hub.finish(run, status=FAILED, summary=texts.WIKI_COMPILE_EMPTY)
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
    planned = plan_pages(completion.message.content)
    if not planned:
        hub.finish(run, status=DONE, summary=texts.WIKI_COMPILE_EMPTY)
        return None

    proposal = deps.store.proposals.create(
        agent_id=profile.id,
        kind=WIKI_COMPILE,
        name=wiki_store.WIKI_DIRNAME,
        description=describe(planned),
        body=json.dumps([page.to_dict() for page in planned], ensure_ascii=False),
        source=JOB_SOURCE,
        previous_body=json.dumps(capture_previous(profile.memory_dir, planned), ensure_ascii=False),
    )
    if profile.settings.autonomous_default:
        written, linked = apply_wiki_proposal(profile.memory_dir, proposal.body)
        deps.store.proposals.resolve(proposal.id, True)
        hub.finish(
            run,
            status=DONE,
            summary=texts.WIKI_COMPILE_APPLIED.format(count=written, linked=linked),
        )
        return deps.store.proposals.get(proposal.id)
    hub.finish(run, status=DONE, summary=texts.WIKI_COMPILE_PROPOSED.format(count=len(planned)))
    return proposal
