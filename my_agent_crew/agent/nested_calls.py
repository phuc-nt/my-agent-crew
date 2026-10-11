"""What a script's own calls tell the turn while the script still runs.

A tool's result arrives when the tool is over. A script is a tool that makes calls of its
own, and may run for minutes: the person watching should see each call as it ends, and
what it cost, not all of them at the end. So the turn hands the call being carried out a
place to say so, in a context variable as `tool_call_id` is, and the script says so through
`note_nested_call`. Where nothing listens, saying so does nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar

from my_agent_crew.tools.result import NestedCall

Sink = Callable[[NestedCall], None]

_sink: ContextVar[Sink | None] = ContextVar("nested_call_sink", default=None)


def set_nested_sink(sink: Sink | None) -> None:
    """Set inside the task that carries one call out, so it is that call's alone."""
    _sink.set(sink)


def note_nested_call(call: NestedCall) -> None:
    sink = _sink.get()
    if sink is not None:
        sink(call)
