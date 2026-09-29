"""One job an agent runs on its own: a cron line or an interval, and a prompt or a slash
command to run when it comes round. `schedules:` in `agent.yaml` is a list of these."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEDULE_KEYS = {
    "id",
    "name",
    "cron",
    "every",
    "prompt",
    "command",
    "enabled",
    "skills",
    "approval_ttl_seconds",
}
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
    # How long an approval in the conversation a prompt job opens waits; None is the setting.
    approval_ttl_seconds: int | None = None

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
            "approval_ttl_seconds": self.approval_ttl_seconds,
            "kind": self.kind,
        }
