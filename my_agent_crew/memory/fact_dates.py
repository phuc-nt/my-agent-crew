"""Dates inside `MEMORY.md`, computed by code rather than left to the model's judgement.

Every bullet line may carry a `(YYYY-MM-DD)` suffix: the day it was last confirmed true.
A line without one, or one older than `STALE_DAYS`, is a candidate the rewrite prompt must
account for explicitly instead of silently keeping or dropping. The removed/invented-date
checks here are the actual gate: they decide, from the two texts alone, whether a rewrite
is safe to apply without a person looking at it first.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime

from my_agent_crew.memory.wiki_lint import STALE_DAYS

#: A bullet line ending in its confirmation date, e.g. `- Sếp thích trà. (2026-09-29)`.
DATE_SUFFIX = re.compile(r" \((\d{4}-\d{2}-\d{2})\)$")
_BULLET = re.compile(r"^[-*+]\s+")

_MAX_LISTED = 40
_MAX_LINE_CHARS = 200
_REASONS_MAX_CHARS = 4000
# Python's `re.IGNORECASE` does not fold `Ý` onto `Y`: they are different codepoints, not
# a case pair. The model may or may not keep the accent, so both spellings are accepted
# outright rather than relying on case folding to bridge them.
_SEPARATOR = re.compile(r"^---\s*L[YÝ]\s+DO\s*---$", re.IGNORECASE)


@dataclass(frozen=True)
class Review:
    """What the rewrite prompt is asked to look at again: undated lines and stale ones,
    each capped so the prompt cannot grow without bound, with the overflow counted rather
    than silently dropped."""

    undated: list[str]
    stale: list[str]
    more_undated: int = 0
    more_stale: int = 0


def _bullet_lines(memory_text: str) -> list[str]:
    return [line for line in memory_text.splitlines() if _BULLET.match(line.strip())]


def _cap(lines: list[str]) -> tuple[list[str], int]:
    kept = [line[:_MAX_LINE_CHARS] for line in lines[:_MAX_LISTED]]
    return kept, max(0, len(lines) - _MAX_LISTED)


def review_list(memory_text: str, today: date, stale_days: int = STALE_DAYS) -> Review:
    """Bullet lines with no date, and bullet lines dated more than `stale_days` ago.

    A line with a recent date is left out entirely: it is not something the model needs
    to reconsider, and including it would just make the prompt longer for no reason. A
    suffix that is not a real day (`2026-02-30`) counts as no date: the file is written by
    hand and by agents, and one bad line must not fail every consolidation after it.
    """
    undated: list[str] = []
    stale: list[str] = []
    for line in _bullet_lines(memory_text):
        day = _suffix_day(line.strip())
        if day is None:
            undated.append(line.strip())
        elif (today - day).days > stale_days:
            stale.append(line.strip())
    kept_undated, more_undated = _cap(undated)
    kept_stale, more_stale = _cap(stale)
    return Review(kept_undated, kept_stale, more_undated, more_stale)


def _suffix_day(line: str) -> date | None:
    match = DATE_SUFFIX.search(line)
    if match is None:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def updated_day(updated_iso: str) -> date | None:
    """The day of a fact's `updated` stamp, or `None` when it does not parse."""
    try:
        return datetime.fromisoformat(updated_iso).date()
    except ValueError:
        return None


def is_stale(updated_iso: str, today: date, days: int = STALE_DAYS) -> bool:
    """A fact with no parseable `updated` counts as stale: absence of evidence is not
    evidence of freshness, same reasoning as the wiki's own stale check."""
    day = updated_day(updated_iso)
    return day is None or (today - day).days > days


def stale_facts(facts: list, today: date, days: int = STALE_DAYS) -> list:
    """Any object with an `.updated` field; kept generic so both `Fact` and a lightweight
    stand-in used in tests work without a dependency on `user_store` here."""
    return [f for f in facts if is_stale(f.updated, today, days)]


def split_reasons(text: str) -> tuple[str, str]:
    """`(memory, reasons)`, split on the model's own separator line before anything else
    is truncated. Missing the separator is treated as "no reasons given" rather than an
    error, since that was the whole answer's shape before this prompt existed. The line is
    NFC-normalized first: a decomposed `Ý` (`Y` plus a combining accent) would otherwise
    miss the separator and let the reasons land in the memory body."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if _SEPARATOR.match(unicodedata.normalize("NFC", line.strip())):
            body = "\n".join(lines[:i]).strip()
            reasons = "\n".join(lines[i + 1 :]).strip()
            return body, reasons[:_REASONS_MAX_CHARS]
    return text.strip(), ""


def _normalize_key(line: str) -> str:
    """The identity of a line for the purpose of "is this still here": marker, date and
    spacing stripped away, so only what the line actually asserts remains. Deliberately an
    exact match rather than a containment check — see `removed_lines`."""
    stripped = line.strip()
    stripped = _BULLET.sub("", stripped)
    stripped = DATE_SUFFIX.sub("", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped.casefold()


def removed_lines(previous: str, new: str) -> list[str]:
    """Every non-blank line of `previous` whose normalized key is gone from `new`.

    Matching is exact, never "the old line's key is contained in a new line": that
    shortcut would let "Uống cà phê" survive being changed to "Không uống cà phê", exactly
    the kind of silent reversal this check exists to catch.
    """
    new_keys = {_normalize_key(line) for line in new.splitlines() if line.strip()}
    removed = []
    for line in previous.splitlines():
        if not line.strip():
            continue
        if _normalize_key(line) not in new_keys:
            removed.append(line.strip())
    return removed


def invented_dates(previous: str, notes: list[tuple[str, str]], new: str, today: date) -> list[str]:
    """Dates in `new` that come from nowhere: not already in `previous`, not the day of a
    note fed into this prompt, and not today. Catches a model inventing a date by code
    rather than by trusting the prompt was followed."""
    previous_matches = (DATE_SUFFIX.search(line.strip()) for line in previous.splitlines())
    allowed = {match.group(1) for match in previous_matches if match is not None}
    allowed.update(day[:10] for day, _ in notes)
    allowed.add(today.isoformat())

    found: list[str] = []
    seen: set[str] = set()
    for line in new.splitlines():
        match = DATE_SUFFIX.search(line.strip())
        if match is None:
            continue
        day = match.group(1)
        if day not in allowed and day not in seen:
            seen.add(day)
            found.append(day)
    return found
