"""Facts about the person, shared by every agent in the crew.

One fact per file under `users/owner/facts/<name>.md`, each a YAML frontmatter block
followed by Markdown. A file per fact rather than one big document: agents rewrite facts
one at a time, and a single file would make every write a whole-document rewrite.

Writes are reconciled with the fact already there (`fact_reconcile`); replaced and
retracted versions are kept (`fact_history`); the prompt carries an index (`fact_index`).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import yaml

from my_agent_crew.memory import fact_history, fact_index, fact_recall
from my_agent_crew.memory.fact_model import (
    FACT_TYPES,
    NAME_PATTERN,
    SAID,
    Fact,
    check_basis,
    check_day,
    check_name,
    check_type,
    from_mapping,
    front_matter,
)
from my_agent_crew.memory.fact_reconcile import (
    CONFIRMED,
    CREATED,
    DISPUTED,
    closed,
    confirmed,
    decide,
)

INDEX_NAME = "INDEX.md"
SEPARATOR = "---"

__all__ = ["FACT_TYPES", "NAME_PATTERN", "Fact", "check_name", "check_type", "save_fact"]


def facts_dir(user_dir: Path) -> Path:
    return user_dir / "facts"


def parse_fact(path: Path) -> Fact | None:
    """None when the file is not a fact we wrote; a malformed file must not break the prompt."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith(SEPARATOR):
        return None
    _, _, rest = text.partition("\n")
    front, sep, body = rest.partition(f"\n{SEPARATOR}\n")
    if not sep:
        return None
    try:
        data = yaml.safe_load(front) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return from_mapping(data, path.stem, body)


def read_fact(user_dir: Path, name: str) -> Fact | None:
    path = facts_dir(user_dir) / f"{check_name(name)}.md"
    return parse_fact(path) if path.is_file() else None


def list_facts(user_dir: Path) -> list[Fact]:
    """Newest first, which is the order the index and the prompt show them in."""
    directory = facts_dir(user_dir)
    if not directory.is_dir():
        return []
    facts = [f for p in sorted(directory.glob("*.md")) if (f := parse_fact(p)) is not None]
    return sorted(facts, key=lambda f: f.updated, reverse=True)


def _store(user_dir: Path, fact: Fact) -> None:
    directory = facts_dir(user_dir)
    directory.mkdir(parents=True, exist_ok=True)
    front = yaml.safe_dump(front_matter(fact), allow_unicode=True, sort_keys=False)
    document = f"{SEPARATOR}\n{front}{SEPARATOR}\n\n{fact.body}\n"
    (directory / f"{fact.name}.md").write_text(document, encoding="utf-8")
    write_index(user_dir)


def save_fact(
    user_dir: Path,
    name: str,
    description: str,
    type: str,
    body: str,
    written_by: str,
    source: str,
    now: datetime | None = None,
    basis: str = SAID,
    valid_from: str = "",
    valid_until: str = "",
    sources: tuple[str, ...] = (),
    force: bool = False,
) -> tuple[str, Fact]:
    """Reconcile one write with the fact under its name (`fact_reconcile`) and keep the
    result: (outcome, the fact as it now stands). A disputed write changes nothing unless
    `force` says the person decided it."""
    incoming = Fact(
        name=check_name(name),
        description=description.strip(),
        type=check_type(type),
        written_by=written_by,
        source=source,
        updated=(now or datetime.now()).isoformat(timespec="seconds"),
        body=body.strip(),
        basis=check_basis(basis),
        valid_from=check_day(valid_from),
        valid_until=check_day(valid_until),
        sources=tuple(sources),
    )
    existing = read_fact(user_dir, incoming.name)
    outcome = decide(existing, incoming)
    if outcome == DISPUTED and not force:
        assert existing is not None
        return outcome, existing
    directory = facts_dir(user_dir)
    if existing is None:
        fact = replace(incoming, version=fact_history.last_version(directory, incoming.name) + 1)
        assert outcome == CREATED
    elif outcome == CONFIRMED:
        fact = confirmed(existing, incoming)
    else:
        fact_history.append(
            directory, closed(existing, incoming), incoming.updated, fact_history.SUPERSEDED
        )
        fact = replace(incoming, version=existing.version + 1)
    _store(user_dir, fact)
    return outcome, fact


def write_fact(user_dir: Path, name: str, *args, **kwargs) -> Fact:
    """Write as the person decided it: the write always lands, the old version kept."""
    kwargs.setdefault("force", True)
    return save_fact(user_dir, name, *args, **kwargs)[1]


def delete_fact(user_dir: Path, name: str, now: datetime | None = None) -> bool:
    """Retract: the fact leaves the prompt, its versions stay in the history. False when
    there was nothing to retract."""
    fact = read_fact(user_dir, name)
    if fact is None:
        return False
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    fact_history.append(facts_dir(user_dir), fact, stamp, fact_history.RETRACTED)
    (facts_dir(user_dir) / f"{fact.name}.md").unlink()
    write_index(user_dir)
    return True


def purge_fact(user_dir: Path, name: str) -> bool:
    """Forget for good: the file, every past version and the recall count."""
    name = check_name(name)
    directory = facts_dir(user_dir)
    path = directory / f"{name}.md"
    had_file = path.is_file()
    if had_file:
        path.unlink()
    had_history = fact_history.purge(directory, name)
    fact_recall.forget(directory, name)
    write_index(user_dir)
    return had_file or had_history


def render_index(user_dir: Path, today: date | None = None) -> str:
    return fact_index.render(facts_dir(user_dir), list_facts(user_dir), today or date.today())


def write_index(user_dir: Path) -> Path:
    path = facts_dir(user_dir) / INDEX_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_index(user_dir) + "\n", encoding="utf-8")
    return path


def read_index(user_dir: Path, today: date | None = None) -> str:
    """Rendered for the day asked, not read from `INDEX.md`: which version of a fact holds
    changes with the day, not only with a write."""
    return render_index(user_dir, today).strip()


def read_user_md(user_dir: Path) -> str:
    path = user_dir / "USER.md"
    return path.read_text(encoding="utf-8", errors="replace").strip() if path.is_file() else ""


def write_user_md(user_dir: Path, text: str) -> None:
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "USER.md").write_text(text, encoding="utf-8")
