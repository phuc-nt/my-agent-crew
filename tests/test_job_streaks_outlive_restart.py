"""A job's failures in a row are counted across a restart (`scheduler/failure_streaks.py`,
`store/job_streaks.py`).

A host that sleeps when idle starts the process again on every wake. Counted in memory
alone, a job failing every hour would read on its row as one that had just begun failing,
every hour. Here the restart is a second clock and hub over the store the first ones wrote
to.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.scheduler import Scheduler, jobs
from my_agent_crew.scheduler.failure_streaks import Streak, Streaks
from my_agent_crew.store.db import Store
from tests.test_job_failure_streaks import EVERY_FIVE, SYNC, Rig, Shell, clocked, stamps
from tests.test_scheduler import with_schedules


@pytest.fixture
def shell(monkeypatch) -> Shell:
    shell = Shell()
    monkeypatch.setattr(jobs, "run_shell", shell)
    return shell


@pytest.fixture
def rig(deps_factory, shell) -> Rig:
    return clocked(deps_factory(), shell, EVERY_FIVE)


def restarted(rig: Rig) -> Rig:
    """The process begun again: a new clock over the jobs and a new hub, with the store and
    the time of day where the old ones left them."""
    hub = ActivityHub(rig.deps.store)
    sched = Scheduler({"default": rig.deps}, hub, clock=rig.clock)
    return Rig(sched, rig.clock, rig.shell, rig.deps)


async def test_the_count_and_its_start_are_read_back_after_a_restart(rig):
    await rig.tick()
    await rig.tick()

    woken = restarted(rig)
    assert woken.failing() == stamps("07:05", count=2)
    await woken.tick()

    assert woken.failing() == stamps("07:05", count=3)


async def test_a_restart_at_every_run_counts_as_one_long_run_would(rig):
    """What the store is for: an hour between runs, and the process begun again for each."""
    for _ in range(13):
        rig = restarted(rig)
        await rig.tick(hours=1)

    assert rig.failing() == stamps("08:00", count=13)


async def test_a_job_that_mends_after_a_restart_leaves_no_row(rig):
    await rig.tick()
    await rig.tick()
    assert set(rig.deps.store.streaks.all()) == {SYNC}

    woken = restarted(rig)
    woken.shell.mends()
    await woken.tick()

    assert woken.failing() is None and rig.deps.store.streaks.all() == {}
    # And to the process after that one, the job never failed.
    assert restarted(woken).failing() is None


async def test_the_count_of_a_job_no_file_states_after_the_restart_goes(rig, shell):
    await rig.tick()
    other = Schedule("pull", "Kéo thư", every="5m", command="pull-mail")
    with_schedules(rig.deps, other)

    woken = restarted(rig)

    assert rig.deps.store.streaks.all() == {}
    # A job later stated under the id begins its own count.
    with_schedules(rig.deps, EVERY_FIVE)
    woken.sched.reload_profiles()
    await woken.tick()
    assert woken.failing() == stamps("07:10")


async def test_a_job_and_an_agent_that_leave_take_what_was_kept_with_them(rig):
    await rig.tick()
    with_schedules(rig.deps)
    rig.sched.reload_profiles()
    assert rig.deps.store.streaks.all() == {}

    kept = rig.deps.store.streaks
    kept.save("coder/sync", 2, "2026-09-19T07:05:00")
    kept.save("coder-two/sync", 1, "2026-09-19T07:05:00")
    rig.sched.forget_agent("coder")
    assert set(kept.all()) == {"coder-two/sync"}


def test_the_moment_a_count_began_on_a_clock_that_knows_its_zone_is_read_back_as_written(
    tmp_path,
):
    """The server's clock is aware (`Settings.now`)."""
    at = datetime(2026, 9, 19, 7, 5, tzinfo=UTC)
    store = Store(tmp_path / "agent.sqlite3")
    Streaks(store).settle(SYNC, True, at)
    store.close()

    store = Store(tmp_path / "agent.sqlite3")  # the file opened again, as a start opens it
    streaks = Streaks(store)
    assert streaks.of(SYNC) == Streak(1, at)
    streaks.settle(SYNC, True, at + timedelta(minutes=5))
    assert store.streaks.all() == {SYNC: (2, at.isoformat())}
    streaks.settle(SYNC, False, at + timedelta(minutes=10))
    assert store.streaks.all() == {}


def test_a_database_made_before_the_counts_were_kept_gains_their_table(tmp_path):
    path = tmp_path / "agent.sqlite3"
    Store(path).close()
    old = sqlite3.connect(path)
    old.execute("DROP TABLE job_failure_streaks")
    old.execute("INSERT INTO job_state (job_id, enabled, updated_at) VALUES ('a/b', 0, 'x')")
    old.commit()
    old.close()

    store = Store(path)

    assert store.streaks.all() == {}
    store.streaks.save("a/b", 1, "2026-09-19T07:05:00")
    assert store.streaks.all() == {"a/b": (1, "2026-09-19T07:05:00")}
    assert store.jobs.enabled("a/b") is False, "what the file held is as it was"


def test_a_database_that_kept_when_the_person_was_told_still_counts(tmp_path):
    """A home made while a failing job was told to the chat holds a `told_at` column, and
    a row with it, written then. The count reads it back and writes on past it."""
    path = tmp_path / "agent.sqlite3"
    Store(path).close()
    old = sqlite3.connect(path)
    old.execute("DROP TABLE job_failure_streaks")
    old.execute(
        "CREATE TABLE job_failure_streaks (job_id TEXT PRIMARY KEY, count INTEGER NOT NULL,"
        " since TEXT NOT NULL, told_at TEXT)"
    )
    old.execute(
        "INSERT INTO job_failure_streaks VALUES ('a/b', 3, '2026-09-19T07:05:00', "
        "'2026-09-19T07:05:00')"
    )
    old.commit()
    old.close()

    store = Store(path)

    assert store.streaks.all() == {"a/b": (3, "2026-09-19T07:05:00")}
    store.streaks.save("a/b", 4, "2026-09-19T07:05:00")
    store.streaks.save("c/d", 1, "2026-09-19T08:00:00")
    assert store.streaks.all() == {
        "a/b": (4, "2026-09-19T07:05:00"),
        "c/d": (1, "2026-09-19T08:00:00"),
    }
