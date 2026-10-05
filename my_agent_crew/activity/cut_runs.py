"""What the hub does about a run that stopped without reaching its end.

Stopped by a person, or by a failure, it is closed as interrupted. Stopped because the
server itself is going down, it is left open in the store, and the server that starts next
closes it and may take it up again (`turn_resume.py`): once, which `RunRecord.resumed`
records, so a turn that takes the server down with it is not started again at every boot."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from my_agent_crew.activity.step_lookup import pending_model_step
from my_agent_crew.store.runs import ACTIVE_STATUSES, FAILED, RUNNING, RunRecord

if TYPE_CHECKING:
    from my_agent_crew.activity.busy import Busy
    from my_agent_crew.activity.watchers import Watchers
    from my_agent_crew.store import Store

INTERRUPTED = "interrupted"


class CutRuns:
    _store: Store
    _live: dict[str, RunRecord]
    _watchers: Watchers
    busy: Busy
    finish: Any
    # The runs the previous process was still working on, closed when this one started.
    cut: list[RunRecord]
    # Taken up again, their turn not started yet: the turn that starts next in the
    # conversation continues such a run instead of opening a new one.
    _held: set[str]
    # True from the moment the server begins to shut down.
    going_down: bool = False

    def reopen(self, run: RunRecord) -> None:
        """Takes up a run the restart cut. It is the same run, so the turn keeps its start
        (`after_seq`), its timeline and its spend, and its conversation is busy again from
        here on. The model call that died with the process leaves no step behind."""
        if pending_model_step(run) is not None:
            run.steps.pop()
        run.status, run.finished_at, run.summary, run.resumed = RUNNING, None, "", True
        self._live[run.id] = run
        self._held.add(run.id)
        self._store.runs.save(run)
        self._watchers.broadcast({"type": "run", "run": run.to_dict()})

    def holding(self, run: RunRecord) -> bool:
        """Whether the run was taken up again and no turn has continued it yet."""
        return run.id in self._held

    def interrupt(self, run: RunRecord) -> None:
        """A turn that stopped short of its end. While the server goes down its run stays
        as the store has it, still running, for the next process to settle."""
        if self.going_down:
            self._live.pop(run.id, None)
            self._held.discard(run.id)
            return
        self.finish(run, status=FAILED, summary=INTERRUPTED)

    def settled_run(self, conversation_id: str) -> RunRecord | None:
        """The conversation's last run, when it is over and nothing has begun since: what a
        wait on that run is answered with when the run ended in a process that is gone."""
        if self.busy.busy(conversation_id):
            return None
        run = self._store.runs.latest_for_conversation(conversation_id)
        return run if run is not None and run.status not in ACTIVE_STATUSES else None
