"""Each job of an agent goes by an id of its own (`agents/schedule.py`, read through
`agents/profile_yaml.py`).

A job is known by its id on the clock, in the switch a person flips on it and in what a
script job keeps. A file a person wrote with two rows on one id used to start, and the
later row took the earlier one's place without a word. Such a file now stops the start,
and the refusal names the agent and the id. A save from the web meets the same reading of
the file, so it is refused in the same words.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew import texts
from my_agent_crew.config import load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.server.runtime_build import build_runtime

CONSOLIDATING = 'memory_consolidate: "0 3 * * *"\n'


def rows(*ids: object) -> str:
    """A `schedules:` list of one row an id, as a person writes it. None is a row that
    writes no id, and goes by its place in the list."""
    out = "schedules:\n"
    for place, job_id in enumerate(ids):
        named = "" if job_id is None else f"id: {job_id}\n    "
        out += f'  - {named}cron: "0 {place} * * *"\n    prompt: Việc thứ {place}\n'
    return out


# The file, and the id two of its jobs go by. An id is the one written, read as text, or
# the row's place when none is written (and a zero is none); the consolidation job has
# one too.
PAIRS = {
    "written twice": (rows("sang", "toi", "toi"), "toi"),
    "written twice with a row between": (rows("toi", "sang", "toi"), "toi"),
    "a row's place, written on the row before it": (rows("job-1", None), "job-1"),
    "a row's place, written on the row after it": (rows(None, "job-0"), "job-0"),
    "a number and the text of it": (rows(7, '"7"'), "7"),
    "a zero, which is the row's place": (rows("job-1", 0), "job-1"),
    "the consolidation job's": (rows("memory-consolidate") + CONSOLIDATING, "memory-consolidate"),
}
# Files that started before and start now, and the ids their jobs go by.
APART = {
    "written": (rows("sang", "toi"), ["sang", "toi"]),
    "each by its place": (rows(None, None), ["job-0", "job-1"]),
    "a written id that is no row's place": (
        rows("job-9", None, "sang"),
        ["job-9", "job-1", "sang"],
    ),
    "beside the consolidation job": (rows("sang") + CONSOLIDATING, ["sang", "memory-consolidate"]),
    "the consolidation job alone": (CONSOLIDATING, ["memory-consolidate"]),
    "named as the consolidation job, which is off": (
        rows("memory-consolidate"),
        ["memory-consolidate"],
    ),
    "ids apart by a capital": (rows("Sang", "sang"), ["Sang", "sang"]),
}


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


def write(home: Path, agent_id: str, text: str) -> Path:
    """The agent's file as a person leaves it; the master's is the home's own."""
    folder = home if agent_id == "default" else home / "agents" / agent_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "agent.yaml").write_text(text, encoding="utf-8")
    return folder / "agent.yaml"


def start(home: Path) -> Runtime:
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    return build_runtime(load_settings(env=env), env=env)


def told(agent_id: str, job_id: str) -> str:
    return texts.SCHEDULE_ID_TAKEN.format(agent_id=agent_id, id=job_id)


@pytest.mark.parametrize("whose", ["default", "coder"])
@pytest.mark.parametrize("pair", PAIRS)
def test_two_jobs_on_one_id_stop_the_start_and_the_refusal_names_the_id(
    home: Path, pair: str, whose: str
) -> None:
    written, job_id = PAIRS[pair]
    write(home, whose, written)

    with pytest.raises(ValueError) as refused:
        start(home)

    assert str(refused.value) == told(whose, job_id)
    assert whose in str(refused.value) and job_id in str(refused.value)


@pytest.mark.parametrize("whose", ["default", "coder"])
@pytest.mark.parametrize("each", APART)
def test_jobs_each_on_an_id_of_its_own_start_as_before(home: Path, each: str, whose: str) -> None:
    written, ids = APART[each]
    write(home, whose, written)

    runtime = start(home)

    assert [schedule.id for schedule in runtime.deps_for(whose).agent.schedules] == ids
    assert [job.id for job in runtime.scheduler.jobs()] == [f"{whose}/{job_id}" for job_id in ids]


def test_two_agents_may_each_have_a_job_of_one_id_and_neither_hides_the_other(home: Path) -> None:
    """The clock knows a job by its agent and its id together."""
    for agent_id in ("default", "coder", "coder-two"):
        write(
            home, agent_id, f'schedules:\n  - id: nhac\n    every: 1h\n    prompt: "{agent_id}"\n'
        )

    runtime = start(home)

    assert {job.id: job.schedule.prompt for job in runtime.scheduler.jobs()} == {
        "default/nhac": "default",
        "coder/nhac": "coder",
        "coder-two/nhac": "coder-two",
    }


def test_a_save_over_a_file_that_came_to_hold_such_a_pair_is_refused_in_the_starts_words(
    home: Path,
) -> None:
    """The file was changed by hand while the server ran. The save names no schedule, and
    is still a reading of the whole file: it is answered as the next start would answer."""
    manifest = write(home, "coder", "name: Thợ mã\n")
    runtime = start(home)
    by_hand = "name: Thợ mã\n" + rows("toi", "toi")

    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        manifest.write_text(by_hand, encoding="utf-8")
        saved = client.patch("/api/agents/coder", json={"profile": {"description": "Viết mã"}})
        read_again = client.post("/api/agents/reload")
        shown = client.get("/api/agents/coder")

    with pytest.raises(ValueError) as refused:
        start(home)
    assert (saved.status_code, saved.json()["detail"]) == (422, str(refused.value))
    assert (read_again.status_code, read_again.json()["detail"]) == (422, told("coder", "toi"))
    assert shown.status_code == 200
    assert manifest.read_text("utf-8") == by_hand
    assert runtime.deps_for("coder").agent.schedules == ()
    assert runtime.deps_for("coder").agent.description == ""


@pytest.mark.parametrize("pair", ["written twice", "a row's place, written on the row before it"])
def test_an_edit_that_brings_two_jobs_on_one_id_is_refused_in_the_starts_words(
    home: Path, pair: str
) -> None:
    written, job_id = PAIRS[pair]
    manifest = write(home, "coder", "name: Thợ mã\n")
    runtime = start(home)
    brought = [
        {"id": row_id, "cron": f"0 {place} * * *", "prompt": f"Việc thứ {place}"}
        for place, row_id in enumerate(["sang", "toi", "toi"])
    ]
    if job_id == "job-1":
        brought = [{**brought[0], "id": "job-1"}, {"cron": "0 1 * * *", "prompt": "Việc thứ 1"}]

    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        edited = client.patch("/api/agents/coder", json={"profile": {"schedules": brought}})
        made = client.post(
            "/api/agents", json={"agent_id": "moi", "profile": {"schedules": brought}}
        )

    assert (edited.status_code, edited.json()["detail"]) == (422, told("coder", job_id))
    assert (made.status_code, made.json()["detail"]) == (422, told("moi", job_id))
    assert manifest.read_text("utf-8") == "name: Thợ mã\n"
    assert not (home / "agents" / "moi" / "agent.yaml").exists()
    assert sorted(runtime.agents) == ["coder", "default"]
