"""Cron parsing and the scheduler: due detection, prompt, command and consolidate jobs."""

import os
from datetime import datetime

import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.turn_context import JOB
from my_agent_crew.agents.profile import (
    AgentProfile,
    Schedule,
    consolidate_schedule,
    default_profile,
)
from my_agent_crew.agents.profile_yaml import load_profiles
from my_agent_crew.config import Route
from my_agent_crew.llm.fake import completion
from my_agent_crew.memory import agent_store, user_store
from my_agent_crew.memory.consolidate import JOB_SOURCE as CONSOLIDATE_SOURCE
from my_agent_crew.scheduler import CronSpec, Scheduler, due_between, next_run, parse_every
from my_agent_crew.store.memory_proposals import AGENT_MEMORY_REWRITE
from my_agent_crew.store.runs import DONE, FAILED
from my_agent_crew.tools.memory_user import build_user_memory_tools


def test_cron_fields_lists_ranges_steps_and_sunday_alias():
    spec = CronSpec.parse("*/15 7,9 1-3 * 0")
    assert spec.minutes == {0, 15, 30, 45} and spec.hours == {7, 9}
    assert spec.days == {1, 2, 3} and spec.weekdays == {0}
    assert spec.matches(datetime(2026, 2, 1, 7, 30))  # a Sunday
    assert not spec.matches(datetime(2026, 2, 2, 7, 30))
    assert CronSpec.parse("0 0 * * 7").weekdays == {0}


@pytest.mark.parametrize("expr", ["* * * *", "60 * * * *", "* 24 * * *", "* * 0 * *", "a b c d e"])
def test_cron_rejects_bad_fields(expr):
    with pytest.raises(ValueError):
        CronSpec.parse(expr)


def test_next_after_skips_to_the_next_match():
    spec = CronSpec.parse("0 7 * * *")
    assert spec.next_after(datetime(2026, 9, 19, 7, 0, 30)) == datetime(2026, 9, 20, 7, 0)
    assert spec.next_after(datetime(2026, 9, 19, 6, 59)) == datetime(2026, 9, 19, 7, 0)


def test_every_parses_units_and_rejects_short_intervals():
    assert parse_every("30m") == 1800 and parse_every("2h") == 7200 and parse_every("1d") == 86400
    for bad in ("30", "5s", "2 weeks"):
        with pytest.raises(ValueError):
            parse_every(bad)


def test_due_between_and_next_run():
    last, now = datetime(2026, 9, 19, 6, 50), datetime(2026, 9, 19, 7, 0, 10)
    assert due_between("0 7 * * *", None, last, now)
    assert not due_between("0 7 * * *", None, last, datetime(2026, 9, 19, 6, 59))
    assert due_between(None, "10m", last, now) and not due_between(None, "11m", last, now)
    assert next_run(None, "10m", last, now) == datetime(2026, 9, 19, 7, 0)
    assert next_run("0 7 * * *", None, last, now) == datetime(2026, 9, 20, 7, 0)


def with_schedules(deps, *schedules: Schedule):
    profile: AgentProfile = deps.agent
    deps.profile = AgentProfile(**{**profile.__dict__, "schedules": tuple(schedules)})
    return deps


async def test_prompt_job_opens_autonomous_conversation_and_records_run(deps_factory):
    deps = with_schedules(
        deps_factory(routes=(Route("fake", "echo"),)),
        Schedule(
            "brief",
            "Bản tin sáng",
            cron="0 7 * * *",
            prompt='/tool shell_run {"command": "echo brief"}',
        ),
    )
    clock = [datetime(2026, 9, 19, 6, 59)]
    sched = Scheduler({"default": deps}, ActivityHub(deps.store), clock=lambda: clock[0])
    assert sched.due() == []
    clock[0] = datetime(2026, 9, 19, 7, 0, 5)
    [run] = await sched.tick()
    assert run.status == DONE and run.source == "job:default/brief"
    [conv] = deps.store.list()
    assert conv.autonomous and conv.title.startswith("[lịch] Bản tin sáng · 2026-09-19 07:00")
    assert run.conversation_id == conv.id and [s["kind"] for s in run.steps][:2] == [
        "model",
        "tool",
    ]
    assert await sched.tick() == []  # not due again until tomorrow
    [described] = sched.describe()
    assert described["last_run"]["id"] == run.id and described["next_run"] == "2026-09-20T07:00"


async def test_a_schedule_attaches_its_skills_to_the_conversation_it_opens(settings, store):
    from tests.conftest import make_deps

    skills_dir = settings.home / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "weekly.md").write_text(
        "---\nname: weekly\ndescription: Tổng kết tuần\n---\nĐọc kệ sách rồi tóm tắt.\n"
    )
    deps = with_schedules(
        make_deps(settings, store, script=[completion("xong")]),
        Schedule(
            "review", "Tổng kết", cron="0 8 * * 1", prompt="Tổng kết tuần", skills=("weekly",)
        ),
    )
    sched = Scheduler({"default": deps}, ActivityHub(store), clock=lambda: datetime(2026, 9, 21, 8))
    run = await sched.run_job("default/review")

    conv = store.get(run.conversation_id)
    assert conv.skills == ("weekly",)
    [request] = deps.chain.providers["scripted"].requests
    system = request.messages[0].content
    assert "Đọc kệ sách rồi tóm tắt." in system
    assert "## Kỹ năng có sẵn" not in system  # the only skill is attached in full


async def test_command_job_runs_shell_without_a_model(deps_factory):
    deps = with_schedules(
        deps_factory(),
        Schedule("sync", "Đồng bộ", every="1h", command="echo synced; exit 0"),
        Schedule("bad", "Hỏng", every="1h", command="exit 2", enabled=False),
    )
    hub = ActivityHub(deps.store)
    sched = Scheduler({"default": deps}, hub, clock=lambda: datetime(2026, 9, 19, 8, 0))
    run = await sched.run_job("default/sync")
    assert run.status == DONE and run.summary == "synced" and run.conversation_id is None
    assert run.steps[0]["name"] == "shell_run" and run.steps[0]["ok"] is True
    failed = await sched.run_job("default/bad")
    assert failed.status == FAILED and run.spent_usd == 0
    assert [j["running"] for j in sched.describe()] == [False, False]
    assert deps.chain.providers["scripted"].requests == []
    with pytest.raises(KeyError):
        await sched.run_job("default/nope")


def test_disabled_jobs_are_listed_but_never_due(settings, store):
    from tests.conftest import make_deps

    deps = with_schedules(
        make_deps(settings, store), Schedule("x", "x", every="1m", prompt="p", enabled=False)
    )
    sched = Scheduler({"default": deps}, ActivityHub(store), clock=lambda: datetime(2026, 1, 1))
    assert [j.id for j in sched.jobs()] == ["default/x"]
    assert sched.due(datetime(2026, 1, 2)) == []
    assert default_profile(settings).schedules == ()


async def test_prompt_job_result_is_delivered_and_a_failing_delivery_keeps_the_run(deps_factory):
    deps = with_schedules(
        deps_factory(routes=(Route("fake", "echo"),)),
        Schedule("brief", "Bản tin", every="10m", prompt="chào"),
    )
    delivered: list[tuple[str, str]] = []

    async def deliver(agent_id: str, conv_id: str) -> None:
        delivered.append((agent_id, conv_id))
        if len(delivered) > 1:
            raise RuntimeError("telegram down")

    sched = Scheduler({"default": deps}, ActivityHub(deps.store), deliver=deliver)
    first = await sched.run_job("default/brief")
    second = await sched.run_job("default/brief")
    assert first.status == DONE and second.status == DONE
    assert delivered == [("default", first.conversation_id), ("default", second.conversation_id)]


async def test_a_job_turn_only_proposes_what_it_wants_to_remember(deps_factory, settings, store):
    """End to end: nobody is watching a scheduled run, so a memory write waits for review."""
    user_dir = settings.user_dir
    tools = build_user_memory_tools(user_dir, store, "default")
    deps = deps_factory(routes=(Route("fake", "echo"),), extra_tools=tools)
    args = '{"name": "ngu-som", "description": "Ngủ sớm", "type": "preference", "body": "23h"}'
    deps = with_schedules(
        deps,
        Schedule("brief", "Bản tin", cron="0 7 * * *", prompt=f"/tool user_memory_save {args}"),
    )
    sched = Scheduler(
        {"default": deps}, ActivityHub(deps.store), clock=lambda: datetime(2026, 9, 19, 7, 0)
    )
    run = await sched.run_job("default/brief")

    assert run.status == DONE
    assert user_store.list_facts(user_dir) == []
    (proposal,) = deps.store.proposals.list()
    assert proposal.name == "ngu-som" and proposal.source == JOB


async def test_a_consolidate_job_rewrites_memory_without_opening_a_conversation(deps_factory):
    """The rewrite is a job like any other, but it answers nobody, so no thread is made."""
    deps = deps_factory(script=[completion("- Sếp thích trà.")])
    agent_store.write_memory_md(deps.agent.memory_file, "- Sếp thích trà buổi sáng.")
    agent_store.write_note(deps.agent.memory_dir, "2026-09-19", "Sếp uống trà.")
    stamp = deps.agent.memory_file.stat().st_mtime + 10
    os.utime(deps.agent.memory_dir / "2026-09-19.md", (stamp, stamp))
    deps = with_schedules(deps, consolidate_schedule("0 3 * * *"))

    delivered: list[str] = []

    async def deliver(agent_id: str, conv_id: str) -> None:
        delivered.append(agent_id)

    sched = Scheduler(
        {"default": deps},
        ActivityHub(deps.store),
        clock=lambda: datetime(2026, 9, 19, 3, 0),
        deliver=deliver,
    )
    job = sched.describe()[0]
    assert job["kind"] == "consolidate" and job["id"] == "default/memory-consolidate"

    run = await sched.run_job("default/memory-consolidate")
    assert run.status == DONE and run.conversation_id is None
    assert run.source == CONSOLIDATE_SOURCE
    assert delivered == []  # nothing to deliver: a rewrite is not an answer
    (proposal,) = deps.store.proposals.list()
    assert proposal.kind == AGENT_MEMORY_REWRITE


def test_a_consolidate_cron_in_the_profile_becomes_an_ordinary_job(settings, tmp_path):
    home = settings.home / "agents" / "coach"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text(
        "name: HLV\nmemory_consolidate: '0 3 * * *'\n", encoding="utf-8"
    )
    (coach,) = [p for p in load_profiles(settings) if p.id == "coach"]

    assert coach.memory_consolidate == "0 3 * * *"
    (schedule,) = coach.schedules
    assert schedule.consolidate and schedule.cron == "0 3 * * *"
    assert schedule.kind == "consolidate" and schedule.id == "memory-consolidate"
    assert coach.to_dict()["memory_consolidate"] == "0 3 * * *"


def test_a_profile_without_the_key_has_no_consolidate_job(settings):
    home = settings.home / "agents" / "pong"
    home.mkdir(parents=True)
    (home / "agent.yaml").write_text("name: Pong\n", encoding="utf-8")
    (pong,) = [p for p in load_profiles(settings) if p.id == "pong"]
    assert pong.schedules == () and pong.memory_consolidate == ""
