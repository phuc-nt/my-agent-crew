"""Reviewing the shared user facts alongside a memory rewrite.

The facts are shared by the whole crew, so a job forgetting or rewriting one on its own
would affect agents that never asked for it: every action here waits for approval, however
the agent is configured. There is no autonomous path, unlike the memory rewrite next to it.
"""

from __future__ import annotations

import json
import logging
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
MAX_BODY_CHARS = 400
MAX_ACTIONS = 10
MAX_REASON_CHARS = 300
FORGET, UPDATE = "forget", "update"


@dataclass(frozen=True)
class FactReview:
    """What one review pass did: proposals actually created, actions skipped because they
    named an unknown fact or asked for a no-op, and whether the model's reply was usable
    at all."""

    created: int = 0
    skipped: int = 0
    errored: bool = False


def _order_facts(facts: list[user_store.Fact], today: date) -> list[user_store.Fact]:
    """Stale facts first, oldest first, then the rest newest first: what most likely needs
    a decision goes in front of the cut at `MAX_FACTS`, not behind it. A fact whose date
    does not parse sorts as the oldest, as `is_stale` already counts it stale."""

    def day(fact: user_store.Fact) -> date:
        return fact_dates.updated_day(fact.updated) or date.min

    stale = fact_dates.stale_facts(facts, today)
    stale_names = {f.name for f in stale}
    fresh = [f for f in facts if f.name not in stale_names]
    return sorted(stale, key=day) + sorted(fresh, key=day, reverse=True)


def _facts_block(facts: list[user_store.Fact], more: int) -> str:
    """One line per fact, its body flattened and cut, and the facts left out counted
    rather than dropped in silence."""
    lines = [
        f"- {f.name} ({f.updated[:10]}) — {f.description}: "
        + " ".join(f.body.split())[:MAX_BODY_CHARS]
        for f in facts
    ]
    if more:
        lines.append(texts.FACT_REVIEW_MORE.format(count=more))
    return "\n".join(lines)


async def _ask_model(deps: AgentDeps, facts_block: str, notes: str) -> Completion | None:
    prompt = Message(
        role="user", content=texts.FACT_REVIEW_PROMPT.format(facts=facts_block, notes=notes)
    )
    chain = MeteredChain(deps.chain, deps.store, deps.agent.id, "consolidate")
    completion: Completion | None = None
    async for item in chain.stream([prompt], []):
        if isinstance(item, Completion):
            completion = item
    return completion


def _actions(text: str) -> list[dict] | None:
    """The first JSON array anywhere in the reply, or `None` when there is none at all.

    The model may wrap the array in a code fence or a sentence, so each `[` is tried in
    turn until one opens a whole array. Items that are not objects are dropped: an empty
    array, or one with nothing usable in it, means nothing to do rather than a broken reply.
    """
    decoder = json.JSONDecoder()
    start = text.find("[")
    while start != -1:
        try:
            loaded, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            start = text.find("[", start + 1)
            continue
        return [item for item in loaded if isinstance(item, dict)]
    return None


async def review_user_facts(
    deps: AgentDeps, facts: list[user_store.Fact], notes: str, today: date
) -> FactReview:
    """Ask the model which of the person's facts a contradiction or staleness has caught
    up with, and turn each answer into an always-pending proposal.

    `notes` is the recent-notes block the rewrite prompt already carries, so both calls
    read the same days under the same budget. A skipped action never raises: an unknown
    name, an update with no real change, or a duplicate of a proposal already pending is
    simply not worth a card, not a failure.
    """
    ordered = _order_facts(facts, today)
    shown = ordered[:MAX_FACTS]
    completion = await _ask_model(deps, _facts_block(shown, len(ordered) - len(shown)), notes)
    if completion is None:
        return FactReview(errored=True)

    actions = _actions(completion.message.content)
    if actions is None:
        logger.warning("fact review returned no JSON array for agent %s", deps.agent.id)
        return FactReview(errored=True)

    # Only the facts the model was shown: a name past the cut is one it never read.
    by_name = {f.name: f for f in shown}
    created = skipped = 0
    for action in actions[:MAX_ACTIONS]:
        if _apply_action(deps, action, by_name):
            created += 1
        else:
            skipped += 1
    return FactReview(created=created, skipped=skipped)


def _text(action: dict, key: str) -> str:
    value = action.get(key)
    return value.strip() if isinstance(value, str) else ""


def _apply_action(deps: AgentDeps, action: dict, by_name: dict[str, user_store.Fact]) -> bool:
    fact = by_name.get(_text(action, "name"))
    if fact is None:
        return False
    if action.get("action") == FORGET:
        kind, body = USER_FORGET, fact.body
    elif action.get("action") == UPDATE:
        kind, body = USER_FACT, _text(action, "body")
        if not body or body == fact.body:
            return False
    else:
        return False

    if deps.store.proposals.find_pending(deps.agent.id, kind, fact.name, body) is not None:
        return False  # an identical pending proposal already covers this
    proposal = deps.store.proposals.create(
        agent_id=deps.agent.id,
        kind=kind,
        name=fact.name,
        description=fact.description,
        type=fact.type,
        body=body,
        source=SOURCE,
        reasons=_text(action, "reason")[:MAX_REASON_CHARS],
    )
    # One live hygiene proposal per fact, whatever its kind: a new forget replaces a
    # pending update of the same fact and the other way round, never shown side by side.
    deps.store.proposals.supersede(
        deps.agent.id, source=SOURCE, name=fact.name, keep_id=proposal.id
    )
    return True


async def review_for_master(deps: AgentDeps, notes: str, today: date) -> str:
    """The fact review a consolidation runs after its rewrite, as a line for its summary.

    Only the agent the person talks to runs it, and only when there is at least one fact,
    since those facts are shared by the whole crew rather than owned by whichever agent
    happened to consolidate. Empty when there was nothing to run, or nothing worth
    mentioning once it ran.
    """
    profile = deps.agent
    if not profile.is_master:
        return ""
    facts = user_store.list_facts(profile.settings.user_dir)
    if not facts:
        return ""
    try:
        review = await review_user_facts(deps, facts, notes, today)
    except Exception:  # the rewrite already succeeded; a broken review must not lose it
        logger.exception("fact review failed for agent %s", profile.id)
        return texts.FACT_REVIEW_FAILED
    if review.errored:
        return texts.FACT_REVIEW_BROKEN_JSON
    if review.created:
        return texts.FACT_REVIEW_CREATED.format(count=review.created)
    return ""
