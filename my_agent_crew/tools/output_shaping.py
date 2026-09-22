"""Cutting a long tool output down to a cap without destroying what it means.

Cutting at a character count is what we did before, and it is the worst option for JSON:
the model receives a fragment that no longer parses, so it cannot read the last key and
often retries the whole command. Here a JSON output is cut *by structure* instead — arrays
lose their tail, long strings lose their middle, and the result still parses, so every
top-level key survives even when the body under it shrinks.

Numbers and names are never rewritten. Ledger figures and health readings travel through
this code, and a summary that rounds a number is worse than one that omits a row: an
omitted row is visibly missing, a wrong number is not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from my_agent_crew.texts import (
    OUTPUT_SHAPED_ARRAY,
    OUTPUT_SHAPED_NOTE,
    OUTPUT_SHAPED_STRING,
    OUTPUT_TRUNCATED,
)
from my_agent_crew.tools.output_summary import Summariser, summarise

# Below this there is no room to shape anything and a plain cut is honest.
MIN_SHAPE_CHARS = 200
# An array keeps at least this many items, so a shaped list still shows its element shape.
MIN_ARRAY_ITEMS = 1


@dataclass(frozen=True)
class Shaped:
    """The text to show the model, plus what was done to it, for the run record."""

    text: str
    kind: str  # "none" | "json" | "cut" | "summary"
    original_chars: int
    # What shaping itself cost, when a model was asked to summarise. None everywhere else:
    # structural shaping is free, and zero and unknown are different claims.
    cost_usd: float | None = None

    @property
    def shaped(self) -> bool:
        return self.kind != "none"


def _string(value: str, budget: int) -> str:
    """A long string keeps its head and tail: the head says what it is, the tail usually
    carries the total or the conclusion, and the middle is the repetitive part."""
    if len(value) <= budget:
        return value
    if budget <= 40:
        return value[:budget]
    head = int(budget * 0.7)
    tail = budget - head
    dropped = len(value) - head - tail
    return value[:head] + OUTPUT_SHAPED_STRING.format(dropped=dropped) + value[len(value) - tail :]


def _shrink(value: Any, budget: int) -> Any:
    """One value cut to roughly `budget` characters of rendered JSON."""
    if isinstance(value, str):
        return _string(value, max(budget, 40))
    if isinstance(value, list):
        return _shrink_list(value, budget)
    if isinstance(value, dict):
        return _shrink_dict(value, budget)
    return value  # numbers, booleans and null are never altered


def _shrink_list(value: list[Any], budget: int) -> list[Any]:
    if not value:
        return value
    kept: list[Any] = []
    spent = 0
    for item in value:
        share = max(budget - spent, 0)
        if share <= 0 and len(kept) >= MIN_ARRAY_ITEMS:
            break
        shrunk = _shrink(item, max(share // 2, 80))
        rendered = len(json.dumps(shrunk, ensure_ascii=False))
        if kept and spent + rendered > budget:
            break
        kept.append(shrunk)
        spent += rendered
    dropped = len(value) - len(kept)
    if dropped > 0:
        kept.append(OUTPUT_SHAPED_ARRAY.format(dropped=dropped))
    return kept


def _shrink_dict(value: dict[str, Any], budget: int) -> dict[str, Any]:
    """Every key survives. A mapping's keys are its schema, and a model that cannot see a
    key assumes the data is absent rather than shortened."""
    if not value:
        return value
    share = max(budget // max(len(value), 1), 60)
    return {key: _shrink(item, share) for key, item in value.items()}


def shape_json(text: str, limit: int) -> str | None:
    """`text` cut to `limit` with its structure intact, or None when it is not JSON or
    cannot be brought under the cap this way."""
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(data, dict | list):
        return None
    budget = limit
    # Shrinking overshoots, because the note and the punctuation are not free. Try a couple
    # of tighter budgets before giving up rather than returning something still over cap.
    for _ in range(4):
        shrunk = _shrink(data, budget)
        try:
            rendered = json.dumps(shrunk, ensure_ascii=False, indent=None)
        except (TypeError, ValueError):
            return None
        if len(rendered) <= limit:
            return rendered
        budget = int(budget * 0.6)
        if budget < MIN_SHAPE_CHARS:
            break
    return None


def cut(text: str, limit: int) -> str:
    """A plain cut that lands inside the cap, note included.

    The note is part of what the model reads, so it has to be paid for out of the budget
    rather than added on top of it. A cap is a promise about the context an agent's own
    profile bought; a cut that overshoots it by the length of its own apology is not one.
    """
    keep = max(limit - len(OUTPUT_TRUNCATED.format(dropped=len(text))), 0)
    return text[:keep] + OUTPUT_TRUNCATED.format(dropped=len(text) - keep)


def shape_output(text: str, limit: int) -> Shaped:
    """The one entry point: return `text` unchanged when it fits, shaped as JSON when that
    works, and plainly cut otherwise. Never raises, never returns something over the cap."""
    original = len(text)
    if original <= limit:
        return Shaped(text, "none", original)
    if limit >= MIN_SHAPE_CHARS:
        rendered = shape_json(text, limit - len(OUTPUT_SHAPED_NOTE))
        if rendered is not None:
            return Shaped(rendered + OUTPUT_SHAPED_NOTE, "json", original)
    return Shaped(cut(text, limit), "cut", original)


async def shape_output_async(text: str, limit: int, summariser: Summariser | None) -> Shaped:
    """`shape_output`, with one extra option for text that is not JSON: summarising the
    middle instead of dropping it.

    The order matters. JSON is shaped structurally first and never sent to a model, because
    its numbers are the whole point of it. Only what is left over — logs, reports, pages —
    is worth a summary, and even then a failure falls straight back to the plain cut."""
    shaped = shape_output(text, limit)
    if shaped.kind != "cut" or summariser is None:
        return shaped
    summarised = await summarise(text, limit, summariser)
    if summarised is None:
        return shaped
    return Shaped(summarised.text, "summary", shaped.original_chars, summarised.cost_usd)
