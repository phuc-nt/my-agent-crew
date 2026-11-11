"""The day's cap on what scheduled jobs may cost (`scheduler/day_cap.py`).

`jobs_daily_cost_cap_usd` in `config.yaml` is how much the runs of scheduled jobs may cost
in one day of the home's. Once the day has spent it, a job that would call a model is not
run: it leaves a halted run that says why, and the person is told once that day. A command
job runs as ever, the next day starts from nothing, and with no cap set nothing changes.

What a day has spent is read off the runs the store keeps. Most tests here stand on a day
far ahead, where no run of the test's own making falls, and write the day's spending as the
runs it would have left; the first test spends through real runs on the day it is run.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from my_agent_crew import texts_job_cap as words
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.config import load_settings
from my_agent_crew.config_yaml import YAML_KEYS
from my_agent_crew.llm.fake import completion
from my_agent_crew.scheduler import Scheduler, jobs
from my_agent_crew.server import create_app
from my_agent_crew.store.db import Store
from my_agent_crew.store.runs import DONE, FAILED, HALTED, RunRecord
from my_agent_crew.store.stamps import new_id
from tests.test_job_failure_streaks import Chat, Clock, Shell
from tests.test_scheduler import with_schedules

ZONE = ZoneInfo("Asia/Ho_Chi_Minh")
# A day no run of a test's own falls on, at an hour that is still the day before in UTC.
MORNING = datetime(2099, 3, 10, 6, 0, tzinfo=ZONE)
BRIEF = Schedule("brief", "Bản tin sáng", every="5m", prompt="tin gì mới")
SYNC = Schedule("sync", "Đồng bộ", every="5m", command="sync-ledger")
CAP = 1.0


def skipped_by(spent: float, cap: float = CAP) -> str:
    return words.JOB_CAP_SKIPPED.format(spent=f"{spent:.2f}", cap=f"{cap:.2f}")


def reached(spent: float, cap: float = CAP, name: str = BRIEF.name) -> str:
    return words.JOB_CAP_REACHED.format(spent=f"{spent:.2f}", cap=f"{cap:.2f}", name=name)


def spend(deps: AgentDeps, usd: float, at: datetime, source: str = "job:default/earlier") -> None:
    """A run that cost `usd` and started at `at`, as the store would hold it."""
    stamp = at.astimezone(UTC).isoformat(timespec="seconds")
    run = RunRecord(new_id(), "default", None, source, "", DONE, stamp, spent_usd=usd)
    deps.store.runs.save(run)


class Day:
    """A clock over the jobs given, and the channel job notices go to."""

    def __init__(self, deps: AgentDeps, *schedules: Schedule, at: datetime = MORNING):
        self.deps = with_schedules(deps, *schedules)
        self.clock = Clock(at)
        self.chat = Chat(self.clock)
        self.sched = self.restarted()

    def restarted(self) -> Scheduler:
        hub = ActivityHub(self.deps.store)
        self.sched = Scheduler({"default": self.deps}, hub, clock=self.clock, notify=self.chat)
        return self.sched

    async def run(self, job: str = "brief") -> RunRecord:
        return await self.sched.run_job(f"default/{job}")

    @property
    def asked_model(self) -> int:
        return len(self.deps.chain.providers["scripted"].requests)


@pytest.fixture
def capped(deps_factory):
    """Deps whose home caps a day's jobs at `CAP`, with a model that answers each turn."""

    def build(cap: float = CAP, turns: int = 4) -> AgentDeps:
        return deps_factory(
            script=[completion("Không có gì mới.", cost_usd=0.4) for _ in range(turns)],
            jobs_daily_cost_cap_usd=cap,
            timezone="Asia/Ho_Chi_Minh",
        )

    return build


@pytest.fixture
def shell(monkeypatch) -> Shell:
    shell = Shell()
    shell.mends()
    monkeypatch.setattr(jobs, "run_shell", shell)
    return shell


# --- the day's spending, through real runs ---


async def test_jobs_run_under_the_cap_and_are_skipped_once_the_day_has_spent_it(capped):
    day = Day(capped(), BRIEF, at=datetime.now(ZONE))

    ran = [await day.run() for _ in range(3)]

    # 0.40 and 0.80 are under the cap, so three ran, and the third took the day to 1.20.
    assert [(run.status, run.spent_usd) for run in ran] == [(DONE, 0.4)] * 3
    assert day.chat.asked == []

    skipped = await day.run()

    assert (skipped.status, skipped.conversation_id) == (HALTED, None)
    assert (skipped.summary, skipped.steps, skipped.spent_usd) == (skipped_by(1.2), [], 0.0)
    assert skipped.source == "job:default/brief" and skipped.finished_at
    assert day.asked_model == 3
    assert day.chat.texts == [reached(1.2)]
    assert day.chat.texts[0] == (
        "Chi phí các lịch chạy hôm nay đã là 1.20 USD, chạm hạn mức 1.00 USD một ngày.\n"
        'Từ giờ đến hết ngày, các lịch gọi model bị bỏ qua, bắt đầu từ "Bản tin sáng"; lịch'
        " chạy lệnh vẫn chạy, và trò chuyện không bị ảnh hưởng.\n"
        "Đổi hạn mức ở khoá jobs_daily_cost_cap_usd trong config.yaml."
    )
    [row] = day.sched.describe()
    assert row["last_run"]["id"] == skipped.id and row["last_run"]["summary"] == skipped_by(1.2)

    # Two days on, none of that is the day's: the job runs again.
    day.clock.after(days=2)
    assert (await day.run()).status == DONE
    assert day.asked_model == 4 and len(day.chat.texts) == 1


# --- the day's spending, as the runs it left ---


async def test_spending_exactly_the_cap_is_the_cap_reached(capped):
    day = Day(capped(), BRIEF)
    spend(day.deps, 0.75, MORNING - timedelta(hours=1))
    assert (await day.run()).status == DONE

    spend(day.deps, 0.25, MORNING)

    skipped = await day.run()
    assert (skipped.status, skipped.summary) == (HALTED, skipped_by(1.0))


async def test_the_person_is_told_once_a_day_and_again_on_a_later_day(capped):
    day = Day(capped(), BRIEF)
    spend(day.deps, 1.5, MORNING)

    for _ in range(3):
        day.clock.after(minutes=5)
        [run] = await day.sched.tick()
        assert run.status == HALTED

    assert day.chat.texts == [reached(1.5)] and day.asked_model == 0

    # The next day has spent nothing, so the job runs and nothing is said.
    day.clock.after(days=1)
    [run] = await day.sched.tick()
    assert run.status == DONE and len(day.chat.texts) == 1

    # A day that reaches the cap too is told of on its own.
    spend(day.deps, 2, day.clock.at)
    day.clock.after(minutes=5)
    [run] = await day.sched.tick()
    assert run.status == HALTED
    assert day.chat.texts == [reached(1.5), reached(2.0)]


async def test_the_day_is_the_homes_day_not_utcs(capped):
    """06:00 on the 10th in the home's zone is 23:00 on the 9th in UTC. What was spent at
    23:30 the evening before, home time, is yesterday's; what was spent at 00:30 is today's,
    though both fall on the 9th in UTC."""
    day = Day(capped(), BRIEF)
    spend(day.deps, 5, datetime(2099, 3, 9, 23, 30, tzinfo=ZONE))
    assert (await day.run()).status == DONE

    spend(day.deps, 5, datetime(2099, 3, 10, 0, 30, tzinfo=ZONE))

    assert (await day.run()).summary == skipped_by(5.0)


async def test_a_clock_with_no_zone_of_its_own_reads_the_day_in_the_homes(capped):
    day = Day(capped(), BRIEF, at=MORNING.replace(tzinfo=None))
    spend(day.deps, 5, datetime(2099, 3, 10, 0, 30, tzinfo=ZONE))

    assert (await day.run()).status == HALTED


async def test_only_what_scheduled_jobs_cost_counts(capped):
    day = Day(capped(), BRIEF)
    for source in ("web", "telegram", "memory:wiki", "jobless", "delegate:job:default/brief"):
        spend(day.deps, 9, MORNING, source=source)

    assert (await day.run()).status == DONE
    assert day.chat.asked == []


async def test_a_command_job_runs_whatever_the_day_has_spent(capped, shell):
    day = Day(capped(), BRIEF, SYNC)
    spend(day.deps, 3, MORNING)

    run = await day.run("sync")

    assert (run.status, shell.ran) == (DONE, 1)
    # It calls no model, so it is not what the person is told the cap skipped either.
    assert day.chat.asked == []
    assert (await day.run()).status == HALTED
    assert day.chat.texts == [reached(3.0)]


async def test_every_job_that_would_call_a_model_is_skipped(capped):
    script = Schedule("sum", "Tổng kết", every="5m", script="print(1)", then_prompt="tóm tắt")
    day = Day(capped(), BRIEF, script)
    spend(day.deps, 1, MORNING)

    runs = [await day.run("brief"), await day.run("sum")]

    assert [(run.status, run.summary) for run in runs] == [(HALTED, skipped_by(1.0))] * 2
    assert day.chat.texts == [reached(1.0)]


async def test_with_no_cap_set_a_day_spends_what_it_spends(capped):
    day = Day(capped(cap=0.0), BRIEF)
    spend(day.deps, 500, MORNING)

    run = await day.run()

    assert run.status == DONE and day.chat.asked == []
    assert not day.deps.store.job_cap.told(MORNING.date().isoformat())


# --- once a day, and only when it got there ---


async def test_a_restart_does_not_tell_the_same_day_again(capped):
    day = Day(capped(), BRIEF)
    spend(day.deps, 1, MORNING)
    await day.run()

    day.restarted()

    assert (await day.run()).status == HALTED
    assert day.chat.texts == [reached(1.0)]
    assert day.deps.store.job_cap.told("2099-03-10")
    assert not day.deps.store.job_cap.told("2099-03-11")


async def test_a_message_the_channel_did_not_take_is_tried_with_the_next_job_skipped(capped):
    day = Day(capped(), BRIEF)
    spend(day.deps, 1, MORNING)
    day.chat.answer = False

    await day.run()
    assert len(day.chat.asked) == 1 and day.chat.took == []

    day.chat.answer = True
    await day.run()
    await day.run()

    assert len(day.chat.asked) == 2 and day.chat.texts == [reached(1.0)]


async def test_a_clock_with_nobody_to_tell_still_skips(capped):
    day = Day(capped(), BRIEF)
    day.sched = Scheduler({"default": day.deps}, ActivityHub(day.deps.store), clock=day.clock)
    spend(day.deps, 1, MORNING)

    assert (await day.run()).status == HALTED
    assert not day.deps.store.job_cap.told("2099-03-10")


async def test_a_job_skipped_is_neither_a_failure_nor_a_recovery(capped, shell):
    """A job whose check has been failing keeps its count through a skip: the skip did not
    run it, so it says nothing of whether it works again."""
    checked = Schedule("brief", BRIEF.name, every="5m", prompt="tin gì mới", check="test -s a")
    day = Day(capped(), checked)
    shell.breaks()
    assert (await day.run()).status == FAILED
    before = day.sched.describe()[0]["failing"]
    assert before["count"] == 1 and len(day.chat.texts) == 1

    spend(day.deps, 1, MORNING)
    skipped = await day.run()

    assert skipped.status == HALTED
    assert day.sched.describe()[0]["failing"] == before
    assert day.deps.store.streaks.all().keys() == {"default/brief"}
    # The one message since is the cap's.
    assert day.chat.texts[1:] == [reached(1.0)]


# --- the key ---


def test_the_key_is_read_from_the_file_and_the_environment_wins(tmp_path: Path):
    home = {"MY_AGENT_HOME": str(tmp_path)}
    assert load_settings(env=home).jobs_daily_cost_cap_usd == 0.0

    (tmp_path / "config.yaml").write_text("jobs_daily_cost_cap_usd: 2.5\n")

    assert "jobs_daily_cost_cap_usd" in YAML_KEYS
    assert load_settings(env=home).jobs_daily_cost_cap_usd == 2.5
    over = {**home, "MY_AGENT_JOBS_DAILY_COST_CAP_USD": "4"}
    assert load_settings(env=over).jobs_daily_cost_cap_usd == 4.0


@pytest.mark.parametrize("value", ["-1", "-0.01", ".nan"])
def test_a_cap_below_nothing_stops_the_start(tmp_path: Path, value: str):
    (tmp_path / "config.yaml").write_text(f"jobs_daily_cost_cap_usd: {value}\n")

    with pytest.raises(ValueError, match="jobs_daily_cost_cap_usd must be >= 0"):
        load_settings(env={"MY_AGENT_HOME": str(tmp_path)})


def test_the_settings_page_is_given_the_cap(capped):
    with TestClient(create_app(capped(cap=2.5)), base_url="http://127.0.0.1") as client:
        body: dict[str, Any] = client.get("/api/settings").json()

    assert body["jobs_daily_cost_cap_usd"] == 2.5


def test_a_database_made_before_the_cap_gains_its_table(tmp_path: Path):
    path = tmp_path / "agent.sqlite3"
    old = Store(path)
    old._conn.execute("DROP TABLE job_cap_days")
    old._conn.commit()
    old.close()

    again = Store(path)

    assert not again.job_cap.told("2099-03-10")
    again.job_cap.tell("2099-03-10", "2099-03-09T23:00:00+00:00")
    again.job_cap.tell("2099-03-10", "2099-03-09T23:05:00+00:00")
    assert again.job_cap.told("2099-03-10")
