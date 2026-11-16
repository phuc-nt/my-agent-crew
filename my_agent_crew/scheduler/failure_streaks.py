"""The failures in a row each job is in, which the jobs page shows under its last run.

One failed run reads the same on the page as a job that has been down for a week, so the
clock keeps, for each job, how many of its runs in a row failed and since when. A run that
counts is one that failed and opened no conversation (a script, a command, a rewrite of
memory), or one that ended well and whose check then disagreed (`check.py`). A turn that
failed is its conversation's to show, as any turn's ending is. Any other ending closes the
streak. A job skipped under the day's cap was not run, and leaves the count as it was
(`day_cap.py`). Nobody is told of a streak on any channel: the web's inbox and its push say
that a job failed (`webpush/notices.py`), and the page says for how long.

Kept in the store as well as here (`store/job_streaks.py`): a host that sleeps when idle
starts the process again on every wake, and a count begun again each time would read as a
job that just started failing. What is read back at the start is every job still on the
clock.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from my_agent_crew.store.db import Store
from my_agent_crew.store.runs import FAILED, RunRecord


def counts_as_failure(run: RunRecord, check_failed: bool) -> bool:
    """Whether the run a job came to adds to its streak."""
    return check_failed or (run.status == FAILED and run.conversation_id is None)


@dataclass(frozen=True)
class Streak:
    """The failures in a row one job is in. Never changed in place: each step makes a new
    one, so a reader on another thread sees one whole state or the next."""

    count: int
    since: datetime

    def to_dict(self) -> dict[str, Any]:
        """As a job's row shows it (`describe.py`): on the clock's own time and to the
        minute, as the row's next run is."""
        return {"count": self.count, "since": self.since.isoformat(timespec="minutes")}


class Streaks:
    def __init__(self, store: Store | None = None, known: Collection[str] | None = None):
        """`store` is where the counts outlive the process; `known` the jobs on the clock,
        so a count kept for a job that left while the process was down goes with it."""
        self._kept = store.streaks if store is not None else None
        # Written on the event loop only. `of` is asked from a thread-pool thread
        # (`Scheduler.describe`), so it reads one key and never walks the dict.
        self._held: dict[str, Streak] = {}
        for job_id, (count, since) in (self._kept.all() if self._kept else {}).items():
            if known is not None and job_id not in known:
                self._kept.clear(job_id)
                continue
            self._held[job_id] = Streak(count, datetime.fromisoformat(since))

    def of(self, job_id: str) -> Streak | None:
        return self._held.get(job_id)

    def forget(self, job_id: str) -> Streak | None:
        """A job that left the clock leaves no count for one that later takes its id."""
        if self._kept is not None:
            self._kept.clear(job_id)
        return self._held.pop(job_id, None)

    def forget_agent(self, agent_id: str) -> None:
        """Every job of an agent's, read off the id as the store's switches are."""
        prefix = f"{agent_id}/"
        for job_id in [held for held in self._held if held.startswith(prefix)]:
            self._held.pop(job_id, None)
        if self._kept is not None:
            self._kept.forget_agent(agent_id)

    def settle(self, job_id: str, failed: bool, now: datetime) -> None:
        """Counts one more failure in a row at `now`, or closes the streak."""
        if not failed:
            self.forget(job_id)
            return
        before = self._held.get(job_id)
        streak = Streak(before.count + 1, before.since) if before else Streak(1, now)
        self._held[job_id] = streak
        if self._kept is not None:
            self._kept.save(job_id, streak.count, streak.since.isoformat())
