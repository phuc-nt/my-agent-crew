"""What a script's own calls tell the turn while the script still runs.

A tool's result arrives when the tool is over. A script is a tool that makes calls of its
own, and may run for minutes: the person watching should see each call as it ends, and
what it cost, not all of them at the end. So the turn hands the call being carried out a
place to say so, in a context variable as `tool_call_id` is, and the script says so through
`note_nested_call`. Where nothing listens, saying so does nothing.

A turn is allowed so many calls of the model, and each could be a script making calls of its
own; so the scripts of one turn share a count of those too (`NestedBudget`). The script that
would pass it is ended there, and the turn with it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from my_agent_crew.tools.result import NestedCall

# The calls the scripts of one turn may make between them, for each call of the model
# the turn is allowed.
NESTED_CALLS_PER_STEP = 10

Sink = Callable[[NestedCall], None]


@dataclass
class NestedBudget:
    """What the scripts of one turn may still call. `spent` is set by the first asking
    that did not fit, and stays: the turn ends on it."""

    limit: int
    used: int = 0
    spent: bool = False

    def take(self, count: int) -> bool:
        """All of `count` or none: a batch is not made in part."""
        if self.used + count > self.limit:
            self.spent = True
            return False
        self.used += count
        return True


_sink: ContextVar[Sink | None] = ContextVar("nested_call_sink", default=None)
_budget: ContextVar[NestedBudget | None] = ContextVar("nested_call_budget", default=None)


def start_nested_budget(max_steps: int) -> NestedBudget:
    """A turn's own count, from nothing. The tasks its calls run in share it: each copies
    the context, and so holds this same count."""
    budget = NestedBudget(max_steps * NESTED_CALLS_PER_STEP)
    _budget.set(budget)
    return budget


def nested_budget() -> NestedBudget | None:
    """None where no turn is running: a script run on its own is not counted."""
    return _budget.get()


def set_nested_sink(sink: Sink | None) -> None:
    """Set inside the task that carries one call out, so it is that call's alone."""
    _sink.set(sink)


@contextmanager
def outside_a_turn(sink: Sink) -> Iterator[None]:
    """For a script that no turn runs, a schedule's: its calls are told to `sink` and
    counted against no turn, whatever the turn before it in this task left set. Both are
    put back when it is over."""
    told, counted = _sink.set(sink), _budget.set(None)
    try:
        yield
    finally:
        _budget.reset(counted)
        _sink.reset(told)


def note_nested_call(call: NestedCall) -> None:
    sink = _sink.get()
    if sink is not None:
        sink(call)
