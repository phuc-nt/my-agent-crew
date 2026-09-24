"""Turning a patch from the web into a validated profile.

A patch names the keys it changes and nothing else, so leaving a key out means "keep
it" rather than "clear it" — the web sends one section at a time and must not wipe the
rest of the file by omission. Clearing a key is asked for explicitly, by sending null.

Validation is `parse_profile`'s: the same code that reads a hand-written file reads
this one, so the web cannot write a profile the server would refuse to start with.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from my_agent_crew import texts
from my_agent_crew.agents.profile import PROFILE_KEYS, AgentProfile
from my_agent_crew.agents.profile_yaml import parse_profile
from my_agent_crew.config import Settings

AGENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# What the scheduler reads once at startup and never again. The Telegram bridge is not
# here: an edited `telegram` block rebuilds the bot on the spot.
RESTART_KEYS = {
    "schedules": texts.RESTART_REASON_SCHEDULES,
    "memory_consolidate": texts.RESTART_REASON_SCHEDULES,
}
# Keys naming a path on disk. A profile read from a file may point anywhere — a kit
# names its markdown by absolute path, and `agent add --workspace` aims an agent at a
# repo elsewhere on purpose. An edit arriving over HTTP is not that: whoever reaches
# this port would otherwise pick any readable file as a persona (its text goes to the
# model on the next turn) or aim the workspace tools at the source tree. So the check
# lives here, on the edit path, rather than in the parser both of those share.
PATH_KEYS = ("persona_files", "skills_dirs", "workspace")


def check_agent_id(agent_id: str) -> None:
    """An id is a directory name and a URL segment both, so it is kept to the characters
    that are safe in each rather than escaped at every use."""
    if not AGENT_ID_RE.match(agent_id):
        raise ValueError(texts.AGENT_ID_INVALID)


def check_inside_home(profile: AgentProfile, home: Path) -> None:
    """Every path an edit set has to stay under the crew home."""
    home = home.resolve()
    candidates = [profile.workspace, *profile.skills_dirs]
    candidates += [profile.dir / name for name in profile.persona_files]
    for path in candidates:
        if not path.resolve().is_relative_to(home):
            raise ValueError(texts.PATH_OUTSIDE_HOME.format(path=str(path)))


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
    for key, value in patch.items():
        if value is None:
            raw.pop(key, None)
        else:
            raw[key] = value
    return raw


def validated(agent_id: str, agent_dir: Path, raw: Any, settings: Settings) -> AgentProfile:
    """The patched manifest read as a profile, or a ValueError naming what is wrong.

    Plain dicts, not ruamel's: a profile holds what it parsed for the rest of the
    server's life, and a round-trip node carries the whole document along with it.
    """
    return parse_profile(agent_id, agent_dir, dict(raw), settings)


def restart_reasons(old: AgentProfile | None, new: AgentProfile) -> list[str]:
    """What the person still has to restart for, in their own words.

    Everything else about an agent — its routes, its tools, its persona, who it may
    delegate to — is rebuilt live, so saying "restart" for those would train people to
    ignore the one case where it is true.
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
