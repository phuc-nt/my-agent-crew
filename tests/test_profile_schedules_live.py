"""A schedule an agent's file states is on the clock at once (`scheduler/table.py`,
`server/runtime_crew.py`).

The clock read each agent's schedules once, at the start: a row added, changed or taken out
waited for a restart, and the save said so. It now reads them again whenever an agent joins
the crew or is saved. What these tests hold is what a restart never had to decide, which is
from when a row that changed is judged. The clock keeps under each job's id the moment up to
which it was judged, and that mark moves only when the job runs. A new row, one whose timing
changed, and one its file switches on are judged from the save: the mark under their id is
that of a row that is no more, and judged from it the job ran at once for a time that had
passed. A row whose timing stayed keeps its mark, so a save of what it does never puts its
run off. A row taken out goes with its switch and its count of failures.

No command is run: `Shell` stands in for it and keeps what it was asked to run, and when.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.agents import templates_cli
from my_agent_crew.config import Settings, load_settings
from my_agent_crew.scheduler import jobs
from my_agent_crew.server.app import create_app
from my_agent_crew.server.credential_catalog import KNOWN
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.server.runtime_build import build_runtime
from my_agent_crew.store.runs import DONE, FAILED

MONDAY, TUESDAY = "2026-10-12", "2026-10-13"
JOB, MEMORY_JOB = "coder/sync", "coder/memory-consolidate"
# A file as a person writes one: an agent with one command due every five minutes.
BY_HAND = "name: Phụ việc\nschedules:\n  - id: sync\n    every: 5m\n    command: count\n"


def at(minute: str, day: str = MONDAY) -> datetime:
    return datetime.fromisoformat(f"{day}T{minute}")


def daily(hour: int, command: str = "sync", **more: Any) -> dict[str, Any]:
    return {"id": "sync", "cron": f"0 {hour} * * *", "command": command, **more}


def every(span: str, command: str = "sync", **more: Any) -> dict[str, Any]:
    return {"id": "sync", "every": span, "command": command, **more}


# Three rows of one agent, due together and judged in this order.
FIRST, SECOND, THIRD = (every("5m", name, id=name) for name in ("first", "second", "third"))


class Clock:
    """The crew's clock, which stands where a test puts it: at six on a Monday morning."""

    def __init__(self) -> None:
        self.at = at("06:00")

    def __call__(self) -> datetime:
        return self.at


class Shell:
    """Stands in for running a job's command: keeps each command with the minute it was
    asked for, and ends it well unless `fails`."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.ran: list[tuple[str, str]] = []
        self.fails = False
        # Called once, while the next command runs: what happens to a crew in mid-run.
        self.during: Callable[[], object] | None = None

    async def __call__(self, command: str, cwd: Any, timeout_s: float, **more: Any):
        self.ran.append((self.clock().strftime("%d %H:%M"), command))
        if self.during is not None:
            during, self.during = self.during, None
            during()
        return (3, "không vào được sổ\n") if self.fails else (0, "xong\n")


@dataclass
class House:
    client: TestClient
    runtime: Runtime
    clock: Clock
    shell: Shell
    home: Path

    def save(self, *rows: dict[str, Any]) -> None:
        """Saves the agent with these schedules and no other, as its editor does. No save
        asks for a restart."""
        reply = self.client.patch("/api/agents/coder", json={"profile": {"schedules": list(rows)}})
        assert reply.status_code == 200, reply.text
        assert reply.json()["restart_required"] == []

    async def tick(self, minute: str, day: str = MONDAY) -> list[str]:
        """Puts the clock at that minute and has it look: the commands that came due."""
        self.clock.at = at(minute, day)
        before = len(self.shell.ran)
        await self.runtime.scheduler.tick()
        return [command for _, command in self.shell.ran[before:]]

    def rows(self) -> dict[str, dict[str, Any]]:
        return {row["id"]: row for row in self.client.get("/api/jobs").json()}

    def next_run(self, job_id: str = JOB) -> str:
        return self.rows()[job_id]["next_run"][:16]

    def switch(self, enabled: bool, job_id: str = JOB) -> None:
        reply = self.client.patch(f"/api/jobs/{job_id}/state", json={"enabled": enabled})
        assert reply.status_code == 200, reply.text

    def switched(self, job_id: str = JOB) -> bool | None:
        """The switch the store holds for a job; None when nobody flipped one."""
        return self.runtime.store.jobs.enabled(job_id)


@pytest.fixture
def house(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A crew that runs, with an agent `coder` that has no schedule yet."""
    clock = Clock()
    shell = Shell(clock)
    monkeypatch.setattr(Settings, "now", lambda self: clock().replace(tzinfo=self.zone))
    monkeypatch.setattr(jobs, "run_shell", shell)
    home = tmp_path / "home"
    home.mkdir()
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env), env=env)
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        made = client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
        assert made.status_code == 201, made.text
        yield House(client, runtime, clock, shell, home)


# --- a row whose timing changed, and one whose timing did not ---


async def test_a_changed_cron_runs_at_its_new_time_and_for_no_time_that_passed(house) -> None:
    house.save(daily(7))
    assert await house.tick("07:00") == ["sync"]
    house.clock.at = at("09:00")

    house.save(daily(8))

    # The mark is of 07:00, and the new row's 08:00 lies between it and now.
    assert await house.tick("09:00") == []
    assert house.next_run() == f"{TUESDAY}T08:00"
    assert await house.tick("07:00", TUESDAY) == []
    assert await house.tick("08:00", TUESDAY) == ["sync"]


async def test_a_changed_interval_is_counted_from_the_save(house) -> None:
    house.save(every("1h"))
    house.clock.at = at("06:50")

    house.save(every("5m"))

    # Fifty minutes lie behind the mark, ten five-minute spans of them.
    assert await house.tick("06:50") == []
    assert house.next_run() == f"{MONDAY}T06:55"
    assert await house.tick("06:54") == []
    assert await house.tick("06:55") == ["sync"]


async def test_a_save_that_leaves_a_rows_timing_alone_does_not_put_its_run_off(house) -> None:
    """What the job does, what it is called, and anything else about its agent."""
    house.save(every("5m", name="Đồng bộ"))
    house.clock.at = at("06:04")

    renamed = house.client.patch("/api/agents/coder", json={"profile": {"name": "Thợ mã"}})
    house.save(every("5m", "sync --all", name="Đồng bộ hết"))

    assert renamed.status_code == 200 and renamed.json()["restart_required"] == []
    assert house.next_run() == f"{MONDAY}T06:05"
    assert await house.tick("06:05") == ["sync --all"]


async def test_a_row_its_file_switches_on_runs_for_no_time_that_passed_while_it_was_off(
    house,
) -> None:
    house.save(daily(7, enabled=False))
    assert await house.tick("07:00") == []
    house.clock.at = at("09:00")

    house.save(daily(7, enabled=True))

    assert await house.tick("09:00") == []
    assert await house.tick("07:00", TUESDAY) == ["sync"]


# --- a row that is new, and one taken out ---


async def test_a_new_row_runs_at_its_first_time_after_the_save_and_not_before(house) -> None:
    house.clock.at = at("09:00")

    house.save(every("5m"), {"id": "report", "cron": "0 8 * * *", "command": "report"})

    assert await house.tick("09:00") == []
    assert house.next_run() == f"{MONDAY}T09:05"
    assert await house.tick("09:04") == []
    assert await house.tick("09:05") == ["sync"]
    # Eight o'clock had passed that day when the row was written.
    assert house.next_run("coder/report") == f"{TUESDAY}T08:00"
    assert await house.tick("07:59", TUESDAY) == ["sync"]
    assert await house.tick("08:00", TUESDAY) == ["report"]


async def test_a_row_taken_out_of_the_file_never_runs_again(house) -> None:
    house.save(every("5m"), {"id": "stays", "every": "5m", "command": "stays"})
    assert await house.tick("06:05") == ["sync", "stays"]

    house.save({"id": "stays", "every": "5m", "command": "stays"})

    assert list(house.rows()) == ["coder/stays"]
    assert house.client.post(f"/api/jobs/{JOB}/run").status_code == 404
    assert await house.tick("06:10") == ["stays"]
    assert await house.tick("06:10", TUESDAY) == ["stays"]


async def test_a_row_taken_out_takes_its_switch_along_and_its_id_begins_anew(house) -> None:
    house.save(daily(7))
    assert await house.tick("07:00") == ["sync"]
    house.switch(False)

    house.save()
    left = house.switched()
    house.clock.at = at("09:00")
    house.save(daily(8))

    assert left is None
    row = house.rows()[JOB]
    assert (row["enabled"], row["paused"], row["failing"]) == (True, False, None)
    # The id left a mark of 07:00 behind, and 08:00 passed while no file stated the job.
    assert await house.tick("09:00") == []
    assert await house.tick("08:00", TUESDAY) == ["sync"]


async def test_a_switch_outlives_every_save_that_keeps_its_row(house) -> None:
    """A person paused the job, and nothing they saved since says otherwise."""
    house.save(daily(7))
    house.switch(False)

    house.save(daily(7, "sync --all"))
    edited = house.switched()
    house.save(daily(8))

    assert (edited, house.switched()) == (False, False)
    row = house.rows()[JOB]
    assert (row["enabled"], row["paused"]) == (False, True)
    assert await house.tick("08:00") == []


# --- a save that lands while the clock is at work ---


async def test_a_run_under_way_when_its_row_is_saved_ends_as_the_row_it_began_with(house) -> None:
    house.save(every("5m", name="Đồng bộ"))
    house.shell.during = lambda: house.save(daily(8, "sync --all", name="Chép hết"))
    house.clock.at = at("06:05")

    [run] = await house.runtime.scheduler.tick()

    assert run.status == DONE
    assert "Đồng bộ" in run.title and "Chép hết" not in run.title
    assert house.shell.ran == [("12 06:05", "sync")]
    assert house.rows()[JOB]["running"] is False
    # The row it left behind is the one on the clock: at its own time, with its own command.
    assert await house.tick("06:10") == []
    assert await house.tick("08:00") == ["sync --all"]


async def test_a_run_under_way_when_its_row_is_taken_out_ends_and_is_held_against_no_job(
    house,
) -> None:
    house.shell.fails = True
    house.save(every("5m"))
    house.shell.during = lambda: house.save()
    house.clock.at = at("06:05")

    [run] = await house.runtime.scheduler.tick()
    house.save(every("5m"))

    assert run.status == FAILED
    row = house.rows()[JOB]
    assert (row["running"], row["failing"]) == (False, None)


async def test_a_row_given_new_timing_while_an_earlier_job_of_the_tick_runs_waits_for_it(
    house,
) -> None:
    """Counted among the due as the row it was, and by the time its turn comes another."""
    house.save(FIRST, SECOND)
    house.shell.during = lambda: house.save(FIRST, {**SECOND, "every": "10m"})

    ran = await house.tick("06:05")

    assert ran == ["first"]
    assert house.next_run("coder/second") == f"{MONDAY}T06:15"
    assert await house.tick("06:10") == ["first"]
    assert await house.tick("06:15") == ["first", "second"]


async def test_a_row_taken_out_while_an_earlier_job_of_the_tick_runs_holds_up_no_other(
    house,
) -> None:
    house.save(FIRST, SECOND, THIRD)
    house.shell.during = lambda: house.save(FIRST, THIRD)

    ran = await house.tick("06:05")

    assert ran == ["first", "third"]
    assert list(house.rows()) == ["coder/first", "coder/third"]
    assert await house.tick("06:10") == ["first", "third"]


async def test_a_row_edited_while_an_earlier_job_of_the_tick_runs_runs_once_and_as_edited(
    house,
) -> None:
    house.save(FIRST, SECOND)
    house.shell.during = lambda: house.save(FIRST, {**SECOND, "command": "second --all"})

    ran = await house.tick("06:05") + await house.tick("06:05")

    assert ran == ["first", "second --all"]


def test_a_list_of_jobs_being_read_while_a_row_is_taken_out_is_still_answered(
    house, monkeypatch
) -> None:
    """The list is read on a thread of its own, row by row from the table it took at the
    start: a save in the middle may not take away what the rows still to come are read by."""
    house.save(FIRST, SECOND)
    hub = house.runtime.hub
    recent = hub.recent

    def then_a_row_goes(*args: Any, **kwargs: Any):
        monkeypatch.setattr(hub, "recent", recent)
        house.save(FIRST)
        return recent(*args, **kwargs)

    monkeypatch.setattr(hub, "recent", then_a_row_goes)

    read = house.runtime.scheduler.describe()

    assert [row["id"] for row in read] == ["coder/first", "coder/second"]
    assert list(house.rows()) == ["coder/first"]


# --- what was counted of a job's failures ---


async def test_a_row_taken_out_leaves_no_count_of_failures_to_one_made_under_its_id(house) -> None:
    house.shell.fails = True
    house.save(every("5m"))
    await house.tick("06:05")
    await house.tick("06:10")
    counted = house.rows()[JOB]["failing"]["count"]

    house.save()
    house.save(every("5m"))
    anew = house.rows()[JOB]["failing"]
    await house.tick("06:15")

    assert (counted, anew) == (2, None)
    failing = house.rows()[JOB]["failing"]
    assert (failing["count"], failing["since"][:16]) == (1, f"{MONDAY}T06:15")


async def test_a_save_that_keeps_a_row_keeps_what_was_counted_of_its_failures(house) -> None:
    """To the person who was told it fails, a job that was edited is the job it was: the
    next message goes on counting, and the one that says it ran well again is still owed."""
    house.shell.fails = True
    house.save(every("5m"))
    await house.tick("06:05")
    await house.tick("06:10")

    house.save(every("5m", "sync --all"))
    kept = house.rows()[JOB]["failing"]["count"]
    await house.tick("06:15")

    failing = house.rows()[JOB]["failing"]
    assert (kept, failing["count"], failing["since"][:16]) == (2, 3, f"{MONDAY}T06:05")


async def test_an_agent_that_leaves_takes_the_count_of_its_jobs_failures_along(house) -> None:
    house.shell.fails = True
    house.save(every("5m"))
    await house.tick("06:05")
    counted = house.rows()[JOB]["failing"]["count"]

    left = house.client.delete("/api/agents/coder")
    profile = {"schedules": [every("5m")]}
    made = house.client.post("/api/agents", json={"agent_id": "coder", "profile": profile})

    assert (left.status_code, made.status_code) == (200, 201)
    assert (counted, house.rows()[JOB]["failing"]) == (1, None)


# --- every way an agent's schedules come to the crew ---


async def test_an_agent_made_with_schedules_has_them_on_the_clock_at_once(house) -> None:
    house.clock.at = at("09:00")
    profile = {"schedules": [every("5m", "count")]}

    made = house.client.post("/api/agents", json={"agent_id": "helper", "profile": profile})

    assert made.status_code == 201, made.text
    assert made.json()["restart_required"] == []
    assert list(house.rows()) == ["helper/sync"]
    assert await house.tick("09:04") == []
    assert await house.tick("09:05") == ["count"]


@pytest.fixture
def timed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A template that brings a schedule. None of the bundled ones does."""
    bundled = tmp_path / "bundled"
    (bundled / "timed").mkdir(parents=True)
    (bundled / "timed" / "agent.yaml").write_text(BY_HAND, encoding="utf-8")
    (bundled / "_shared_skills").mkdir()
    monkeypatch.setattr(templates_cli, "TEMPLATES_DIR", bundled)
    return "timed"


async def test_an_installed_agent_has_its_schedules_on_the_clock_and_waits_for_no_restart(
    house, timed
) -> None:
    house.clock.at = at("09:00")

    reply = house.client.post("/api/agents/install", json={"template": timed})

    assert reply.status_code == 201, reply.text
    assert reply.json() == {"installed": ["timed"], "live": ["timed"], "needs_restart": False}
    assert list(house.rows()) == ["timed/sync"]
    assert await house.tick("09:04") == []
    assert await house.tick("09:05") == ["count"]


def test_an_install_written_over_an_agent_that_runs_still_waits_for_a_restart(house, timed) -> None:
    """The one that runs is not built again from the file put in place of its own, so the
    crew, and the clock with it, goes by the agent from before until the next start."""
    profile = {"name": "Của tôi"}
    made = house.client.post("/api/agents", json={"agent_id": "timed", "profile": profile})
    assert made.status_code == 201, made.text

    reply = house.client.post("/api/agents/install", json={"template": timed, "force": True})

    assert reply.status_code == 201, reply.text
    assert reply.json() == {"installed": ["timed"], "live": [], "needs_restart": True}
    assert house.rows() == {}


async def test_a_folder_copied_in_by_hand_is_on_the_clock_once_the_crew_is_read_again(
    house,
) -> None:
    folder = house.home / "agents" / "helper"
    folder.mkdir(parents=True)
    (folder / "agent.yaml").write_text(BY_HAND, encoding="utf-8")
    house.clock.at = at("09:00")

    reply = house.client.post("/api/agents/reload")

    assert (reply.status_code, reply.json()) == (200, {"added": ["helper"]})
    assert list(house.rows()) == ["helper/sync"]
    assert await house.tick("09:04") == []
    assert await house.tick("09:05") == ["count"]


@pytest.fixture
def environ():
    """A saved connection is written to the process environment, as it must be for the
    crew to see it; the test gets it back as it was, less what a developer's shell set."""
    saved = dict(os.environ)
    for known in KNOWN:
        os.environ.pop(known.name, None)
    yield
    os.environ.clear()
    os.environ.update(saved)


async def test_a_file_edited_by_hand_is_on_the_clock_once_a_connection_is_saved(
    house, environ
) -> None:
    """Saving a key builds every agent that runs again from its file, so that is when a
    schedule written there by hand joins the crew; the clock goes by the crew that runs."""
    (house.home / "agents" / "coder" / "agent.yaml").write_text(BY_HAND, encoding="utf-8")
    house.clock.at = at("09:00")

    reply = house.client.put("/api/credentials/GOODREADS_ID", json={"value": "abc"})

    assert reply.status_code == 200, reply.text
    assert reply.json()["restart_required"] is None
    assert list(house.rows()) == [JOB]
    assert await house.tick("09:04") == []
    assert await house.tick("09:05") == ["count"]


# --- the nightly rewrite of an agent's memory, which is a schedule as any other ---


def test_the_time_an_agents_memory_is_rewritten_at_follows_the_same_rules(house) -> None:
    def rewritten_at(cron: str | None) -> None:
        body = {"profile": {"memory_consolidate": cron}}
        reply = house.client.patch("/api/agents/coder", json=body)
        assert reply.status_code == 200, reply.text
        assert reply.json()["restart_required"] == []

    def due() -> list[str]:
        return [job.id for job in house.runtime.scheduler.due()]

    rewritten_at("0 7 * * *")
    house.clock.at = at("09:00")
    # Nobody looked at seven: the job is due, and its mark still that of the save.
    missed = due()

    rewritten_at("0 8 * * *")
    after = due()
    house.clock.at = at("08:00", TUESDAY)
    at_its_time = due()
    house.switch(False, MEMORY_JOB)
    rewritten_at(None)

    assert (missed, after, at_its_time) == ([MEMORY_JOB], [], [MEMORY_JOB])
    assert house.rows() == {}
    assert house.switched(MEMORY_JOB) is None
