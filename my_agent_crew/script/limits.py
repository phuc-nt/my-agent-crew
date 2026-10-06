"""The limits a script runs under, and the two ways it stops.

A script is text a model wrote, run before anyone reads it. What it may do is settled by
the interpreter having nothing else in it; how much it may do is settled here. A step is
one node of the script evaluated. No one value may be longer than `MAX_VALUE`, which is
checked before the making wherever one operation can make far more than it was given.
What the script holds in all is measured, not estimated: the process that runs it traces
its own allocations (`child.py`), and the budget reads that figure each time enough has
been made to matter. Where nothing is tracing, as in a test of the interpreter alone, only
the first two limits hold.

`ScriptError` is a failure the script may catch with `try`: a tool that failed, a missing
key. `Halt` ends it whatever it wrote: a limit reached, or a call it is not let to make.
"""

from __future__ import annotations

import tracemalloc
from dataclasses import dataclass, field
from typing import Any

from my_agent_crew import texts_script as t

MAX_SOURCE_CHARS = 20_000
MAX_STEPS = 2_000_000
# Characters of one text, items of one list.
MAX_VALUE = 8_000_000
MAX_LIVE_BYTES = 256 * 1024 * 1024
# How many characters and items are made between two readings of the memory held.
ROOM_CHECK_EVERY = 50_000
# Calls of the script's own functions, one inside another.
MAX_DEPTH = 40
MAX_CALLS = 25
MAX_OUTPUT_CHARS = 60_000
MAX_ARGUMENT_CHARS = 100_000
# The most of an error's own words that is kept: one may carry a whole text of the script's.
MAX_ERROR_CHARS = 2_000
MAX_INDENT = 8
MAX_INT_BITS = 256
# How far a value is walked before it is written out: its depth, and its nodes in all.
MAX_NESTING = 50
MAX_WALK = 200_000
# What a number, a flag or None is counted as when written.
SCALAR_CHARS = 24

SIZED = (str, list, tuple, dict, set)


class ScriptError(Exception):
    """A failure the script can catch and carry on from."""


class Halt(Exception):
    """Ends the script. No `except` of the script's catches it."""


def _traced() -> int | None:
    return tracemalloc.get_traced_memory()[0] if tracemalloc.is_tracing() else None


@dataclass
class Budget:
    steps: int = 0
    calls: int = 0
    depth: int = 0
    made_so_far: int = 0
    check_at: int = ROOM_CHECK_EVERY
    # The memory already held when the script began, or None when nothing is tracing.
    base: int | None = field(default_factory=_traced)

    def step(self, count: int = 1) -> None:
        self.steps += count
        if self.steps > MAX_STEPS:
            raise Halt(t.SCRIPT_OUT_OF_STEPS.format(most=MAX_STEPS))

    def charge(self, size: int) -> None:
        """Counts what was just made or added, and looks at the memory held once enough
        has been. Anything large is enough by itself, so one big value is never waited on."""
        self.made_so_far += size
        if self.made_so_far >= self.check_at:
            self.check_at = self.made_so_far + ROOM_CHECK_EVERY
            self.room()

    def room(self) -> None:
        if self.base is not None:
            held = tracemalloc.get_traced_memory()[0] - self.base
            if held > MAX_LIVE_BYTES:
                raise Halt(t.SCRIPT_OUT_OF_ROOM)

    def fits(self, size: int) -> None:
        """Refuses before the making, for an operation whose result can be far larger than
        what went into it: looking afterwards would be looking at memory already taken."""
        if size > MAX_VALUE:
            raise Halt(t.SCRIPT_OUT_OF_ROOM)

    def made(self, value: Any) -> Any:
        """Counts a value just made, and hands it back."""
        kind = type(value)
        if kind is int:
            if value.bit_length() > MAX_INT_BITS:
                raise ScriptError(t.SCRIPT_BIG_NUMBER)
        elif kind in SIZED:
            self.fits(len(value))
            self.charge(len(value))
        return value

    def measure(self, value: Any) -> int:
        """About how many characters the value is when written out, refused when that
        would not fit in one text. A list of a thousand items is a thousand long until it
        is written, and each of them may be a long text held once and named a thousand
        times; so anything about to be written is walked first. The walk stops at a depth and at
        a count, which is also what stops it on a list that holds itself."""
        total = seen = 0
        stack = [(value, 0)]
        while stack:
            item, depth = stack.pop()
            seen += 1
            kind = type(item)
            if kind is str:
                total += len(item) + 2
            elif kind is int:
                total += item.bit_length() // 3 + 2
            elif kind in (list, tuple, set, dict):
                children = [*item.keys(), *item.values()] if kind is dict else item
                if depth >= MAX_NESTING or seen + len(stack) + len(children) > MAX_WALK:
                    raise ScriptError(t.SCRIPT_TOO_NESTED)
                total += 2 + 2 * len(children)
                stack.extend((child, depth + 1) for child in children)
            else:
                total += SCALAR_CHARS
            self.fits(total)
        self.step(seen)
        return total
