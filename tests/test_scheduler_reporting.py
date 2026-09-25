"""What a scheduled job tells the person, and what the Jobs page tells about a job.

A deadline check that found nothing answered "OK", and that "OK" landed in the chat every
morning. The Jobs page showed "never ran" for a weekly job whose last run had simply
fallen behind the two hundred newest runs of a busy crew."""

from __future__ import annotations

import logging

import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.llm.fake import completion
from my_agent_crew.scheduler import Scheduler
from my_agent_crew.store.runs import DONE
from tests.test_scheduler import with_schedules


def _check_job(deps_factory, *replies: str):
    deps = with_schedules(
        deps_factory(script=[completion(r) for r in replies]),
        Schedule("deadline-check", "Nhắc hạn", cron="30 7 * * *", prompt="Có hạn nào không?"),
    )
    delivered: list[str] = []

    async def deliver(agent_id: str, conv_id: str) -> bool:
        delivered.append(conv_id)
        return True

    return Scheduler({"default": deps}, ActivityHub(deps.store), deliver=deliver), delivered


@pytest.mark.parametrize("reply", ["OK", " ok. ", "OK!"])
async def test_a_job_with_nothing_to_report_is_not_pushed(deps_factory, caplog, reply: str):
    sched, delivered = _check_job(deps_factory, reply)
    with caplog.at_level(logging.INFO, logger="my_agent_crew.scheduler.runner"):
        run = await sched.run_job("default/deadline-check")

    assert run.status == DONE and delivered == []
    assert "job default/deadline-check: nothing to report, not delivered" in caplog.text
    # The run itself still shows, so the person can see the check did happen.
    assert sched.describe()[0]["last_run"]["id"] == run.id


async def test_a_reply_that_says_more_than_ok_is_pushed(deps_factory):
    sched, delivered = _check_job(deps_factory, "OK, nhưng HP3-12 còn 14 ngày tới hạn.")
    run = await sched.run_job("default/deadline-check")

    assert delivered == [run.conversation_id]


async def test_a_weekly_jobs_last_run_is_found_behind_a_busy_week(deps_factory):
    deps = with_schedules(
        deps_factory(script=[completion("Tổng kết tuần.")]),
        Schedule("weekly-review", "Tổng kết tuần", cron="0 8 * * 0", prompt="Tổng kết tuần"),
    )
    hub = ActivityHub(deps.store)
    sched = Scheduler({"default": deps}, hub)
    weekly = await sched.run_job("default/weekly-review")
    for n in range(210):
        hub.finish(hub.start("default", "chat", f"chat {n}", None), status=DONE, summary="")

    assert sched.describe()[0]["last_run"]["id"] == weekly.id
