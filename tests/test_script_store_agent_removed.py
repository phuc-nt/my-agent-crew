"""What an agent's scripts kept goes with the agent, and nothing comes back under its id
(`store/script_store.py`, `script/store_session.py`, `server/routes_agents_edit.py`).

Removing an agent stops none of what it is doing. A script of its that is running then, or a
later one of a turn that outlives it, ends well and would write what it stored: rows under
the id of an agent that is gone, which an agent later given the id would read as its own.
So nothing put together for an agent before it was removed writes there again. The script
is told that none of it was kept, as a script that failed.

Each script here waits at a tool that answers when the test lets it, so the removal falls
where the test puts it: after the script stored, before it ended.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.script.store_session import Kept, job_kept
from my_agent_crew.script.tool import run_source
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store.script_store import ScriptStore
from my_agent_crew.texts_script_store import STORE_AGENT_GONE
from my_agent_crew.tools.result import ToolResult
from tests.test_api_script_store import ROOM, serving, shown
from tests.test_script_gate import played, ran
from tests.test_script_store import Waits
from tests.test_script_tool import unfinished

STORES_THEN_WAITS = """
store("seen", [1, 2])
tools.hung_read()
print("xong")
"""
LOST = unfinished("xong", STORE_AGENT_GONE)


@pytest.fixture
def house(tmp_path: Path):
    with serving(tmp_path) as served:
        yield served


def made(client: TestClient, agent_id: str = "coder") -> None:
    created = client.post("/api/agents", json={"agent_id": agent_id, "profile": {}})
    assert created.status_code == 201


def removed(client: TestClient, agent_id: str = "coder") -> None:
    assert client.delete(f"/api/agents/{agent_id}").status_code == 200


def rows(runtime: Runtime, agent: str = "coder") -> list[tuple[str, str, str]]:
    kept = runtime.store.script_store.kept_by(agent)
    return [(row.namespace, row.key, row.text) for row in kept]


def waiting(runtime: Runtime, agent_id: str = "coder") -> tuple[AgentDeps, Waits]:
    """The agent as the crew runs it, holding one more tool: a read that waits."""
    deps, waits = runtime.deps_for(agent_id), Waits()
    deps.tools.register(waits.tool)
    return deps, waits


async def in_a_turn(deps: AgentDeps, runtime: Runtime) -> ToolResult:
    """The script as a call of a turn of the agent's, which keeps under its conversation."""
    conv = runtime.store.create(agent_id=deps.agent.id)
    result, _ = await played(deps, conv.id, STORES_THEN_WAITS)
    return result


async def of_a_schedule(deps: AgentDeps, runtime: Runtime) -> ToolResult:
    """The script as a schedule's job runs it (`scheduler/script_job.py`), which keeps under
    the schedule's id."""
    return (await run_source(STORES_THEN_WAITS, deps.tools, kept=job_kept(deps, "due"))).result


BEGUN = pytest.mark.parametrize("begun", [in_a_turn, of_a_schedule])


@BEGUN
async def test_a_script_that_ends_well_keeps_what_it_stored(house, begun):
    """What every case below takes away: the same script, with nobody removed."""
    client, runtime = house
    made(client)
    deps, waits = waiting(runtime)
    waits.go.set()

    result = await begun(deps, runtime)

    assert (result.ok, result.output) == (True, "xong")
    assert [(key, text) for _, key, text in rows(runtime)] == [("seen", "[1,2]")]


@BEGUN
async def test_a_script_running_when_its_agent_is_removed_keeps_nothing(house, begun):
    client, runtime = house
    made(client)
    deps, waits = waiting(runtime)
    script = asyncio.create_task(begun(deps, runtime))
    await waits.entered.wait()

    removed(client)
    waits.go.set()
    result = await script

    assert rows(runtime) == []
    # It is told so, as a script that failed: it ran to its end and none of it is kept.
    assert (result.ok, result.output) == (False, LOST)


@BEGUN
async def test_an_agent_given_the_id_meanwhile_gets_nothing_of_the_script_still_running(
    house, begun
):
    client, runtime = house
    made(client)
    deps, waits = waiting(runtime)
    script = asyncio.create_task(begun(deps, runtime))
    await waits.entered.wait()

    removed(client)
    made(client)
    assert shown(client, "coder") == []
    waits.go.set()
    result = await script

    assert (result.ok, result.output) == (False, LOST)
    assert rows(runtime) == [] and shown(client, "coder") == []
    # The agent that has the id now is another agent, and keeps as any agent does.
    after = runtime.deps_for("coder")
    assert after is not deps
    conv = runtime.store.create(agent_id="coder")
    assert (await ran(after, conv, 'store("n", 1)')).ok
    assert rows(runtime) == [(f"conv:{conv.id}", "n", "1")]


async def test_a_turn_that_outlives_its_agent_keeps_nothing_by_a_later_script_either(house):
    """The turn goes on with the agent it began with. A script of it that begins after the
    removal would write under the id as well as one that was running then."""
    client, runtime = house
    made(client)
    deps = runtime.deps_for("coder")
    conv = runtime.store.create(agent_id="coder")

    removed(client)
    result = await ran(deps, conv, 'store("n", 1)\nprint("xong")')

    assert (result.ok, result.output) == (False, LOST)
    assert rows(runtime) == []
    # And with the id taken again: what the turn holds is still the agent that went.
    made(client)
    again = await ran(deps, conv, 'store("n", 1)\nprint("xong")')
    assert (again.ok, again.output) == (False, LOST)
    assert rows(runtime) == []


async def test_a_script_that_stored_nothing_ends_as_well_as_ever_beside_a_removal(house):
    client, runtime = house
    made(client)
    deps, waits = waiting(runtime)
    conv = runtime.store.create(agent_id="coder")
    script = asyncio.create_task(played(deps, conv.id, 'tools.hung_read()\nprint("xong")'))
    await waits.entered.wait()

    removed(client)
    waits.go.set()
    result, _ = await script

    assert (result.ok, result.output) == (True, "xong")


@BEGUN
async def test_removing_one_agent_takes_nothing_from_a_script_of_another(house, begun):
    client, runtime = house
    made(client)
    deps, waits = waiting(runtime, "coach")
    script = asyncio.create_task(begun(deps, runtime))
    await waits.entered.wait()

    removed(client)
    waits.go.set()
    result = await script

    assert (result.ok, result.output) == (True, "xong")
    assert [(key, text) for _, key, text in rows(runtime, "coach")] == [("seen", "[1,2]")]


@BEGUN
async def test_a_save_of_the_agent_takes_nothing_from_a_script_it_is_running(house, begun):
    """A save puts the agent together again, and is no removal: the agent is who it was."""
    client, runtime = house
    made(client)
    deps, waits = waiting(runtime)
    script = asyncio.create_task(begun(deps, runtime))
    await waits.entered.wait()

    saved = client.patch("/api/agents/coder", json={"profile": {"description": "Viết mã"}})
    assert saved.status_code == 200 and runtime.deps_for("coder") is not deps
    waits.go.set()
    result = await script

    assert (result.ok, result.output) == (True, "xong")
    assert [(key, text) for _, key, text in rows(runtime)] == [("seen", "[1,2]")]


# --- the table itself ---


@pytest.fixture
def table(house) -> ScriptStore:
    return house[1].store.script_store


def test_what_is_written_for_an_agent_since_removed_is_not_written(table):
    then = table.era("coder")
    assert table.apply("coder", "job:due", {"seen": "[1]"}, ROOM, then)

    assert table.forget_agent("coder") == 1

    assert table.era("coder") != then
    assert not table.apply("coder", "job:due", {"seen": "[2]"}, ROOM, then)
    assert table.kept_by("coder") == []
    # Dropping a key is a write too, and what is there now is another agent's.
    assert table.apply("coder", "job:due", {"seen": "[3]"}, ROOM, table.era("coder"))
    assert not table.apply("coder", "job:due", {"seen": None}, ROOM, then)
    assert [row.text for row in table.kept_by("coder")] == ["[3]"]


def test_each_removal_of_an_id_is_told_from_the_one_before(table):
    """An id may be given and removed any number of times: none of them is another's."""
    seen = [table.era("coder")]
    for _ in range(3):
        table.forget_agent("coder")
        seen.append(table.era("coder"))

    assert len(set(seen)) == 4
    for old in seen[:-1]:
        assert not table.apply("coder", "job:due", {"n": "1"}, ROOM, old)
    assert table.era("coach") == seen[0]  # another agent's is not moved
    assert table.apply("coach", "job:due", {"n": "1"}, ROOM, table.era("coach"))


def test_a_script_told_its_agent_is_gone_is_not_told_its_store_is_full(table):
    script = Kept(table, "coder", "job:due", table.era("coder"))
    script.answer("store", {"key": "seen", "value": [1]})

    table.forget_agent("coder")

    assert script.commit() == STORE_AGENT_GONE
    assert table.kept_by("coder") == []
