"""One job an agent runs on its own: a cron line or an interval, and what to do when it comes
round: a prompt for the model, a slash command, or a script that runs with no model at all.
`schedules:` in `agent.yaml` is a list of these."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from my_agent_crew import texts

SCHEDULE_KEYS = {
    "id",
    "name",
    "cron",
    "every",
    "prompt",
    "command",
    "script",
    "then_prompt",
    "enabled",
    "skills",
    "approval_ttl_seconds",
}
# Every key a row may state in its file. `check` stands apart from `SCHEDULE_KEYS`, the table
# the web editor's form is held to, because that form does not carry it yet.
ROW_KEYS = SCHEDULE_KEYS | {"check"}
# What a row does, one of these and never two.
ACTIONS = ("prompt", "command", "script")
PROMPT, COMMAND, SCRIPT, CONSOLIDATE = "prompt", "command", "script", "consolidate"
# The kinds whose run may be a conversation's, which is what is sent on to the person: a
# prompt job's always, a script job's when what it printed went on to the model.
DELIVERED = (PROMPT, SCRIPT)


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
    # A script run as `tool_script` runs one, with no turn opened (`scheduler/script_job.py`).
    script: str | None = None
    # Beside a script only: when the script printed something, a turn is opened with this
    # and what it printed, as a prompt job opens one.
    then_prompt: str | None = None
    # A command run once the job's own work ended well; leaving with anything but 0, it
    # makes the run a failed one (`scheduler/check.py`).
    check: str | None = None

    @property
    def kind(self) -> str:
        """What running this job does, so the UI can label it without guessing."""
        if self.consolidate:
            return CONSOLIDATE
        if self.script:
            return SCRIPT
        return COMMAND if self.command else PROMPT

    def to_dict(self) -> dict[str, Any]:
        # A row that states no check shows none, as it did before a row could state one.
        check = {"check": self.check} if self.check else {}
        return {
            "id": self.id,
            "name": self.name,
            "cron": self.cron,
            "every": self.every,
            "prompt": self.prompt,
            "command": self.command,
            "script": self.script,
            "then_prompt": self.then_prompt,
            "enabled": self.enabled,
            "skills": list(self.skills),
            "approval_ttl_seconds": self.approval_ttl_seconds,
            "kind": self.kind,
            **check,
        }


def check_of(raw: dict[str, Any], where: str) -> str | None:
    """A row's `check` as its file states it: a command, or nothing. Read as a job's command
    is run, as a text; one that is none would fail every run of a job that did its work."""
    check = raw.get("check")
    if check is None:
        return None
    if not isinstance(check, str) or not check.strip():
        raise ValueError(f"{where}: check must be a non-empty string")
    return check


def each_on_its_own_id(agent_id: str, schedules: Sequence[Schedule]) -> tuple[Schedule, ...]:
    """An agent's jobs as it will hold them, or a ValueError naming the id two of them go by.

    A job is known by its id: on the clock (`<agent>/<id>`), in the switch a person flips on
    it, in what a script job keeps (`job:<id>`). Two rows on one id were one job to each of
    those. The later row ran, the earlier never did, and nothing said so. A row that writes
    no id goes by its place (`job-1`), which another row may have written, and the
    consolidation job has an id as well, so the ids are compared once every job has its
    own, as the texts they are."""
    seen: set[str] = set()
    for schedule in schedules:
        if schedule.id in seen:
            raise ValueError(texts.SCHEDULE_ID_TAKEN.format(agent_id=agent_id, id=schedule.id))
        seen.add(schedule.id)
    return tuple(schedules)
