"""What a new write does to the fact already under its name, decided by code.

Five outcomes, the same every time for the same two facts:

- created: nothing was there;
- confirmed: the same thing again, so only its evidence grows (sources, confirmed day,
  the stronger of the two bases);
- superseded: something different from a basis at least as strong, so the old version
  goes to the history and the new one takes its place;
- disputed: something different from a weaker basis (an agent's inference against what
  the person said), so nothing is overwritten and the person is asked instead.

A write that only says when the new value starts (`valid_from`) also closes the old one
the day before, so on the days in between the old value is still the one that holds.
"""

from __future__ import annotations

from dataclasses import replace

from my_agent_crew.memory.fact_model import AUTHORITY, Fact, day_before

CREATED, CONFIRMED, SUPERSEDED, DISPUTED = "created", "confirmed", "superseded", "disputed"


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def same_claim(old: Fact, new: Fact) -> bool:
    return (
        _norm(old.body) == _norm(new.body)
        and _norm(old.description) == _norm(new.description)
        and old.type == new.type
        and old.valid_from == new.valid_from
        and old.valid_until == new.valid_until
    )


def decide(existing: Fact | None, incoming: Fact) -> str:
    if existing is None:
        return CREATED
    if same_claim(existing, incoming):
        return CONFIRMED
    if incoming.authority < existing.authority:
        return DISPUTED
    return SUPERSEDED


def merged_sources(old: tuple[str, ...], new: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*old, *new)))


def confirmed(existing: Fact, incoming: Fact) -> Fact:
    """The existing fact with the new write's evidence added to it."""
    stronger = max((existing.stands_on, incoming.stands_on), key=AUTHORITY.__getitem__)
    return replace(
        existing,
        basis=stronger,
        sources=merged_sources(existing.sources, incoming.sources),
        confirmed=incoming.updated,
    )


def closed(existing: Fact, incoming: Fact) -> Fact:
    """The old version as the history keeps it: ended the day before the new one starts,
    when the new one says when it starts and the old one had no end of its own."""
    if incoming.valid_from and not existing.valid_until:
        return replace(existing, valid_until=day_before(incoming.valid_from))
    return existing
