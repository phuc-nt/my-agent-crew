"""Skills are markdown with a small front matter, either a single `name.md` or a folder
`name/SKILL.md` whose siblings (scripts, references) the model reaches by absolute path.
`always: true` skills ride on every prompt; the rest are attached per conversation."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from my_agent_crew.texts import SKILL_LOCATION, SKILL_MISSING_BINS

BUILTIN_DIR = Path(__file__).parent / "builtin"
FOLDER_MANIFEST = "SKILL.md"
Which = Callable[[str], str | None]


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    always: bool = False
    path: str | None = None
    # Command-line programs the skill drives. A skill that needs one it cannot find is
    # still indexed and still readable — the model has to know why a command fails.
    requires_bins: tuple[str, ...] = ()
    # The one command that prints the real syntax, e.g. "gws calendar --help". Cheaper
    # for the model to run once than to guess flags for sixteen steps.
    cli_help: str = ""
    missing_bins: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "always": self.always,
            "path": self.path,
            "requires_bins": list(self.requires_bins),
            "cli_help": self.cli_help,
            "missing_bins": list(self.missing_bins),
        }


def _required_bins(meta: dict[str, Any]) -> tuple[str, ...]:
    """`requires: {bins: [gws]}`. A string is accepted as one name so a one-tool skill
    does not have to remember list syntax."""
    requires = meta.get("requires")
    bins = requires.get("bins") if isinstance(requires, dict) else None
    if isinstance(bins, str):
        bins = [bins]
    if not isinstance(bins, list):
        return ()
    return tuple(str(b).strip() for b in bins if str(b).strip())


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
        requires_bins=_required_bins(meta),
        cli_help=str(meta.get("cliHelp") or "").strip(),
    )


def check_bins(skill: Skill, which: Which = shutil.which) -> Skill:
    """Fill in what is missing from this machine, and say so at the top of the body: the
    model reads the body, not the index, when it is about to run the command."""
    missing = tuple(name for name in skill.requires_bins if which(name) is None)
    if not missing:
        return skill
    notice = SKILL_MISSING_BINS.format(bins=", ".join(missing))
    return replace(skill, missing_bins=missing, body=f"{notice}\n\n{skill.body}")


def mentioned_skills(prompt: str, skills: Sequence[Skill]) -> list[str]:
    """Skill names a scheduled prompt spells out, so a job that says "chạy gws-shared" gets
    the instructions instead of guessing the command.

    Only hyphenated names count. A single ordinary word like "ledger" or "read" shows up in
    prompts that have nothing to do with the skill, and attaching the wrong body costs the
    job a slice of its context for no reason.
    """
    lowered = prompt.lower()
    return [s.name for s in skills if "-" in s.name and s.name.lower() in lowered and not s.always]


def _skill_files(directory: Path) -> list[tuple[Path, str, Path | None]]:
    """(file, fallback name, folder) for every `*.md` and `*/SKILL.md` in the directory."""
    found: list[tuple[Path, str, Path | None]] = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix == ".md":
            found.append((path, path.stem, None))
        elif path.is_dir() and (path / FOLDER_MANIFEST).is_file():
            found.append((path / FOLDER_MANIFEST, path.name, path))
    return found


def load_skills(*dirs: Path, which: Which = shutil.which) -> list[Skill]:
    """Later directories override earlier ones by name, so a home skill can shadow a builtin."""
    by_name: dict[str, Skill] = {}
    for directory in dirs:
        if not directory.is_dir():
            continue
        for path, fallback, folder in _skill_files(directory):
            skill = parse_skill(path.read_text(encoding="utf-8"), fallback)
            if folder is not None:
                location = str(folder.resolve())
                skill = replace(
                    skill,
                    body=f"{SKILL_LOCATION.format(path=location)}\n\n{skill.body}",
                    path=location,
                )
            by_name[skill.name] = check_bins(skill, which)
    return list(by_name.values())
