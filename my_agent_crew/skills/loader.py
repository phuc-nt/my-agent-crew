"""Skills are markdown with a small front matter, either a single `name.md` or a folder
`name/SKILL.md` whose siblings (scripts, references) the model reaches by absolute path.
`always: true` skills ride on every prompt; the rest are attached per conversation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from my_agent_crew.texts import SKILL_LOCATION

BUILTIN_DIR = Path(__file__).parent / "builtin"
FOLDER_MANIFEST = "SKILL.md"


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    always: bool = False
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "always": self.always,
            "path": self.path,
        }


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


def _skill_files(directory: Path) -> list[tuple[Path, str, Path | None]]:
    """(file, fallback name, folder) for every `*.md` and `*/SKILL.md` in the directory."""
    found: list[tuple[Path, str, Path | None]] = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix == ".md":
            found.append((path, path.stem, None))
        elif path.is_dir() and (path / FOLDER_MANIFEST).is_file():
            found.append((path / FOLDER_MANIFEST, path.name, path))
    return found


def load_skills(*dirs: Path) -> list[Skill]:
    """Later directories override earlier ones by name, so a home skill can shadow a builtin."""
    by_name: dict[str, Skill] = {}
    for directory in dirs:
        if not directory.is_dir():
            continue
        for path, fallback, folder in _skill_files(directory):
            skill = parse_skill(path.read_text(encoding="utf-8"), fallback)
            if folder is not None:
                location = str(folder.resolve())
                skill = Skill(
                    name=skill.name,
                    description=skill.description,
                    body=f"{SKILL_LOCATION.format(path=location)}\n\n{skill.body}",
                    always=skill.always,
                    path=location,
                )
            by_name[skill.name] = skill
    return list(by_name.values())
