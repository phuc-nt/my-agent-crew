"""Skills are markdown files with a small front matter. `always: true` skills ride on
every prompt; the rest are attached per conversation by name."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

BUILTIN_DIR = Path(__file__).parent / "builtin"


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    always: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "always": self.always}


def parse_skill(text: str, fallback_name: str) -> Skill:
    meta: dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        _, _, rest = text.partition("---\n")
        front, sep, body = rest.partition("\n---")
        if sep:
            meta = yaml.safe_load(front) or {}
            body = body.lstrip("\n")
    return Skill(
        name=str(meta.get("name") or fallback_name),
        description=str(meta.get("description") or ""),
        body=body.strip(),
        always=bool(meta.get("always", False)),
    )


def load_skills(*dirs: Path) -> list[Skill]:
    """Later directories override earlier ones by name, so a home skill can shadow a builtin."""
    by_name: dict[str, Skill] = {}
    for directory in dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            skill = parse_skill(path.read_text(encoding="utf-8"), path.stem)
            by_name[skill.name] = skill
    return list(by_name.values())
