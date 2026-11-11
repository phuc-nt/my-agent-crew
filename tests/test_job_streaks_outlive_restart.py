"""A job's failures in a row are counted across a restart (`scheduler/failure_streaks.py`,
`store/job_streaks.py`).

A host that sleeps when idle starts the process again on every wake. Counted in memory
alone, a job failing every hour was a first failure every hour: told each time, never by
how long it had gone on, and never said to have mended. Here the restart is a second
clock, hub and channel over the store the first ones wrote to.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.scheduler import Job, Scheduler, jobs
from my_agent_crew.scheduler.failure_streaks import RETELL_AFTER, Streaks
from my_agent_crew.store.db import Store
from my_agent_crew.store.runs import DONE, FAILED, RunRecord
from tests.test_job_failure_streaks import (
    EVERY_FIVE,
    SYNC,
    Chat,
    Rig,
    Shell,
    again,
    clocked,
    first,
    mended,
    stamps,
)
from tests.test_scheduler import with_schedules


@pytest.fixture
def shell(monkeypatch) -> Shell:
    shell = Shell()
    monkeypatch.setattr(jobs, "run_shell", shell)
    return shell


@pytest.fixture
def rig(deps_factory, shell) -> Rig:
    return clocked(deps_factory(), shell, EVERY_FIVE)


def restarted(rig: Rig, answer: object = True) -> Rig:
    """The process begun again: a new clock over the jobs, a new hub and a new channel,
    with the store and the time of day where the old ones left them."""
    chat = Chat(rig.clock, answer)
    hub = ActivityHub(rig.deps.store)
    sched = Scheduler({"default": rig.deps}, hub, clock=rig.clock, notify=chat)
    return Rig(sched, rig.clock, chat, rig.shell, rig.deps)


async def test_a_job_still_failing_after_a_restart_is_not_told_again_inside_the_wait(rig):
    await rig.tick()
    assert rig.chat.texts == [first()]

    woken = restarted(rig)
    assert woken.failing() == stamps("07:05", "07:05", "13:05")
    await woken.tick()
    await woken.tick(hours=5, minutes=45)  # 13:00, five minutes short of the wait

    assert woken.shell.ran == 3 and woken.chat.asked == []
    assert woken.failing() == stamps("07:05", "07:05", "13:05", count=3)


async def test_a_restart_at_every_run_tells_of_a_failing_job_as_one_long_run_would(rig):
    """What the store is for: an hour between runs, and the process begun again for each."""
    told: list[str] = []
    for _ in range(13):
        rig = restarted(rig)
        await rig.tick(hours=1)
        told += rig.chat.texts

    since = "08:00 ngày 19/09"
    assert told == [first(), again(7, since=since), again(13, since=since)]


async def test_the_count_goes_on_after_a_restart_and_the_next_message_says_since_when(rig):
    await rig.tick()
    await rig.tick()

    woken = restarted(rig)
    await woken.tick(hours=5, minutes=55)  # 13:05, the wait to the minute

    assert woken.chat.texts == [again(3)]
    assert woken.failing() == stamps("07:05", "13:05", "19:05", count=3)


async def test_a_job_that_mends_after_a_restart_is_said_to_and_leaves_no_row(rig):
    await rig.tick()
    await rig.tick()
    assert set(rig.deps.store.streaks.all()) == {SYNC}

    woken = restarted(rig)
    woken.shell.mends()
    await woken.tick()

    assert woken.chat.texts == [mended(2)]
    assert woken.failing() is None and rig.deps.store.streaks.all() == {}
    # And to the process after that one, the job never failed.
    assert restarted(woken).failing() is None


async def test_a_failure_nobody_was_told_of_before_the_restart_is_told_at_the_next(rig):
    rig.chat.answer = False
    await rig.tick()
    assert rig.failing() == stamps("07:05")

    woken = restarted(rig)
    await woken.tick()

    assert woken.chat.texts == [again(2)]


async def test_a_message_on_its_way_when_the_process_went_is_not_kept_as_on_its_way(rig):
    held = rig.deps.store.streaks
    held.save(SYNC, 4, "2026-09-19T07:05:00", None)

    assert restarted(rig).failing() == stamps("07:05", count=4)


async def test_the_count_of_a_job_no_file_states_after_the_restart_goes(rig, shell):
    await rig.tick()
    other = Schedule("pull", "Kéo thư", every="5m", command="pull-mail")
    with_schedules(rig.deps, other)

    woken = restarted(rig)

    assert rig.deps.store.streaks.all() == {}
    # A job later stated under the id begins its own count, told at once.
    with_schedules(rig.deps, EVERY_FIVE)
    woken.sched.reload_profiles()
    await woken.tick()
    assert woken.chat.texts == [first()]


async def test_a_job_and_an_agent_that_leave_take_what_was_kept_with_them(rig):
    await rig.tick()
    with_schedules(rig.deps)
    rig.sched.reload_profiles()
    assert rig.deps.store.streaks.all() == {}

    kept = rig.deps.store.streaks
    kept.save("coder/sync", 2, "2026-09-19T07:05:00", None)
    kept.save("coder-two/sync", 1, "2026-09-19T07:05:00", None)
    rig.sched.forget_agent("coder")
    assert set(kept.all()) == {"coder-two/sync"}


async def test_the_moments_of_a_clock_that_knows_its_zone_are_read_back_as_written(tmp_path):
    """The server's clock is aware (`Settings.now`): the wait is still measured after a
    restart, and so is the moment the count began."""
    at = [datetime(2026, 9, 19, 7, 5, tzinfo=UTC)]
    job = Job(SYNC, "default", EVERY_FIVE)
    failed = RunRecord("r1", "default", None, f"job:{SYNC}", "Đồng bộ", FAILED, "2026-09-19")
    took: list[str] = []

    async def chat(agent_id: str, text: str) -> bool:
        took.append(text)
        return True

    store = Store(tmp_path / "agent.sqlite3")
    await Streaks(chat, lambda: at[0], store).settle(job, failed, "hỏng")
    store.close()

    store = Store(tmp_path / "agent.sqlite3")  # the file opened again, as a start opens it
    streaks = Streaks(chat, lambda: at[0], store)
    assert streaks.of(SYNC).since == at[0] and streaks.of(SYNC).told_at == at[0]
    at[0] += RETELL_AFTER - timedelta(minutes=1)
    await streaks.settle(job, failed, "hỏng")
    assert len(took) == 1
    at[0] += timedelta(minutes=1)
    await streaks.settle(job, failed, "hỏng")
    assert took[1] == again(3, reason="hỏng")
    await streaks.settle(job, RunRecord("r2", "default", None, "job", "x", DONE, "2026"), "")
    assert took[2] == mended(3) and store.streaks.all() == {}


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
    store.streaks.save("a/b", 1, "2026-09-19T07:05:00", None)
    assert store.streaks.all() == {"a/b": (1, "2026-09-19T07:05:00", None)}
    assert store.jobs.enabled("a/b") is False, "what the file held is as it was"
