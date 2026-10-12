"""An agent that leaves the crew takes its jobs with it (`scheduler/runner.py`,
`server/runtime.py`).

The clock was given each agent's schedules once, at the start, and kept them whoever left.
A removed agent's job then came due with nobody to run it: the tick raised, and the jobs
after it in that tick waited for the next. Once an agent was made under the same id, the
job ran again, as that agent. So a removal takes the agent's jobs off the clock and out
of the store, and a job that comes due with no agent in the crew is told of in one line
and left out, whatever way its agent went.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.server.runtime_build import build_runtime
from my_agent_crew.store.created_schedules import CreatedScheduleRow


def stating(job_id: str) -> str:
    return f'schedules:\n  - id: {job_id}\n    cron: "* * * * *"\n    prompt: Làm việc {job_id}\n'


# One job each, due every minute; the agents stand in the order the clock goes through.
# The one that stays begins with the id of the one that goes, and names its job the same.
# The last is an agent of the crew's kit, whose markdown can state no schedule: the jobs
# it holds are the ones it is given in a conversation.
FILES = {
    "agent.yaml": stating("chao"),
    "agents/coder/agent.yaml": stating("nhac"),
    "agents/coder-two/agent.yaml": stating("nhac"),
    ".claude/agents/helper.md": "---\nname: helper\ndescription: Phụ việc\n---\nPhụ việc.\n",
}
OTHERS = ["job:default/chao", "job:coder-two/nhac"]
STAMP = "2026-10-12T00:00:00+00:00"


@pytest.fixture
def house(tmp_path: Path):
    home = tmp_path / "home"
    for name, text in FILES.items():
        (home / name).parent.mkdir(parents=True, exist_ok=True)
        (home / name).write_text(text, encoding="utf-8")
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env), env=env)
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, runtime


def made_in_chat(runtime: Runtime, agent_id: str) -> CreatedScheduleRow:
    """A job the agent was given in a conversation, which the store holds and no file."""
    fields = {
        "agent_id": agent_id,
        "name": "Nhắc uống nước",
        "cron": "* * * * *",
        "every": None,
        "prompt": "Nhắc uống nước",
        "skills": [],
        "created_by_conversation": "c1",
    }
    return runtime.store.created_schedules.add(fields, cap=20)


def on_the_clock(runtime: Runtime) -> list[str]:
    return [job.id for job in runtime.scheduler.jobs()]


def listed(client: TestClient) -> list[str]:
    return [job["id"] for job in client.get("/api/jobs").json()]


def later(runtime: Runtime, minutes: int) -> datetime:
    return runtime.settings.now() + timedelta(minutes=minutes)


def removed(client: TestClient, agent_id: str = "coder") -> None:
    assert client.delete(f"/api/agents/{agent_id}").status_code == 200


def leaving_mid_tick(monkeypatch, runtime: Runtime, leave: Callable[[], object]) -> None:
    """The agent goes while the tick's first job runs, when the clock has already counted
    the agent's own among the due."""
    run_job = runtime.scheduler.run_job

    async def then_the_agent_goes(job_id: str):
        run = await run_job(job_id)
        if job_id == "default/chao":
            leave()
        return run

    monkeypatch.setattr(runtime.scheduler, "run_job", then_the_agent_goes)


def test_removing_an_agent_takes_its_jobs_off_the_clock_at_once(house) -> None:
    client, runtime = house
    its, kept = made_in_chat(runtime, "coder"), made_in_chat(runtime, "coder-two")
    switched = ["coder/nhac", f"coder/{its.id}", "coder-two/nhac", f"coder-two/{kept.id}"]
    for job_id in switched:
        runtime.store.jobs.set_enabled(job_id, False, STAMP)
    before = on_the_clock(runtime)

    removed(client)

    assert before == [
        "default/chao",
        "coder/nhac",
        "coder-two/nhac",
        f"coder/{its.id}",
        f"coder-two/{kept.id}",
    ]
    assert on_the_clock(runtime) == ["default/chao", "coder-two/nhac", f"coder-two/{kept.id}"]
    assert listed(client) == on_the_clock(runtime)
    # What the store held of them goes too: the jobs made in chat, and every switch flipped
    # on a job of the agent's. Another agent's stay, whatever its id begins with.
    assert [row.id for row in runtime.store.created_schedules.all()] == [kept.id]
    assert {job_id: runtime.store.jobs.enabled(job_id) for job_id in switched} == {
        "coder/nhac": None,
        f"coder/{its.id}": None,
        "coder-two/nhac": False,
        f"coder-two/{kept.id}": False,
    }
    assert client.post("/api/jobs/coder/nhac/run").status_code == 404


def test_an_agent_takes_the_jobs_under_its_own_id_and_no_id_that_reads_like_it(house) -> None:
    """The id is text. To a pattern `_` stands for any letter and case counts for nothing,
    and a longer id begins with a shorter one."""
    _, runtime = house
    others = ["axb", "a_b-two", "A_B", "a_"]
    for agent_id in ["a_b", *others]:
        made_in_chat(runtime, agent_id)
        runtime.store.jobs.set_enabled(f"{agent_id}/nhac", False, STAMP)

    runtime.scheduler.forget_agent("a_b")

    assert [row.agent_id for row in runtime.store.created_schedules.all()] == others
    assert runtime.store.jobs.enabled("a_b/nhac") is None
    assert [runtime.store.jobs.enabled(f"{agent_id}/nhac") for agent_id in others] == [False] * 4


async def test_a_due_job_whose_agent_is_not_in_the_crew_is_skipped_and_holds_up_no_other(
    house, caplog
) -> None:
    """Gone by a way that took no job along, which is what the clock may not count on. The
    job stands before another agent's in the tick, so a tick it ended would show."""
    _, runtime = house
    runtime.agents.pop("coder")

    with caplog.at_level(logging.WARNING, logger="my_agent_crew.scheduler.runner"):
        first = await runtime.scheduler.tick(later(runtime, 2))
        second = await runtime.scheduler.tick(later(runtime, 4))

    assert [run.source for run in first] == OTHERS
    assert [run.source for run in second] == OTHERS
    told = [record.getMessage() for record in caplog.records]
    assert len(told) == 1 and "coder/nhac" in told[0]
    assert on_the_clock(runtime) == ["default/chao", "coder-two/nhac"]


async def test_an_agent_removed_while_an_earlier_job_of_the_tick_runs_holds_up_no_other(
    house, monkeypatch
) -> None:
    client, runtime = house
    made_in_chat(runtime, "coder")
    leaving_mid_tick(monkeypatch, runtime, lambda: removed(client))

    runs = await runtime.scheduler.tick(later(runtime, 2))

    assert [run.source for run in runs] == OTHERS


async def test_a_kit_agent_gone_while_an_earlier_job_of_the_tick_runs_holds_up_no_other(
    house, monkeypatch, caplog
) -> None:
    """A job made in a conversation is shown by the store for as long as its agent is in
    the crew, so the one way it comes due with no agent is this: counted, then left."""
    _, runtime = house
    its, after = made_in_chat(runtime, "helper"), made_in_chat(runtime, "coder-two")
    leaving_mid_tick(monkeypatch, runtime, lambda: runtime.agents.pop("helper", None))

    with caplog.at_level(logging.WARNING, logger="my_agent_crew.scheduler.runner"):
        first = await runtime.scheduler.tick(later(runtime, 2))
        second = await runtime.scheduler.tick(later(runtime, 4))

    assert [run.source for run in first] == ["job:default/chao", "job:coder/nhac", *OTHERS[1:]] + [
        f"job:coder-two/{after.id}"
    ]
    assert [run.source for run in second] == [run.source for run in first]
    told = [record.getMessage() for record in caplog.records]
    assert len(told) == 1 and f"helper/{its.id}" in told[0]


def test_a_kit_agent_is_not_removed_over_the_api_and_keeps_its_jobs(house) -> None:
    """The one way out of a running crew is the removal of an agent a folder describes. An
    agent a kit's markdown describes is refused it, so nothing of its may go either."""
    client, runtime = house
    its = made_in_chat(runtime, "helper")
    runtime.store.jobs.set_enabled(f"helper/{its.id}", False, STAMP)

    reply = client.delete("/api/agents/helper")

    assert reply.status_code == 409
    assert f"helper/{its.id}" in on_the_clock(runtime)
    assert runtime.store.jobs.enabled(f"helper/{its.id}") is False


def test_a_reload_leaves_no_job_on_the_clock_whose_agent_is_not_in_the_crew(house) -> None:
    """A reload brings agents in and takes none out, a folder gone from the home or not.
    Held by what must stay true should it ever take one out: its jobs go the same way."""
    client, runtime = house
    made_in_chat(runtime, "coder")
    shutil.rmtree(runtime.settings.home / "agents" / "coder")

    assert client.post("/api/agents/reload").status_code == 200

    assert {job.agent_id for job in runtime.scheduler.jobs()} <= set(runtime.agents)
    assert {job["agent_id"] for job in client.get("/api/jobs").json()} <= set(runtime.agents)


async def test_a_run_whose_agent_is_gone_is_told_to_nobody_and_raises_nothing(house) -> None:
    """A job's turn that waited on the person is pushed to the chat when it ends, which
    may be after its agent left."""
    _, runtime = house
    job = runtime.scheduler.get("coder/nhac")
    run = await runtime.scheduler.run_job(job.id)
    runtime.agents.pop("coder")

    await runtime.scheduler.deliver_run(job, run)

    assert run.conversation_id


async def test_an_agent_made_under_a_removed_agents_id_is_given_none_of_its_jobs(house) -> None:
    client, runtime = house
    its = made_in_chat(runtime, "coder")
    runtime.store.jobs.set_enabled(f"coder/{its.id}", False, STAMP)

    removed(client)
    again = client.post("/api/agents", json={"agent_id": "coder", "profile": {"name": "Mới"}})
    runs = await runtime.scheduler.tick(later(runtime, 2))

    assert again.status_code == 201
    assert on_the_clock(runtime) == listed(client) == ["default/chao", "coder-two/nhac"]
    assert [run.source for run in runs] == OTHERS
    assert {run.agent_id for run in runs} == {"default", "coder-two"}
    assert runtime.store.created_schedules.all() == []
    assert runtime.store.jobs.enabled(f"coder/{its.id}") is None
