"""One remembered fact about the person and what it must be able to answer about itself.

Besides what it says, a fact carries where it came from (`sources`), who stands behind it
(`basis`), when it holds (`valid_from` and `valid_until`, both inclusive days) and which
version of itself it is. These are what decide, by code and not by a model, whether a new
write may replace it (`fact_reconcile`), what the prompt shows today (`fact_index`) and
what was held true on an earlier day (`fact_history.as_of`).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any

# operator: the person wrote it by hand on the web; said: the person said it in a chat;
# inferred: an agent concluded it; extracted: a job or review proposed it unattended.
OPERATOR, SAID, INFERRED, EXTRACTED = "operator", "said", "inferred", "extracted"
BASES = (OPERATOR, SAID, INFERRED, EXTRACTED)
# The person's own word, typed or said, outranks what an agent made of it. Both of the
# person's ways count the same: a correction said in a chat replaces a hand edit.
AUTHORITY = {OPERATOR: 2, SAID: 2, INFERRED: 1, EXTRACTED: 0}
WEB = "web"
DAY = "%Y-%m-%d"
NAME_PATTERN = re.compile(r"^[a-z0-9-]{1,60}$")
FACT_TYPES = ("profile", "preference", "feedback", "project", "reference")


@dataclass(frozen=True)
class Fact:
    """One remembered fact plus who wrote it, how it arrived and when it holds."""

    name: str
    description: str
    type: str
    written_by: str
    source: str
    updated: str
    body: str
    basis: str = ""
    valid_from: str = ""
    valid_until: str = ""
    sources: tuple[str, ...] = ()
    version: int = 1
    confirmed: str = ""

    @property
    def stands_on(self) -> str:
        """The basis, with a fact written before bases existed read as the web's hand edit
        or else as an agent's inference: an old fact keeps being replaceable as before."""
        if self.basis in AUTHORITY:
            return self.basis
        return OPERATOR if self.written_by == WEB else INFERRED

    @property
    def authority(self) -> int:
        return AUTHORITY[self.stands_on]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["sources"] = list(self.sources)
        data["basis"] = self.stands_on
        return data


def check_name(name: str) -> str:
    """Names become file names, so they stay a plain slug."""
    name = name.strip().lower()
    if not NAME_PATTERN.match(name):
        raise ValueError(f"tên phải dạng chu-de-ngan (a-z, 0-9, dấu gạch), nhận {name!r}")
    return name


def check_type(value: str) -> str:
    value = value.strip().lower()
    if value not in FACT_TYPES:
        raise ValueError(f"type phải là một trong {', '.join(FACT_TYPES)}, nhận {value!r}")
    return value


def check_basis(value: str) -> str:
    value = (value or "").strip().lower()
    if value not in AUTHORITY:
        raise ValueError(f"basis phải là một trong {', '.join(BASES)}, nhận {value!r}")
    return value


def check_day(value: str) -> str:
    """A day as `YYYY-MM-DD`, or empty for none."""
    value = (value or "").strip()
    if value:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"ngày phải dạng YYYY-MM-DD, nhận {value!r}") from exc
    return value


def day_of(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10]) if value else None
    except ValueError:
        return None


def day_before(value: str) -> str:
    day = day_of(value)
    return (day - timedelta(days=1)).strftime(DAY) if day else ""


def state_on(fact: Fact, today: date) -> str:
    """`pending` before its first day, `expired` after its last, `current` otherwise."""
    start, end = day_of(fact.valid_from), day_of(fact.valid_until)
    if start and today < start:
        return "pending"
    if end and today > end:
        return "expired"
    return "current"


def front_matter(fact: Fact) -> dict[str, Any]:
    """What the file's frontmatter holds; the optional fields only when they are set."""
    data: dict[str, Any] = {
        "name": fact.name,
        "description": fact.description,
        "type": fact.type,
        "written_by": fact.written_by,
        "source": fact.source,
        "updated": fact.updated,
        "basis": fact.stands_on,
        "version": fact.version,
    }
    for key in ("valid_from", "valid_until", "confirmed"):
        if getattr(fact, key):
            data[key] = getattr(fact, key)
    if fact.sources:
        data["sources"] = list(fact.sources)
    return data


def from_mapping(data: dict[str, Any], name: str, body: str) -> Fact:
    """A fact from frontmatter (or a history record), tolerant of fields it lacks."""
    raw_sources = data.get("sources") or ()
    try:
        version = max(1, int(data.get("version") or 1))
    except (TypeError, ValueError):
        version = 1
    return Fact(
        name=str(data.get("name") or name),
        description=str(data.get("description", "")),
        type=str(data.get("type", "reference")),
        written_by=str(data.get("written_by", "")),
        source=str(data.get("source", "")),
        updated=str(data.get("updated", "")),
        body=body.strip(),
        basis=str(data.get("basis") or ""),
        valid_from=str(data.get("valid_from") or ""),
        valid_until=str(data.get("valid_until") or ""),
        sources=tuple(str(s) for s in raw_sources) if isinstance(raw_sources, list) else (),
        version=version,
        confirmed=str(data.get("confirmed") or ""),
    )
