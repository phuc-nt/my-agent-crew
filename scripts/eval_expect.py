"""The `expect` block of a case: the keys it may hold, and how a tool call is matched to one.

Pure logic: a case file is checked as it is read, so a typo in one is refused before a cent is
spent."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

EXPECT_KEYS = (
    "calls_tool",
    "not_calls_tool",
    "asks_approval",
    "max_calls",
    "reply_contains",
    "reply_not_contains",
    "delegates_to",
    "max_cost_usd",
)
TOOL_SPEC_KEYS = {
    "calls_tool": ("name", "args_regex", "agent", "turn"),
    "not_calls_tool": ("name", "args_regex", "turn"),
    "asks_approval": ("name", "args_regex"),
}
DELEGATE_KEYS = ("agent",)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    args_regex: re.Pattern[str] | None = None
    agent: str | None = None
    turn: int | None = None

    def hit(self, name: str, args: Mapping[str, Any], turn: int, agent: str = "") -> bool:
        return (
            name == self.name
            and (self.turn is None or turn == self.turn)
            and (self.agent is None or agent == self.agent)
            and (self.args_regex is None or self.args_regex.search(args_text(args)) is not None)
        )

    def __str__(self) -> str:
        parts = [self.name]
        if self.args_regex is not None:
            parts.append(f"with arguments matching /{self.args_regex.pattern}/")
        if self.agent is not None:
            parts.append(f"by {self.agent}")
        if self.turn is not None:
            parts.append(f"in turn {self.turn}")
        return " ".join(parts)


@dataclass(frozen=True)
class Expect:
    calls_tool: tuple[ToolSpec, ...] = ()
    not_calls_tool: tuple[ToolSpec, ...] = ()
    asks_approval: tuple[ToolSpec, ...] = ()
    max_calls: Mapping[str, int] = field(default_factory=dict)
    reply_contains: tuple[str, ...] = ()
    reply_not_contains: tuple[str, ...] = ()
    delegates_to: str | None = None
    max_cost_usd: float | None = None


def args_text(args: Mapping[str, Any]) -> str:
    return json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)


def only(raw: Mapping[str, Any], allowed: Sequence[str], where: str) -> None:
    unknown = sorted(set(raw) - set(allowed), key=str)
    if unknown:
        raise ValueError(f"{where}: unknown key {unknown[0]!r}; known keys: {', '.join(allowed)}")


def strings(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ValueError(f"{where} must be a list of non-empty strings")
    return tuple(value)


def parse_expect(raw: object, where: str) -> Expect:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{where}: expect must be a mapping")
    only(raw, EXPECT_KEYS, f"{where}: expect")
    specs = {key: _tool_specs(raw.get(key, []), key, where) for key in TOOL_SPEC_KEYS}
    return Expect(
        **specs,
        max_calls=_max_calls(raw.get("max_calls", {}), where),
        reply_contains=_needles(raw.get("reply_contains", []), "reply_contains", where),
        reply_not_contains=_needles(raw.get("reply_not_contains", []), "reply_not_contains", where),
        delegates_to=_delegates_to(raw.get("delegates_to"), where),
        max_cost_usd=_max_cost(raw.get("max_cost_usd"), where),
    )


def _tool_specs(raw: object, key: str, where: str) -> tuple[ToolSpec, ...]:
    if not isinstance(raw, list):
        raise ValueError(f"{where}: {key} must be a list")
    return tuple(_tool_spec(item, f"{key}[{i}]", key, where) for i, item in enumerate(raw))


def _tool_spec(raw: object, label: str, key: str, where: str) -> ToolSpec:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{where}: {label} must be a mapping")
    only(raw, TOOL_SPEC_KEYS[key], f"{where}: {label}")
    name, pattern, agent, turn = (raw.get(k) for k in ("name", "args_regex", "agent", "turn"))
    if not isinstance(name, str) or not name:
        raise ValueError(f"{where}: {label} needs a name")
    if turn is not None and (isinstance(turn, bool) or not isinstance(turn, int) or turn < 1):
        raise ValueError(f"{where}: {label}.turn counts from 1")
    if agent is not None and not isinstance(agent, str):
        raise ValueError(f"{where}: {label}.agent must be a string")
    compiled = None
    if pattern is not None:
        try:
            compiled = re.compile(str(pattern))
        except re.error as exc:
            raise ValueError(f"{where}: {label}.args_regex does not compile: {exc}") from exc
    return ToolSpec(name, compiled, agent, turn)


def _max_calls(raw: object, where: str) -> dict[str, int]:
    if isinstance(raw, Mapping) and all(_count(n) for n in raw.values()):
        return {str(name): int(limit) for name, limit in raw.items()}
    raise ValueError(f"{where}: max_calls maps a tool name to a whole number, 0 or more")


def _count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _needles(raw: object, key: str, where: str) -> tuple[str, ...]:
    return strings([raw] if isinstance(raw, str) else raw, f"{where}: {key}")


def _delegates_to(raw: object, where: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError(f"{where}: delegates_to is a mapping with an agent")
    only(raw, DELEGATE_KEYS, f"{where}: delegates_to")
    agent = raw.get("agent")
    if not isinstance(agent, str) or not agent:
        raise ValueError(f"{where}: delegates_to needs an agent")
    return agent


def _max_cost(raw: object, where: str) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int | float) or raw < 0:
        raise ValueError(f"{where}: max_cost_usd must be a number, 0 or more")
    return float(raw)
