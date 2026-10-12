"""Turning a patch from the web into a validated profile.

A patch names the keys it changes and nothing else, so leaving a key out means "keep
it" rather than "clear it" — the web sends one section at a time and must not wipe the
rest of the file by omission. Clearing a key is asked for explicitly, by sending null.

Validation starts with `read_profile`, the same code that reads a hand-written file,
so the web cannot write a profile the server would refuse to start with. It then asks
more of the schedules an edit brings than boot asks of a file: see `check_schedules`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from my_agent_crew import texts
from my_agent_crew.agent_ids import is_agent_id
from my_agent_crew.agents.profile import PROFILE_KEYS, AgentProfile, Schedule
from my_agent_crew.agents.profile_edit_paths import PATH_KEYS
from my_agent_crew.agents.profile_write import as_written
from my_agent_crew.agents.profile_yaml import read_profile
from my_agent_crew.agents.schedule import COMMAND, PROMPT
from my_agent_crew.config import Route, Settings
from my_agent_crew.scheduler.cron import CronSpec, parse_every

# What the scheduler reads once at startup and never again. The Telegram bridge is not
# here: an edited `telegram` block rebuilds the bot on the spot.
RESTART_KEYS = {
    "schedules": texts.RESTART_REASON_SCHEDULES,
    "memory_consolidate": texts.RESTART_REASON_SCHEDULES,
}


def check_agent_id(agent_id: str) -> None:
    """An id is a directory name and a URL segment both, so it is kept to the characters
    that are safe in each rather than escaped at every use."""
    if not is_agent_id(agent_id):
        raise ValueError(texts.AGENT_ID_INVALID)


def route_text(value: Any) -> Any:
    """A route as the manifest writes it. The web edits a route as a provider and a model
    apart and sends it so; the file keeps the one line a person would write by hand."""
    if not isinstance(value, dict):
        return value
    provider, model = value.get("provider"), value.get("model")
    if set(value) != {"provider", "model"} or not all(isinstance(v, str) for v in value.values()):
        raise ValueError(f"route must look like provider:model, got {value!r}")
    route = Route.parse(f"{provider.strip()}:{model.strip()}")
    return f"{route.provider}:{route.model}"


def apply_patch(raw: Any, patch: dict[str, Any]) -> Any:
    """The manifest with the patch's keys set, mutated in place so ruamel keeps the
    comments and the key order of everything the patch did not mention."""
    unknown = sorted(set(patch) - PROFILE_KEYS)
    if unknown:
        raise ValueError(texts.PROFILE_KEY_UNKNOWN.format(keys=", ".join(unknown)))
    # A string is iterable, so the parser would turn "rm" into the patterns "r" and "m"
    # and the guard that asks before a destructive command would quietly stop matching.
    list_keys = (
        "shell_ask_patterns",
        "shell_allow_patterns",
        "shell_deny_patterns",
        "shell_write_paths",
        "write_paths",
    )
    for key in (*list_keys, *PATH_KEYS):
        value = patch.get(key)
        if key != "workspace" and value is not None and not isinstance(value, list):
            raise ValueError(texts.PROFILE_KEY_NEEDS_LIST.format(key=key))
    if isinstance(patch.get("routes"), list):
        patch = patch | {"routes": [route_text(route) for route in patch["routes"]]}
    if "escalation_route" in patch:
        patch = patch | {"escalation_route": route_text(patch["escalation_route"])}
    for key, value in patch.items():
        if value is None:
            raw.pop(key, None)
        else:
            raw[key] = as_written(value)
    return raw


def validated(
    agent_id: str,
    agent_dir: Path,
    to_be: dict[str, Any],
    settings: Settings,
    before: AgentProfile | None = None,
) -> AgentProfile:
    """The patched manifest read as a profile, or a ValueError naming what is wrong.

    `to_be` is the file about to be written as the next start will read it
    (`profile_read_back.py`), and not as the library that writes it reads it. The two go
    by two versions of YAML: a switch a person wrote as `off` is a boolean to the one and
    a text to the other, and measured by the other every save of that agent, about
    anything, was refused for it. It is plain dicts too: a profile holds what it parsed
    for the rest of the server's life, and a round-trip node carries the whole document
    along with it.

    `before` is the agent as it runs now. A new agent has none, so every schedule it
    carries is the edit's.
    """
    profile = read_profile(agent_id, agent_dir, to_be, settings)
    check_schedules(agent_id, profile.schedules, before.schedules if before else ())
    return profile


def check_schedules(agent_id: str, schedules: Sequence[Schedule], kept: Sequence[Schedule]) -> None:
    """Each schedule the edit adds or changes has a timing the clock can read, an id of
    its own and a text to run.

    Boot checks neither. The parser leaves timing to the scheduler, which first reads it
    when the jobs list is asked for or the clock ticks: a hand-written file with a typo in
    a cron starts fine, then answers the jobs list with a 500 and, while that job is on,
    fails every tick for every job beside it. And the scheduler keys its jobs by id, so a
    second job on the same id — a blank row numbered by its place onto a kept row's
    `job-1`, or a row named like the consolidation job — replaces the first without a word.
    Nor does it read what a job does, beyond a script: a prompt or a command goes to the
    model or to a shell as it stands, and one that is no text fails when its time comes,
    with no run to show for it and the jobs due beside it held up.

    The rows in `kept`, the schedules the agent runs with now, are not checked again: a
    file edited by hand may already hold one this check would refuse, and holding an
    unrelated save hostage to it helps nobody. They are matched one for one, and by
    equality rather than in a set, because a hand-written cron can be any YAML value.
    """
    unchanged = list(kept)
    taken = Counter(schedule.id for schedule in schedules)
    for schedule in schedules:
        if schedule in unchanged:
            unchanged.remove(schedule)
            continue
        if taken[schedule.id] > 1:
            raise ValueError(texts.SCHEDULE_ID_TAKEN.format(id=schedule.id))
        try:
            if schedule.cron:
                CronSpec.parse(str(schedule.cron))
            else:
                parse_every(str(schedule.every))
        except ValueError as exc:
            raise ValueError(f"agent {agent_id}: schedule {schedule.id}: {exc}") from exc
        for action in (PROMPT, COMMAND):
            doing = getattr(schedule, action)
            if doing and not isinstance(doing, str):
                where = f"agent {agent_id}: schedule {schedule.id}"
                raise ValueError(f"{where}: {action} must be a non-empty string")


def restart_reasons(old: AgentProfile | None, new: AgentProfile) -> list[str]:
    """What the person still has to restart for, in their own words.

    Each reason is a whole sentence, and the agent editor shows it as it is, never as the
    name of a key. Everything else about an agent — its routes, its tools, its persona,
    who it may delegate to — is rebuilt live, so saying "restart" for those would train
    people to ignore the one case where it is true.
    """
    reasons: list[str] = []
    for key, reason in RESTART_KEYS.items():
        before = getattr(old, key, None) if old else None
        after = getattr(new, key)
        # A new agent has nothing before it, and an agent with no schedules is the same
        # as one that never had any: only something there now makes a restart worth
        # asking for. Comparing None against an empty tuple would claim one every time
        # an agent is created, and a notice that is always on is one nobody reads.
        if not before and not after:
            continue
        if before != after and reason not in reasons:
            reasons.append(reason)
    return reasons
