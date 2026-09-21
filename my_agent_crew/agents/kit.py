"""Harness kits: the `.agents/`, `.claude/` and `.opencode/` directories the other agent
tools keep next to a project or in a home. One holds skills (`skills/<name>/SKILL.md`),
agents (`agents/<id>.md`), commands (`commands/<name>.md`) and `settings.json` with
hooks. The crew reads the same layout so a kit built for Claude Code, Codex or opencode
works here without being rewritten: the home's kit is crew-wide, an agent's own kit is
its, and the kit of the project an agent works in governs its work there.

Where a kit sits decides what it may add. Home and agent kits bring everything, agents
included. A project kit brings skills, commands, hooks and the project's `AGENTS.md`,
not its agents: a repository's helper subagents are that repository's, and they would
otherwise flood the crew roster of every project the crew touches.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from my_agent_crew.agents.profile import AgentProfile

KIT_DIRS = (".agents", ".claude", ".opencode")
SKILL_DIRS = ("skills", "skill")
AGENT_DIRS = ("agents", "agent")
COMMAND_DIRS = ("commands", "command")
SETTINGS_FILE = "settings.json"
# The cross-harness instructions file a project keeps at its root.
INSTRUCTIONS_FILE = "AGENTS.md"
HOME, AGENT, PROJECT = "home", "agent", "project"


@dataclass(frozen=True)
class Kit:
    root: Path  # the `.agents` (or `.claude`, `.opencode`) directory itself
    workspace: Path  # what an agent read from this kit works in unless it says otherwise
    scope: str = PROJECT

    @property
    def project(self) -> Path:
        """The directory the kit belongs to: hook commands run from here, like the
        harnesses run them."""
        return self.root.parent

    @property
    def brings_agents(self) -> bool:
        return self.scope in (HOME, AGENT)

    @property
    def skills_dirs(self) -> tuple[Path, ...]:
        return tuple(self.root / name for name in SKILL_DIRS if (self.root / name).is_dir())

    @property
    def agent_files(self) -> tuple[Path, ...]:
        return tuple(_markdown_files(self.root, AGENT_DIRS, recursive=False))

    @property
    def command_files(self) -> tuple[Path, ...]:
        """Recursive: `commands/mk/plan.md` is the command `mk:plan`, as in Claude Code."""
        return tuple(_markdown_files(self.root, COMMAND_DIRS, recursive=True))

    @property
    def settings_file(self) -> Path | None:
        path = self.root / SETTINGS_FILE
        return path if path.is_file() else None

    def command_name(self, path: Path) -> str:
        for name in COMMAND_DIRS:
            base = self.root / name
            if path.is_relative_to(base):
                parts = path.relative_to(base).with_suffix("").parts
                return ":".join(parts)
        return path.stem


def _markdown_files(root: Path, names: tuple[str, ...], recursive: bool) -> Iterator[Path]:
    for name in names:
        base = root / name
        if not base.is_dir():
            continue
        found = base.rglob("*.md") if recursive else base.glob("*.md")
        yield from sorted(p for p in found if p.is_file())


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """`---` yaml `---` body, the shape every harness uses for its markdown files."""
    if not text.startswith("---"):
        return {}, text.strip()
    _, _, rest = text.partition("---\n")
    front, sep, body = rest.partition("\n---")
    if not sep:
        return {}, text.strip()
    meta = yaml.safe_load(front) or {}
    return (meta if isinstance(meta, dict) else {}), body.strip()


def discover_kits(project: Path, workspace: Path, scope: str = PROJECT) -> list[Kit]:
    """The kits found directly under `project`, in `KIT_DIRS` order."""
    return [
        Kit(root=(project / name).resolve(), workspace=workspace, scope=scope)
        for name in KIT_DIRS
        if (project / name).is_dir()
    ]


def crew_kits(home: Path) -> list[Kit]:
    return discover_kits(home, home / "workspace", HOME)


def agent_kits(profile: AgentProfile) -> list[Kit]:
    """Every kit that speaks to one agent: the crew's, its own, then its project's, so a
    later kit shadows an earlier one by name."""
    kits = crew_kits(profile.settings.home)
    if profile.dir != profile.settings.home:
        kits += discover_kits(profile.dir, profile.workspace, AGENT)
    if profile.workspace not in (profile.settings.home, profile.dir):
        kits += discover_kits(profile.workspace, profile.workspace, PROJECT)
    seen: set[Path] = set()
    unique = []
    for kit in kits:
        if kit.root not in seen:
            seen.add(kit.root)
            unique.append(kit)
    return unique


def with_kits(profile: AgentProfile) -> AgentProfile:
    """The profile with what its kits add: skill directories after its own, the commands
    and hooks they define, and the project's `AGENTS.md` read as one more persona file
    when the agent works in a project of its own."""
    from my_agent_crew.agents.kit_commands import load_commands
    from my_agent_crew.agents.kit_hooks import load_hooks

    kits = agent_kits(profile)
    persona = list(profile.persona_files)
    instructions = profile.workspace / INSTRUCTIONS_FILE
    if profile.workspace != profile.dir and instructions.is_file():
        persona.append(str(instructions))
    return replace(
        profile,
        persona_files=tuple(persona),
        skills_dirs=profile.skills_dirs + tuple(d for kit in kits for d in kit.skills_dirs),
        commands=load_commands(kits),
        hooks=load_hooks(kits),
        kits=tuple(kit.root for kit in kits),
    )
