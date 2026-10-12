"""How often the person is told of a job that keeps failing.

A job that fails every five minutes would otherwise say so every five minutes, and a chat
that repeats itself all day is one nobody reads. So the clock keeps, for each job, the
failures in a row it is in: how many, since when, and when the person was last told. The
first is told at once. While the job goes on failing, at most one message every
`RETELL_AFTER` says how long it has gone on and why the latest run failed; a failure in
between is only counted. When the job runs well again the streak ends, with one line if
the person had been told of it and none if they had not.

A failure is one `failure_notice.py` has a message for: a run that failed and opened no
conversation. Any other ending closes the streak, and only a run that ended well is worth
the line.

Told means the channel took the message. One that was not sent, was not said in time, or
had no channel to go to leaves the streak untold, so the next failure tries again and says
how many there have been by then. While a message is on its way the streak says so: a
send can take up to a minute, and whoever reads the job's row meanwhile is not to be told
that nothing got through.

Kept in memory, not in the store: a restart begins every job's count again, and a job
still failing after it is told at once.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from my_agent_crew import texts_job_failure as words
from my_agent_crew.activity.step_previews import preview
from my_agent_crew.scheduler.failure_notice import Notify, failure_notice, say
from my_agent_crew.scheduler.jobs import Job
from my_agent_crew.store.runs import DONE, RunRecord

RETELL_AFTER = timedelta(hours=6)


def _stamp(moment: datetime | None) -> str | None:
    return moment.isoformat(timespec="minutes") if moment else None


@dataclass(frozen=True)
class Streak:
    """The failures in a row one job is in. Never changed in place: each step makes a new
    one, so a reader on another thread sees one whole state or the next."""

    count: int
    since: datetime
    # When the channel last took a message of this streak; None while none got through.
    told_at: datetime | None = None
    # A message of this streak is on its way to the channel, and may or may not be taken.
    telling: bool = False

    def due(self, now: datetime) -> bool:
        """Whether a failure at `now` is told: nothing of this streak was yet, or what was
        is `RETELL_AFTER` old."""
        return self.told_at is None or now - self.told_at >= RETELL_AFTER

    def to_dict(self) -> dict[str, Any]:
        """As a job's row shows it (`describe.py`): on the clock's own time and to the
        minute, as the row's next run is."""
        again = self.told_at + RETELL_AFTER if self.told_at else None
        return {
            "count": self.count,
            "since": _stamp(self.since),
            "told_at": _stamp(self.told_at),
            "next_notice_at": _stamp(again),
            "telling": self.telling,
        }


def closing(streak: Streak) -> str:
    """The line a message of a failure ends on: when the next one comes, and from the second
    failure in a row how long the job has been failing."""
    hours = RETELL_AFTER // timedelta(hours=1)
    if streak.count == 1:
        return words.JOB_FAILED_NEXT.format(hours=hours)
    since = streak.since.strftime(words.JOB_FAILING_SINCE)
    return words.JOB_FAILED_AGAIN.format(count=streak.count, since=since, hours=hours)


class Streaks:
    def __init__(self, notify: Notify | None, clock: Callable[[], datetime]):
        self._notify, self._clock = notify, clock
        # Written on the event loop only. `of` is asked from a thread-pool thread
        # (`Scheduler.describe`), so it reads one key and never walks the dict.
        self._held: dict[str, Streak] = {}

    def of(self, job_id: str) -> Streak | None:
        return self._held.get(job_id)

    def forget(self, job_id: str) -> None:
        """A job that left the clock leaves no count for one that later takes its id."""
        self._held.pop(job_id, None)

    def forget_agent(self, agent_id: str) -> None:
        """Every job of an agent's, read off the id as the store's switches are."""
        prefix = f"{agent_id}/"
        for job_id in [held for held in self._held if held.startswith(prefix)]:
            self._held.pop(job_id, None)

    async def settle(self, job: Job, run: RunRecord, ended_by: str) -> None:
        """Counts the run a job came to, and tells the person what the count calls for.
        `ended_by` is why the run failed, as `failure_notice` takes it."""
        text = failure_notice(job, run, ended_by)
        if text is None:
            await self._close(job, run)
            return
        now = self._clock()
        before = self._held.get(job.id)
        streak = replace(before, count=before.count + 1) if before else Streak(1, now)
        self._held[job.id] = streak
        if not streak.due(now):
            return
        self._held[job.id] = replace(streak, telling=True)
        sent = False
        try:
            sent = await say(job, f"{text}\n{closing(streak)}", self._notify)
        finally:
            # Read again, not written from `streak`: the send waited, and by now the job may
            # have left the clock, or another run of it may have been counted. In a
            # `finally`, so a send cut short does not leave the row saying one is under way.
            held = self._held.get(job.id)
            if held is not None:
                told_at = self._clock() if sent else held.told_at
                self._held[job.id] = replace(held, telling=False, told_at=told_at)

    async def _close(self, job: Job, run: RunRecord) -> None:
        streak = self._held.pop(job.id, None)
        if streak is None or streak.told_at is None or run.status != DONE:
            return
        name = preview(job.schedule.name)
        await say(job, words.JOB_RECOVERED.format(name=name, count=streak.count), self._notify)
