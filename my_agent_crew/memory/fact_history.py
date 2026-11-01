"""The versions of a fact that are no longer its current one.

A replaced or retracted fact is not thrown away: its last version is appended to
`facts/.history/<name>.jsonl`, one JSON object per line, with when and why it stopped
being current. That is what answers "what did we hold true on that day" (`as_of`) and
what lets a retraction be undone by hand. Only a purge, asked for by the person, erases
it. The directory starts with a dot so nothing that lists facts (`*.md`) ever sees it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from my_agent_crew.memory.fact_model import Fact, day_of, from_mapping, front_matter

HISTORY_DIR = ".history"
SUPERSEDED, RETRACTED = "superseded", "retracted"


@dataclass(frozen=True)
class Version:
    """A past version of a fact and how it ended."""

    fact: Fact
    ended_at: str
    why: str

    def to_dict(self) -> dict:
        return {**self.fact.to_dict(), "ended_at": self.ended_at, "why": self.why}


def history_path(facts_dir: Path, name: str) -> Path:
    return facts_dir / HISTORY_DIR / f"{name}.jsonl"


def append(facts_dir: Path, fact: Fact, ended_at: str, why: str) -> None:
    path = history_path(facts_dir, fact.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {**front_matter(fact), "body": fact.body, "ended_at": ended_at, "why": why}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def versions(facts_dir: Path, name: str) -> list[Version]:
    """Oldest first. A line that does not parse is skipped, not fatal."""
    path = history_path(facts_dir, name)
    if not path.is_file():
        return []
    out: list[Version] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict):
            fact = from_mapping(data, name, str(data.get("body", "")))
            out.append(Version(fact, str(data.get("ended_at", "")), str(data.get("why", ""))))
    return out


def last_version(facts_dir: Path, name: str) -> int:
    return max((v.fact.version for v in versions(facts_dir, name)), default=0)


def purge(facts_dir: Path, name: str) -> bool:
    path = history_path(facts_dir, name)
    if not path.is_file():
        return False
    path.unlink()
    return True


def retracted(facts_dir: Path) -> list[Version]:
    """The last version of each fact that was retracted and has no current file."""
    directory = facts_dir / HISTORY_DIR
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.jsonl")):
        if (facts_dir / f"{path.stem}.md").is_file():
            continue
        past = versions(facts_dir, path.stem)
        if past and past[-1].why == RETRACTED:
            out.append(past[-1])
    return out


def _span(fact: Fact, ended_at: str, first: bool) -> tuple[date | None, date | None, bool]:
    """(first day, last day, last day inclusive). Without its own first day a version
    holds from when it was written, except the first one, whose start is unknown; without
    its own last day it holds until the day it ended, that day excluded."""
    start = day_of(fact.valid_from) or (None if first else day_of(fact.updated))
    end = day_of(fact.valid_until)
    if end is not None:
        return start, end, True
    return start, day_of(ended_at), False


def as_of(current: Fact | None, past: list[Version], day: date) -> Fact | None:
    """The version that held on `day`: the newest whose span covers it, or None."""
    spans = [(v.fact, *_span(v.fact, v.ended_at, i == 0)) for i, v in enumerate(past)]
    if current is not None:
        spans.append((current, *_span(current, "", not past)))
    for fact, start, end, inclusive in reversed(spans):
        if start is not None and day < start:
            continue
        if end is not None and (day > end if inclusive else day >= end):
            continue
        return fact
    return None
