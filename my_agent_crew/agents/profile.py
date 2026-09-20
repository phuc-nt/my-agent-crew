"""Agent profiles. `MY_AGENT_HOME/agents/<id>/agent.yaml` describes one agent: its
persona files, workspace, model routes and schedules. The `default` agent always exists
and is described by the top-level settings, so a fresh home works with no profile at all."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from my_agent_crew import texts
from my_agent_crew.agents.channels import TelegramConfig
from my_agent_crew.config import Settings

DEFAULT_AGENT_ID = "default"
PERSONA_FILES = ("AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md")
PROFILE_KEYS = {
    "name",
    "description",
    "routes",
    "workspace",
    "persona_files",
    "skills_dirs",
    "cost_cap_usd",
    "max_steps",
    "autonomous",
    "schedules",
    "telegram",
    "memory_consolidate",
}
SCHEDULE_KEYS = {"id", "name", "cron", "every", "prompt", "command", "enabled", "skills"}
CONSOLIDATE_JOB_ID = "memory-consolidate"
PROMPT, COMMAND, CONSOLIDATE = "prompt", "command", "consolidate"


@dataclass(frozen=True)
class Schedule:
    id: str
    name: str
    cron: str | None = None
    every: str | None = None
    prompt: str | None = None
    command: str | None = None
    enabled: bool = True
    consolidate: bool = False
    # Skills attached in full to the conversation a prompt job opens, by name.
    skills: tuple[str, ...] = ()

    @property
    def kind(self) -> str:
        """What running this job does, so the UI can label it without guessing."""
        if self.consolidate:
            return CONSOLIDATE
        return COMMAND if self.command else PROMPT

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "cron": self.cron,
            "every": self.every,
            "prompt": self.prompt,
            "command": self.command,
            "enabled": self.enabled,
            "skills": list(self.skills),
            "kind": self.kind,
        }


@dataclass(frozen=True)
class AgentProfile:
    id: str
    name: str
    dir: Path
    workspace: Path
    settings: Settings
    description: str = ""
    persona_files: tuple[str, ...] = PERSONA_FILES
    skills_dirs: tuple[Path, ...] = ()
    schedules: tuple[Schedule, ...] = field(default_factory=tuple)
    telegram: TelegramConfig | None = None
    memory_consolidate: str = ""

    @property
    def memory_dir(self) -> Path:
        return self.dir / "memory"

    @property
    def memory_file(self) -> Path:
        return self.dir / "MEMORY.md"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "dir": str(self.dir),
            "workspace": str(self.workspace),
            "routes": [{"provider": r.provider, "model": r.model} for r in self.settings.routes],
            "cost_cap_usd": self.settings.cost_cap_usd,
            "max_steps": self.settings.max_steps,
            "autonomous": self.settings.autonomous_default,
            "persona_files": [f for f in self.persona_files if (self.dir / f).is_file()],
            "schedules": [s.to_dict() for s in self.schedules],
            "telegram": self.telegram.to_dict() if self.telegram else None,
            "memory_consolidate": self.memory_consolidate,
        }


def default_profile(settings: Settings) -> AgentProfile:
    return AgentProfile(
        id=DEFAULT_AGENT_ID,
        name="Trợ lý",
        dir=settings.home,
        workspace=settings.workspace_dir,
        settings=settings,
        skills_dirs=(settings.skills_dir,),
    )


def consolidate_schedule(cron: str) -> Schedule:
    """The consolidation job is a profile key rather than a schedule the user writes out,
    but it becomes an ordinary schedule so the scheduler needs no special case."""
    return Schedule(
        id=CONSOLIDATE_JOB_ID,
        name=texts.CONSOLIDATE_JOB_NAME,
        cron=cron,
        consolidate=True,
    )


def profile_ids(profiles: Sequence[AgentProfile]) -> list[str]:
    return [p.id for p in profiles]
