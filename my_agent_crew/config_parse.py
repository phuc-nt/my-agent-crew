"""Small parsers `config.py` leans on, kept apart so the settings module stays a readable
list of what can be configured rather than how each value is read.

`Route` lives here rather than in `config` because the route parsers need it and it needs
nothing back; keeping the pair together is what lets both sides stay this small. `config`
re-exports it, so every existing `from my_agent_crew.config import Route` still works.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# The vision chain a picture is sent to when the chat model cannot see one. Two routes so a
# single provider hiccup does not turn image reading off for the day.
DEFAULT_VISION_ROUTES = (
    "openrouter:google/gemini-2.5-flash-lite,openrouter:qwen/qwen3-vl-8b-instruct"
)


@dataclass(frozen=True)
class Route:
    """One (provider, model) pair the chain may try; order in `Settings.routes` is priority."""

    provider: str
    model: str
    # How hard the model thinks (`reasoning.effort` on OpenRouter); empty leaves it to the
    # provider. Set per agent by the `reasoning` key, never written in a route string.
    reasoning: str = ""

    @classmethod
    def parse(cls, text: str) -> Route:
        provider, sep, model = text.strip().partition(":")
        if not sep or not provider or not model:
            raise ValueError(f"route must look like provider:model, got {text!r}")
        return cls(provider=provider, model=model)


def parse_routes(value: str | Sequence[str] | None) -> tuple[Route, ...]:
    """Comma-separated text or a yaml list; empty (or null) is an empty tuple."""
    if not value:
        return ()
    parts = value.split(",") if isinstance(value, str) else list(value)
    return tuple(Route.parse(part) for part in parts if str(part).strip())


def required_routes(value: str | Sequence[str]) -> tuple[Route, ...]:
    routes = parse_routes(value)
    if not routes:
        raise ValueError("at least one route is required")
    return routes


def vision_routes(env: Mapping[str, str], file_values: Mapping) -> tuple[Route, ...]:
    """An empty env value or an empty yaml list turns image reading off on purpose; only
    an absent setting takes the default."""
    from_env = env.get("MY_AGENT_VISION_ROUTES")
    if from_env is not None:
        return parse_routes(from_env)
    return parse_routes(file_values.get("vision_routes", DEFAULT_VISION_ROUTES))


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


# Below this, a pattern matches so much of what a person would type that it is not an
# allowance for a shape of command, it is approval switched off. Two characters is `ls`,
# the shortest command worth naming.
MIN_ALLOW_PATTERN_CHARS = 2

# Patterns that are long enough yet still match nearly everything. `.*` and `*` look like
# wildcards to anyone who writes one, but the match is a plain substring, so `.*` would
# allow only a literal `.*` while reading as "allow all" — the dangerous direction is the
# misunderstanding, not the match. The rest appear inside almost any command line.
ALLOW_PATTERN_DENYLIST = frozenset({"*", ".*", ".", "-", "--", "/", "&&", "||", ";", "|"})


def allow_patterns(from_env: str | None, from_file: object) -> tuple[str, ...]:
    """Commands that run without asking even outside an autonomous conversation.

    Empty by default: an agent that has not been told which commands are routine keeps the
    old rule, which is to ask about all of them. Patterns too broad to name a command are
    dropped rather than refused, because one bad entry in a list of ten would otherwise
    take an agent off the air, and dropping fails the safe way — the command still asks.
    """
    if from_env is not None:
        raw: Sequence[str] = from_env.split(";")
    elif isinstance(from_file, Sequence) and not isinstance(from_file, str):
        raw = [str(p) for p in from_file]
    else:
        return ()
    cleaned = (p.strip() for p in raw)
    return tuple(
        p for p in cleaned if len(p) >= MIN_ALLOW_PATTERN_CHARS and p not in ALLOW_PATTERN_DENYLIST
    )


def name_list(from_env: str | None, from_file: object) -> tuple[str, ...]:
    """Plain names, comma-separated in the environment or a list in the file; env wins."""
    if from_env is not None:
        raw: Sequence[str] = from_env.split(",")
    elif isinstance(from_file, Sequence) and not isinstance(from_file, str):
        raw = [str(p) for p in from_file]
    elif isinstance(from_file, str):
        raw = from_file.split(",")
    else:
        return ()
    return tuple(p.strip() for p in raw if p.strip())


def as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
