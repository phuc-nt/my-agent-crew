"""What the Jobs page tells about a job.

The Jobs page showed "never ran" for a weekly job whose last run had simply fallen behind
the two hundred newest runs of a busy crew. What a job tells the person is read on the web's
inbox (`test_webpush_notices.py`), and never in the chat (`test_jobs_tell_no_chat.py`)."""

from __future__ import annotations

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.llm.fake import completion
from my_agent_crew.scheduler import Scheduler
from my_agent_crew.store.runs import DONE
from tests.test_scheduler import with_schedules


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
