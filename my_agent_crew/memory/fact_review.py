"""Reviewing the shared user facts alongside a memory rewrite.

Only the master runs this, and only when the person has at least one fact recorded: those
facts are shared by the whole crew, so a job forgetting or rewriting one on its own would
affect agents that never asked for the change. Every action this produces waits for
approval regardless of how the agent is configured — there is no autonomous path here at
all, unlike the memory rewrite next to it.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from my_agent_crew import texts
from my_agent_crew.llm.metered_chain import MeteredChain
from my_agent_crew.llm.types import Completion, Message
from my_agent_crew.memory import fact_dates, user_store
from my_agent_crew.store.memory_proposals import USER_FACT, USER_FORGET

if TYPE_CHECKING:  # the loop imports memory, not the other way round
    from my_agent_crew.agent.loop import AgentDeps

logger = logging.getLogger(__name__)

SOURCE = "memory:hygiene"
MAX_FACTS = 60
MAX_ACTIONS = 10
FORGET, UPDATE = "forget", "update"

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class FactReview:
    """What one review pass did: proposals actually created, actions skipped because they
    named an unknown fact or asked for a no-op, and whether the model's reply was usable
    at all."""

    created: int = 0
    skipped: int = 0
    errored: bool = False


def _order_facts(facts: list[user_store.Fact], today: date) -> list[user_store.Fact]:
    """Stale facts first, then the rest newest-first: what is most likely to need a
    decision goes in front of the truncation at `MAX_FACTS`, not behind it."""
    stale = fact_dates.stale_facts(facts, today)
    stale_names = {f.name for f in stale}
    fresh = [f for f in facts if f.name not in stale_names]
    return [*stale, *fresh][:MAX_FACTS]


def _facts_block(facts: list[user_store.Fact]) -> str:
    return "\n".join(f"- {f.name}: {f.body} ({f.updated})" for f in facts)


def _notes_block(notes: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"## {day}\n{text}" for day, text in notes)


async def _ask_model(deps: AgentDeps, facts_block: str, notes_block: str) -> Completion | None:
    prompt = Message(
        role="user",
        content=texts.FACT_REVIEW_PROMPT.format(facts=facts_block, notes=notes_block),
    )
    chain = MeteredChain(deps.chain, deps.store, deps.agent.id, "consolidate")
    completion: Completion | None = None
    async for item in chain.stream([prompt], []):
        if isinstance(item, Completion):
            completion = item
    return completion


def _actions(text: str) -> list[dict] | None:
    """The action list in the model's reply, or `None` when it cannot be read at all.

    A JSON value that parses but is not a list, or a list with no dict in it, is treated
    the same as nothing to do rather than an error: the model said something coherent, it
    just had no actions to propose.
    """
    match = _FENCE.search(text)
    body = match.group(1).strip() if match else text.strip()
    try:
        loaded = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, list):
        return None
    return [item for item in loaded if isinstance(item, dict)]


async def review_user_facts(
    deps: AgentDeps, facts: list[user_store.Fact], notes: list[tuple[str, str]], today: date
) -> FactReview:
    """Ask the model which of the person's facts a contradiction or staleness has caught
    up with, and turn each answer into an always-pending proposal.

    A skipped action never raises: an unknown name, an update with no real change, or a
    duplicate of a proposal already pending is simply not worth a card, not a failure.
    """
    ordered = _order_facts(facts, today)
    completion = await _ask_model(deps, _facts_block(ordered), _notes_block(notes))
    if completion is None:
        return FactReview(errored=True)

    actions = _actions(completion.message.content)
    if actions is None:
        logger.warning("fact review returned unparseable JSON for agent %s", deps.agent.id)
        return FactReview(errored=True)

    by_name = {f.name: f for f in facts}
    created = skipped = 0
    for action in actions[:MAX_ACTIONS]:
        outcome = _apply_action(deps, action, by_name)
        if outcome:
            created += 1
        else:
            skipped += 1
    return FactReview(created=created, skipped=skipped)


def _apply_action(deps: AgentDeps, action: dict, by_name: dict[str, user_store.Fact]) -> bool:
    kind = action.get("action")
    name = action.get("name")
    reason = str(action.get("reason", ""))
    fact = by_name.get(name) if isinstance(name, str) else None
    if fact is None:
        return False

    if kind == FORGET:
        body = fact.body
        proposal_kind = USER_FORGET
    elif kind == UPDATE:
        body = str(action.get("body", "")).strip()
        if not body or body == fact.body:
            return False
        proposal_kind = USER_FACT
    else:
        return False

    if deps.store.proposals.find_pending(deps.agent.id, proposal_kind, name, body) is not None:
        return False  # an identical pending proposal already covers this

    proposal = deps.store.proposals.create(
        agent_id=deps.agent.id,
        kind=proposal_kind,
        name=name,
        description=fact.description,
        type=fact.type,
        body=body,
        source=SOURCE,
        reasons=reason,
    )
    # A different body for the same fact+kind replaces what was pending before, so the
    # panel never shows two cards proposing two different rewrites of the same fact.
    deps.store.proposals.supersede(
        deps.agent.id, kind=proposal_kind, source=SOURCE, name=name, keep_id=proposal.id
    )
    return True
