"""Small parsers `config.py` leans on, kept apart so the settings module stays a readable
list of what can be configured rather than how each value is read."""

from __future__ import annotations

from collections.abc import Sequence

# Commands that get an approval even in an autonomous conversation. This is a second,
# additive guard, not a sandbox: it catches the obvious destructive shapes, and anyone
# meaning to get around it can. Matched as case-insensitive substrings of the command.
DEFAULT_SHELL_ASK_PATTERNS = (
    "rm -rf",
    "rm -r ",
    "sudo ",
    "| sh",
    "| bash",
    "mkfs",
    "git push --force",
    "git reset --hard",
    "> /dev/",
    "chmod -R",
    "launchctl",
)


def ask_patterns(from_env: str | None, from_file: object) -> tuple[str, ...]:
    """An empty env value or an empty yaml list turns the guard off on purpose; only an
    absent setting falls back to the defaults."""
    if from_env is not None:
        return tuple(p.strip() for p in from_env.split(";") if p.strip())
    if isinstance(from_file, Sequence) and not isinstance(from_file, str):
        return tuple(str(p).strip() for p in from_file if str(p).strip())
    return DEFAULT_SHELL_ASK_PATTERNS


def as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
