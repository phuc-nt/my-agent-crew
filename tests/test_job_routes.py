"""A schedule's `routes`: the models a prompt job's turn runs on instead of the agent's
(`scheduler/jobs.py`), so a daily brief can run on a cheaper model while a chat with the
agent keeps its own. Read from the file as `check` is, and kept off the web form's table."""

from __future__ import annotations

from typing import Any

import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.agents.profile_yaml import parse_profile
from my_agent_crew.config_parse import Route
from my_agent_crew.scheduler import jobs
from my_agent_crew.store.runs import DONE

ECHO = (Route("fake", "echo"),)
BRIEF = "Tin sáng hôm nay"


def job(routes: tuple[Route, ...] = ()) -> jobs.Job:
    schedule = Schedule("brief", "Tin sáng", cron="0 7 * * *", prompt=BRIEF, routes=routes)
    return jobs.Job(id="default/brief", agent_id="default", schedule=schedule)


async def ran(deps, the_job: jobs.Job):
    run = await jobs.run_prompt(the_job, deps, ActivityHub(deps.store), "[lịch] Tin sáng")
    return run, deps.store.history(run.conversation_id)[-1]


async def test_a_job_that_states_routes_runs_its_turn_on_them(deps_factory):
    # The agent's own route is the scripted model with nothing scripted: a turn on it fails.
    deps = deps_factory()

    run, answer = await ran(deps, job(ECHO))

    assert run.status == DONE
    assert (answer.provider, answer.model, answer.message.content) == (
        "fake",
        "echo",
        f"(echo) {BRIEF}",
    )
    # The agent itself is left as it was, for every other turn it takes.
    assert [r.provider for r in deps.chain.routes] == ["scripted"]


async def test_a_job_that_states_none_runs_on_the_agents_routes(deps_factory):
    deps = deps_factory(routes=ECHO)

    run, answer = await ran(deps, job())

    assert run.status == DONE and (answer.provider, answer.model) == ("fake", "echo")


async def test_a_route_this_machine_has_no_key_for_is_passed_over(deps_factory):
    deps = deps_factory(routes=ECHO)

    stated = (Route("anthropic", "claude-haiku-5-5"), Route("fake", "slow"))
    assert jobs.on_job_routes(job(stated), deps).chain.routes == (Route("fake", "slow"),)
    # With none left, the job runs on the agent's routes rather than on nothing.
    alone = job((Route("anthropic", "claude-haiku-5-5"),))
    assert jobs.on_job_routes(alone, deps) is deps


def test_the_routes_think_as_hard_as_the_agents_own(deps_factory):
    deps = deps_factory(routes=(Route("fake", "echo", reasoning="low"),))

    [route] = jobs.on_job_routes(job((Route("fake", "slow"),)), deps).chain.routes

    assert route == Route("fake", "slow", reasoning="low")


# --- the key in the file and on the jobs list ---


def rows(**more: Any) -> dict[str, Any]:
    return {"schedules": [{"id": "brief", "cron": "0 7 * * *", "prompt": BRIEF, **more}]}


def test_the_key_is_read_from_the_file_and_shown_as_written(settings, tmp_path):
    stated = ["anthropic:claude-haiku-5-5", "openrouter:deepseek/deepseek-v4-flash"]
    [brief] = parse_profile("a", tmp_path, rows(routes=stated), settings).schedules
    [plain] = parse_profile("a", tmp_path, rows(), settings).schedules

    assert brief.routes == (
        Route("anthropic", "claude-haiku-5-5"),
        Route("openrouter", "deepseek/deepseek-v4-flash"),
    )
    assert brief.to_dict()["routes"] == stated
    # A row that states none shows none: what an editor reads and writes back is unchanged.
    assert plain.routes == () and "routes" not in plain.to_dict()


@pytest.mark.parametrize("value", [[], "", "anthropic:claude-haiku-5-5", ["haiku"], [7], {"a": 1}])
def test_routes_that_name_no_model_are_refused_when_the_file_is_read(settings, tmp_path, value):
    with pytest.raises(ValueError, match="agent a: schedule brief: "):
        parse_profile("a", tmp_path, rows(routes=value), settings)
