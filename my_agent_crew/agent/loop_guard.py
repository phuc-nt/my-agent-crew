"""Stopping a turn that keeps making the same tool calls.

A model stuck on a command that fails repeats it word for word until the step limit: a
long, paid way to get nowhere. The guard reads the tool calls of each model call as one
signature and counts identical signatures in a row. At the threshold the model is told it
is repeating itself; if it carries on for as many calls again, the turn halts before the
last one runs.

Only calls in a row count. "Run the tests, fix, run the tests" changes something in
between, and that is how work gets done. A model call with no tool calls, or with only a
progress note or a question to the person, starts the count over, and so does a new
message from the person: each `run_turn` has a guard of its own.

The reminder is stored in the person's role, so it names the tools and quotes neither their
arguments nor their results: fetched text must never reach the model as the person's words.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from my_agent_crew import texts
from my_agent_crew.llm.types import Message
from my_agent_crew.store import Store, StoredMessage
from my_agent_crew.tools.ask_user import ASK_USER_TOOL_NAME
from my_agent_crew.tools.progress_note import PROGRESS_NOTE_TOOL_NAME

THRESHOLD = 3
EXEMPT = frozenset({PROGRESS_NOTE_TOOL_NAME, ASK_USER_TOOL_NAME})
OK, REDIRECT, HALT = "ok", "redirect", "halt"


def _arguments(arguments: Mapping[str, Any]) -> str:
    return json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str)


def _signature(call: Mapping[str, Any]) -> str:
    return f"{call['name']} {_arguments(call['arguments'])} {call.get('invalid', '')}"


class LoopGuard:
    def __init__(self, threshold: int = THRESHOLD, exempt: Iterable[str] = EXEMPT) -> None:
        self.threshold = threshold
        self.exempt = frozenset(exempt)
        self.redirect_due = False
        self.reset()

    def reset(self) -> None:
        """Forget the current run of repeats, as a new message from the person does."""
        self._signature: tuple[str, ...] = ()
        self._names: list[str] = []
        self._repeats = 0
        self._redirected = False

    def observe(self, tool_calls: Sequence[Mapping[str, Any]]) -> str:
        """Takes one model call's tool calls (as the assistant event carries them) and says
        whether the turn goes on, is told it repeats itself, or halts. Parallel calls in
        another order are the same call; ids never count. A call whose arguments did not
        parse arrives with `{}` and counts by where it broke, so long documents cut off at
        different places are attempts, not repeats."""
        counted = [c for c in tool_calls if c["name"] not in self.exempt]
        signature = tuple(sorted(_signature(c) for c in counted))
        if not signature:
            self.reset()
            return OK
        if signature != self._signature:
            self.reset()
            self._signature = signature
            self._names = sorted({c["name"] for c in counted})
        self._repeats += 1
        if self._repeats < self.threshold:
            return OK
        if self._redirected:
            return HALT
        # Told once per run of repeats; the count starts over so the model gets as many
        # calls again to change course.
        self._redirected, self._repeats, self.redirect_due = True, 0, True
        return REDIRECT

    def redirect(self, store: Store, conv_id: str) -> list[StoredMessage]:
        """Appends the reminder after the repeated calls' results, before the next model
        call, and returns the history with it in place."""
        self.redirect_due = False
        note = texts.LOOP_REDIRECT.format(names=", ".join(self._names), count=self.threshold)
        store.append(conv_id, Message(role="user", content=note))
        return store.history(conv_id)
