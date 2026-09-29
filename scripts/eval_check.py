"""Judging one run against its case: what a run did, and which expectations it broke.

Pure logic with no server and no model. `eval_play.py` gathers what a run did into an
`Observed`; `check` says which of the case's expectations that run broke."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, NamedTuple

from eval_cases import Case
from eval_expect import args_text

from my_agent_crew.memory.search import normalize

RUN = "run"  # the assertion a run that did not finish breaks
SNIPPET_CHARS = 160


class Call(NamedTuple):
    turn: int
    agent: str
    name: str
    args: dict[str, Any]


class Ask(NamedTuple):
    turn: int
    name: str
    args: dict[str, Any]


class Delegate(NamedTuple):
    agent: str
    outcome: str | None


@dataclass(frozen=True)
class Observed:
    """What one run did, whatever the model said about it."""

    reply: str = ""
    tool_calls: tuple[Call, ...] = ()
    approvals: tuple[Ask, ...] = ()
    delegates: tuple[Delegate, ...] = ()
    spent_usd: float = 0.0
    unknown_cost_calls: int = 0
    error: str = ""


@dataclass(frozen=True)
class Failure:
    assertion: str
    detail: str

    def __str__(self) -> str:
        return f"{self.assertion}: {self.detail}"


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SNIPPET_CHARS else text[: SNIPPET_CHARS - 1] + "…"


def check(case: Case, observed: Observed) -> list[Failure]:
    """Every expectation the run broke, in a fixed order; empty when it kept them all."""
    expect = case.expect
    out: list[Failure] = []
    if observed.error:
        out.append(Failure(RUN, observed.error))
    saw = ", ".join(dict.fromkeys(c.name for c in observed.tool_calls)) or "no tool calls"
    for spec in expect.calls_tool:
        if not any(spec.hit(c.name, c.args, c.turn, c.agent) for c in observed.tool_calls):
            out.append(Failure("calls_tool", f"no call to {spec}; saw {saw}"))
    for spec in expect.not_calls_tool:
        for call in observed.tool_calls:
            if spec.hit(call.name, call.args, call.turn, call.agent):
                with_args = _short(args_text(call.args))
                out.append(
                    Failure("not_calls_tool", f"{call.name} in turn {call.turn}: {with_args}")
                )
                break
    asked = ", ".join(dict.fromkeys(a.name for a in observed.approvals)) or "none"
    for spec in expect.asks_approval:
        if not any(spec.hit(a.name, a.args, a.turn) for a in observed.approvals):
            out.append(Failure("asks_approval", f"no approval asked for {spec}; asked for {asked}"))
    for name, limit in expect.max_calls.items():
        made = sum(1 for c in observed.tool_calls if c.name == name)
        if made > limit:
            out.append(Failure("max_calls", f"{name} called {made} times, at most {limit}"))
    reply = normalize(observed.reply)
    for needle in expect.reply_contains:
        if normalize(needle) not in reply:
            out.append(Failure("reply_contains", f"no {needle!r} in: {_short(observed.reply)}"))
    for needle in expect.reply_not_contains:
        if normalize(needle) in reply:
            out.append(Failure("reply_not_contains", f"{needle!r} is in: {_short(observed.reply)}"))
    if expect.delegates_to and all(d.agent != expect.delegates_to for d in observed.delegates):
        went = ", ".join(d.agent for d in observed.delegates) or "nobody"
        out.append(
            Failure("delegates_to", f"no delegation to {expect.delegates_to}; went to {went}")
        )
    if expect.max_cost_usd is not None and observed.spent_usd > expect.max_cost_usd:
        detail = f"spent ${observed.spent_usd:.4f}, at most ${expect.max_cost_usd:.4f}"
        out.append(Failure("max_cost_usd", detail))
    return out


def case_passed(outcomes: Sequence[bool], runs: int) -> bool:
    """A model does not answer the same way twice: two runs in three are enough."""
    return sum(outcomes) * 3 >= runs * 2
