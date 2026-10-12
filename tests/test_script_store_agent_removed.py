"""What an agent's scripts kept goes with the agent, and nothing comes back under its id
(`store/script_store.py`, `script/store_session.py`, `server/routes_agents_edit.py`).

Removing an agent stops none of what it is doing. A script of its that is running then, or a
later one of a turn that outlives it, ends well and would write what it stored: rows under
the id of an agent that is gone, which an agent later given the id would read as its own.
So nothing put together for an agent before it was removed writes there again. The script
is told that none of it was kept, as a script that failed. Nor does it read there: what lies
under the id by then is another agent's, and a script that asks is answered with nothing and
ends the same way.

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
from my_agent_crew.store.models import Conversation
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
# What the agent that has the id by then keeps, in the place the script of the one before
# reads; and that script, which is answered with nothing of it.
THEIRS = "của agent mới"
KEEPS = f'store("seen", "{THEIRS}")'
LOADS = 'print(load("seen"))'
WAITS_THEN_LOADS = f"""
tools.hung_read()
{LOADS}
"""
LOADS_THEN_WAITS_AND_LOADS = f"""
{LOADS}
tools.hung_read()
{LOADS}
"""
NOT_READ = unfinished("None", STORE_AGENT_GONE)


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


async def in_a_turn(
    deps: AgentDeps,
    runtime: Runtime,
    source: str = STORES_THEN_WAITS,
    conv: Conversation | None = None,
) -> ToolResult:
    """The script as a call of a turn of the agent's, which keeps under its conversation:
    `conv` when two scripts are to keep in one place, else a conversation of its own."""
    conv = conv or runtime.store.create(agent_id=deps.agent.id)
    result, _ = await played(deps, conv.id, source)
    return result


async def of_a_schedule(
    deps: AgentDeps,
    runtime: Runtime,
    source: str = STORES_THEN_WAITS,
    conv: Conversation | None = None,
) -> ToolResult:
    """The script as a schedule's job runs it (`scheduler/script_job.py`), which keeps under
    the schedule's id, whatever conversation is named."""
    return (await run_source(source, deps.tools, kept=job_kept(deps, "due"))).result


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
async def test_a_script_of_a_removed_agent_reads_nothing_kept_under_its_id(house, begun):
    """The turn goes on with the agent it began with. A script of it that asks after the
    removal is answered with nothing, the id taken again or not, and is told its agent is
    gone as one that stored is."""
    client, runtime = house
    made(client)
    deps = runtime.deps_for("coder")
    conv = runtime.store.create(agent_id="coder")

    removed(client)
    with_nobody = await begun(deps, runtime, LOADS, conv)
    made(client)
    assert (await begun(runtime.deps_for("coder"), runtime, KEEPS, conv)).ok
    theirs = rows(runtime)
    with_another = await begun(deps, runtime, LOADS, conv)

    assert [(key, text) for _, key, text in theirs] == [("seen", f'"{THEIRS}"')]
    assert (with_nobody.ok, with_nobody.output) == (False, NOT_READ)
    assert (with_another.ok, with_another.output) == (False, NOT_READ)
    assert rows(runtime) == theirs


@BEGUN
async def test_a_script_running_when_its_agent_is_removed_reads_nothing_kept_since(house, begun):
    """It had not asked yet when the agent went, so what it asks for now is asked of an id
    that is another agent's."""
    client, runtime = house
    made(client)
    deps, waits = waiting(runtime)
    conv = runtime.store.create(agent_id="coder")
    script = asyncio.create_task(begun(deps, runtime, WAITS_THEN_LOADS, conv))
    await waits.entered.wait()

    removed(client)
    made(client)
    assert (await begun(runtime.deps_for("coder"), runtime, KEEPS, conv)).ok
    waits.go.set()
    result = await script

    assert (result.ok, result.output) == (False, NOT_READ)
    assert [(key, text) for _, key, text in rows(runtime)] == [("seen", f'"{THEIRS}"')]


@BEGUN
async def test_what_a_script_read_before_its_agent_went_is_what_it_goes_on_reading(house, begun):
    """A script goes by what the place held when it first asked. That was its own agent's,
    and it asks the table no more: nothing of the agent that has the id since reaches it."""
    client, runtime = house
    made(client)
    deps, waits = waiting(runtime)
    conv = runtime.store.create(agent_id="coder")
    assert (await begun(deps, runtime, 'store("seen", "của agent cũ")', conv)).ok
    script = asyncio.create_task(begun(deps, runtime, LOADS_THEN_WAITS_AND_LOADS, conv))
    await waits.entered.wait()

    removed(client)
    made(client)
    assert (await begun(runtime.deps_for("coder"), runtime, KEEPS, conv)).ok
    waits.go.set()
    result = await script

    assert (result.ok, result.output) == (True, "của agent cũ\ncủa agent cũ")
    assert [(key, text) for _, key, text in rows(runtime)] == [("seen", f'"{THEIRS}"')]


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


def test_what_is_read_for_an_agent_since_removed_is_nothing_of_the_agent_that_has_the_id(table):
    then = table.era("coder")
    assert table.apply("coder", "job:due", {"seen": "[1]"}, ROOM, then)
    assert table.read_as("coder", "job:due", then) == {"seen": "[1]"}

    table.forget_agent("coder")
    now = table.era("coder")
    assert table.read_as("coder", "job:due", then) is None
    assert table.read_as("coder", "job:due", now) == {}
    assert table.apply("coder", "job:due", {"seen": "[2]"}, ROOM, now)

    assert table.read_as("coder", "job:due", then) is None
    assert table.read_as("coder", "job:due", now) == {"seen": "[2]"}
    # Another agent's era is its own, and a place that holds nothing is not a place refused.
    assert table.read_as("coach", "job:due", table.era("coach")) == {}


class LetGo:
    """The table's lock, which does one thing the first time nobody holds it any more: what
    another thread would do, had it been waiting for the lock."""

    def __init__(self, lock, then) -> None:
        self._lock, self._then, self._holds = lock, then, 0

    def __enter__(self) -> None:
        self._lock.acquire()
        self._holds += 1

    def __exit__(self, *raised) -> None:
        self._holds -= 1
        self._lock.release()
        if not self._holds and self._then is not None:
            then, self._then = self._then, None
            then()


def test_no_removal_falls_between_the_look_at_the_era_and_the_read(table, monkeypatch):
    """The era is looked at in the hold of the lock that reads, as a write's is. Looked at
    in a hold of its own, it could be the agent's when looked at and another's when read."""
    then = table.era("coder")
    assert table.apply("coder", "job:due", {"seen": "[1]"}, ROOM, then)

    def another_takes_the_id() -> None:
        table.forget_agent("coder")
        assert table.apply("coder", "job:due", {"seen": "[2]"}, ROOM, table.era("coder"))

    monkeypatch.setattr(table, "_lock", LetGo(table._lock, another_takes_the_id))

    assert table.read_as("coder", "job:due", then) == {"seen": "[1]"}
    assert table.read_as("coder", "job:due", then) is None


def test_a_script_that_only_read_for_an_agent_since_removed_is_told_the_agent_is_gone(table):
    then = table.era("coder")
    table.forget_agent("coder")
    assert table.apply("coder", "job:due", {"seen": "[2]"}, ROOM, table.era("coder"))
    script = Kept(table, "coder", "job:due", then)

    assert script.answer("load", {"key": "seen"}) is None
    assert script.commit() == STORE_AGENT_GONE
    # The agent that has the id reads its own, and ends with nothing to be told.
    theirs = Kept(table, "coder", "job:due", table.era("coder"))
    assert theirs.answer("load", {"key": "seen"}) == "[2]"
    assert theirs.commit() is None
    assert [row.text for row in table.kept_by("coder")] == ["[2]"]
