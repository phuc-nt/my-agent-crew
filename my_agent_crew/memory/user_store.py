"""Facts about the person, shared by every agent in the crew.

One fact per file under `users/owner/facts/<name>.md`, each a YAML frontmatter block
followed by Markdown. A file per fact rather than one big document: agents rewrite facts
one at a time, and a single file would make every write a whole-document rewrite.

`INDEX.md` is regenerated after every write so the prompt can carry a cheap table of
contents instead of the facts themselves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

NAME_PATTERN = re.compile(r"^[a-z0-9-]{1,60}$")
FACT_TYPES = ("profile", "preference", "feedback", "project", "reference")
INDEX_NAME = "INDEX.md"
SEPARATOR = "---"


@dataclass(frozen=True)
class Fact:
    """One remembered fact plus who wrote it and how it arrived."""

    name: str
    description: str
    type: str
    written_by: str
    source: str
    updated: str
    body: str


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
    return Fact(
        name=str(data.get("name") or path.stem),
        description=str(data.get("description", "")),
        type=str(data.get("type", "reference")),
        written_by=str(data.get("written_by", "")),
        source=str(data.get("source", "")),
        updated=str(data.get("updated", "")),
        body=body.strip(),
    )


def list_facts(user_dir: Path) -> list[Fact]:
    """Newest first, which is the order the index and the prompt show them in."""
    directory = facts_dir(user_dir)
    if not directory.is_dir():
        return []
    facts = [f for p in sorted(directory.glob("*.md")) if (f := parse_fact(p)) is not None]
    return sorted(facts, key=lambda f: f.updated, reverse=True)


def write_fact(
    user_dir: Path,
    name: str,
    description: str,
    type: str,
    body: str,
    written_by: str,
    source: str,
    now: datetime | None = None,
) -> Fact:
    """Write (or overwrite) one fact and refresh the index."""
    fact = Fact(
        name=check_name(name),
        description=description.strip(),
        type=check_type(type),
        written_by=written_by,
        source=source,
        updated=(now or datetime.now()).isoformat(timespec="seconds"),
        body=body.strip(),
    )
    directory = facts_dir(user_dir)
    directory.mkdir(parents=True, exist_ok=True)
    front = yaml.safe_dump(
        {
            "name": fact.name,
            "description": fact.description,
            "type": fact.type,
            "written_by": fact.written_by,
            "source": fact.source,
            "updated": fact.updated,
        },
        allow_unicode=True,
        sort_keys=False,
    )
    document = f"{SEPARATOR}\n{front}{SEPARATOR}\n\n{fact.body}\n"
    (directory / f"{fact.name}.md").write_text(document, encoding="utf-8")
    write_index(user_dir)
    return fact


def delete_fact(user_dir: Path, name: str) -> bool:
    """False when there was nothing to forget."""
    path = facts_dir(user_dir) / f"{check_name(name)}.md"
    if not path.is_file():
        return False
    path.unlink()
    write_index(user_dir)
    return True


def render_index(facts: list[Fact]) -> str:
    return "\n".join(
        f"- [{f.description or f.name}]({f.name}.md) · {f.type} · {f.written_by}" for f in facts
    )


def write_index(user_dir: Path) -> Path:
    path = facts_dir(user_dir) / INDEX_NAME
    path.write_text(render_index(list_facts(user_dir)) + "\n", encoding="utf-8")
    return path


def read_index(user_dir: Path) -> str:
    path = facts_dir(user_dir) / INDEX_NAME
    return path.read_text(encoding="utf-8", errors="replace").strip() if path.is_file() else ""


def read_user_md(user_dir: Path) -> str:
    path = user_dir / "USER.md"
    return path.read_text(encoding="utf-8", errors="replace").strip() if path.is_file() else ""
