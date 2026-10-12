"""Where one run of a script keeps things, and what it has written so far.

`store` and `load` are answered here, out of what the namespace held when the script first
asked and what the script wrote since: a script reads its own writes. None of them reaches
the table while it runs. They are applied together once it ended well (`commit`), so a
script that failed, was refused a call or ran out of time leaves things as it found them.

Where is settled here and never by the script. A job's script keeps under the job's own id,
and so does a script of the turn that job opened, which is how the two read each other. A
script of any other turn keeps under its conversation, and goes when the conversation is
deleted. An agent's scripts reach only what that agent kept, and only while it is of the
crew: what was put together for an agent that was since removed keeps nothing (`era`).

A turn's run is saved before the first of its events is read (`activity/tracked.py`), so it
is on record, with where it came from, before any script of the turn can run, and after a
restart too. A turn somebody took up in a conversation a job once opened is theirs: its run
names no job, and its scripts keep under the conversation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_script_store as t
from my_agent_crew.agent.turn_context import JOB, turn_conversation_id
from my_agent_crew.script import limits
from my_agent_crew.script.kept import LOAD, as_text, checked_key
from my_agent_crew.script.limits import ScriptError
from my_agent_crew.store.script_store import (
    ScriptStore,
    conversation_namespace,
    held_chars,
    job_namespace,
)

if TYPE_CHECKING:
    from my_agent_crew.agent.loop import AgentDeps


@dataclass
class Kept:
    """One run's view of one namespace. `answer` is what `ScriptRun` asks (`nested.py`)."""

    table: ScriptStore
    agent_id: str
    namespace: str
    # Which agent of that id the script runs for (`ScriptStore.era`).
    era: int = 0
    # The namespace as this run sees it, read the first time the script asks, and its size.
    _held: dict[str, str] | None = None
    _chars: int = 0
    # What the script wrote, by key: the last value as JSON text, or None for a key dropped.
    _writes: dict[str, str | None] = field(default_factory=dict)

    def _seen(self) -> dict[str, str]:
        if self._held is None:
            self._held = self.table.read(self.agent_id, self.namespace)
            self._chars = held_chars(self._held)
        return self._held

    def answer(self, kind: str, arguments: dict[str, Any]) -> Any:
        """A `load` is answered with the value as JSON text, or None for a key that holds
        nothing. A `store` is answered with nothing; one that does not fit is a mistake the
        script may catch, and is not among what is written."""
        key = checked_key(arguments.get("key"))
        held = self._seen()
        if kind == LOAD:
            return held.get(key)
        value = arguments.get("value")
        text = None if value is None else as_text(value)
        without = self._chars - (len(key) + len(held[key]) if key in held else 0)
        after = without if text is None else without + len(key) + len(text)
        most = limits.MAX_STORE_TOTAL_CHARS
        if text is not None and after > most:
            raise ScriptError(t.STORE_FULL.format(size=after, most=most))
        if text is None:
            held.pop(key, None)
        else:
            held[key] = text
        self._chars = after
        self._writes[key] = text
        return None

    def commit(self) -> str | None:
        """Applies what the script wrote, for a script that ended well. None when it is kept
        or there was nothing to keep; else the words its answer ends on, since none of it
        was: the agent was removed, or the namespace was written by another run meanwhile
        and no longer has the room."""
        if not self._writes:
            return None
        most = limits.MAX_STORE_TOTAL_CHARS
        if self.table.apply(self.agent_id, self.namespace, self._writes, most, self.era):
            return None
        if self.table.era(self.agent_id) != self.era:
            return t.STORE_AGENT_GONE
        return t.STORE_NOT_KEPT.format(most=most)


def _schedule_named(source: str) -> str:
    """The schedule a run's source names (`job:<agent id>/<schedule id>`), or "" for none."""
    prefix = f"{JOB}:"
    return source[len(prefix) :].partition("/")[2] if source.startswith(prefix) else ""


def _kept(deps: AgentDeps, namespace: str) -> Kept:
    """A namespace as a script of that agent keeps it: of the agent as it was put together,
    which a turn or a job goes on holding after the agent was removed."""
    return Kept(deps.store.script_store, deps.agent.id, namespace, deps.kept_era)


def turn_kept(deps: AgentDeps) -> Kept | None:
    """Where a script of the turn now running keeps things; None outside any conversation,
    where there is nowhere."""
    conv_id = turn_conversation_id()
    if not conv_id:
        return None
    run = deps.store.runs.latest_for_conversation(conv_id)
    schedule_id = _schedule_named(run.source) if run is not None else ""
    namespace = job_namespace(schedule_id) if schedule_id else conversation_namespace(conv_id)
    return _kept(deps, namespace)


def job_kept(deps: AgentDeps, schedule_id: str) -> Kept:
    """Where the script a schedule runs keeps things: under the schedule's own id."""
    return _kept(deps, job_namespace(schedule_id))
