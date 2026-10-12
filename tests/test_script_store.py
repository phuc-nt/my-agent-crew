"""What a script keeps from one run to the next (`store` and `load`).

A script reads its own writes, and none of them reaches the table before it ended well: one
that failed, was refused a call, ran out of time or was stopped leaves things as it found
them. Where a value is kept is the server's to say and never the script's: under the
conversation of the turn, under the schedule when a job opened that conversation, and nowhere
outside both (`script/store_session.py` over `store/script_store.py`). How much may be kept
is in `test_script_limits.py`, a schedule's own script in `test_script_job.py`, and what the
owner is shown of it in `test_api_script_store.py`. Every script here runs in a real child
process.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from functools import partial
from typing import Any

import pytest

from my_agent_crew import texts_script as t
from my_agent_crew import texts_script_store as kept_texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.script import limits
from my_agent_crew.script import tool as script_module
from my_agent_crew.script.scope import SCRIPT_TOOL
from my_agent_crew.script.store_session import job_kept
from my_agent_crew.script.tool import hand_script, run_source
from my_agent_crew.tools.registry import Tool
from tests.test_script_gate import played, ran
from tests.test_script_tool import SCHEMA, erred, halted, unfinished

Held = dict[tuple[str, str], str]


def agent(deps_factory, *tools: Tool, **settings: Any) -> AgentDeps:
    """An agent with `tools` beside its own, handed the script tool as the server hands it."""
    deps = deps_factory(**settings)
    for tool in tools:
        deps.tools.register(tool)
    hand_script(deps)
    return deps


def held(deps: AgentDeps) -> Held:
    """All the agent keeps, as the table holds it: (namespace, key) to the value's JSON."""
    rows = deps.store.script_store.kept_by(deps.agent.id)
    return {(row.namespace, row.key): row.text for row in rows}


def of(conv) -> str:
    return f"conv:{conv.id}"


class Waits:
    """A tool that only reads and does not answer until it is let go; `entered` is set once
    a script got as far as calling it."""

    def __init__(self) -> None:
        self.entered, self.go = asyncio.Event(), asyncio.Event()
        self.tool = Tool("hung_read", "Đọc.", SCHEMA, self._run, replay_safe=True)

    async def _run(self, arguments: dict[str, Any]) -> str:
        self.entered.set()
        await self.go.wait()
        return "muộn"


# --- one script, and the next ---


async def test_a_script_reads_what_it_wrote_and_none_of_it_is_kept_until_it_ends(deps_factory):
    seen: list[Held] = []

    async def look(arguments: dict[str, Any]) -> str:
        seen.append(held(deps))
        return "đã nhìn"

    deps = agent(deps_factory, Tool("table_look", "Nhìn.", SCHEMA, look, replay_safe=True))
    conv = deps.store.create()

    result = await ran(
        deps,
        conv,
        """
        store("seen", ["a", "b"])
        print(load("seen"), load("never"))
        tools.table_look()
        store("seen", load("seen") + ["c"])
        print(load("seen"))
        """,
    )

    assert (result.ok, result.output) == (True, "['a', 'b'] None\n['a', 'b', 'c']")
    # Half-way through, the script had its first write to read and the table had nothing.
    assert seen == [{}]
    assert held(deps) == {(of(conv), "seen"): '["a","b","c"]'}


async def test_what_a_script_kept_is_there_for_the_next_script_of_the_conversation(deps_factory):
    deps = agent(deps_factory)
    conv = deps.store.create()

    first = await ran(deps, conv, 'store("due", {"HP3-12": 14, "done": False})')
    second = await ran(deps, conv, 'due = load("due")\nprint(due["HP3-12"] + 1, due["done"])')

    assert first.ok and (second.ok, second.output) == (True, "15 False")


async def test_storing_none_drops_the_key(deps_factory):
    deps = agent(deps_factory)
    conv = deps.store.create()
    await ran(deps, conv, 'store("a", 1)\nstore("b", 2)')

    result = await ran(
        deps, conv, 'store("a", None)\nstore("never", None)\nprint(load("a"), load("b"))'
    )

    assert (result.ok, result.output) == (True, "None 2")
    assert held(deps) == {(of(conv), "b"): "2"}


async def test_a_none_inside_a_value_is_kept_where_a_none_alone_forgets_the_key(deps_factory):
    deps = agent(deps_factory)
    conv = deps.store.create()
    await ran(deps, conv, 'store("due", [1, None])\nstore("gone", {"at": None})')

    result = await ran(deps, conv, 'store("gone", None)\nprint(load("due"), load("gone"))')

    assert (result.ok, result.output) == (True, "[1, None] None")
    assert held(deps) == {(of(conv), "due"): "[1,null]"}


# --- a script that did not end well ---

NOT_FROM_A_SCRIPT = t.SCRIPT_ASKS_FIRST.format(name="shell_run", instead="gọi trực tiếp")
# Each is the third line of its script: two writes come before it.
ENDED_BADLY = [
    # A mistake nothing caught.
    ("print(nowhere_named)", erred(3, t.SCRIPT_NO_NAME.format(name="nowhere_named"))),
    # A call a script of this agent may not make ends it where it asked.
    ('tools.shell_run(command="ls")', halted(3, NOT_FROM_A_SCRIPT)),
]


@pytest.mark.parametrize(("last_line", "said"), ENDED_BADLY)
async def test_a_script_that_did_not_end_well_keeps_nothing_of_what_it_wrote(
    deps_factory, last_line, said
):
    deps = agent(deps_factory)
    conv = deps.store.create()
    await ran(deps, conv, 'store("n", 0)\nstore("other", "cũ")')

    result = await ran(deps, conv, f'store("other", None)\nstore("n", 1)\n{last_line}')

    assert (result.ok, result.output) == (False, unfinished(said))
    # Neither the new value nor the key it dropped: what the last good run left is whole.
    assert held(deps) == {(of(conv), "n"): "0", (of(conv), "other"): '"cũ"'}


async def test_a_script_its_clock_ended_keeps_nothing(deps_factory, monkeypatch):
    """The clock is shortened, so the script is ended while its call still waits."""
    waits = Waits()
    shortened = partial(script_module.run_script, total_s=1.5)
    monkeypatch.setattr(script_module, "run_script", shortened)
    deps = agent(deps_factory, waits.tool)
    conv = deps.store.create()

    try:
        result = await ran(deps, conv, 'store("n", 1)\ntools.hung_read()')
    finally:
        waits.go.set()

    assert not result.ok and t.SCRIPT_TIMED_OUT.format(seconds=1.5) in result.output
    # It had written before it waited: the write was on its way and is not kept.
    assert waits.entered.is_set() and held(deps) == {}


async def test_a_script_that_was_stopped_keeps_nothing(deps_factory):
    waits = Waits()
    deps = agent(deps_factory, waits.tool)
    conv = deps.store.create()

    turn = asyncio.create_task(played(deps, conv.id, 'store("n", 1)\ntools.hung_read()'))
    await waits.entered.wait()
    turn.cancel()

    with pytest.raises(asyncio.CancelledError):
        await turn
    assert held(deps) == {}


async def test_writes_that_no_longer_fit_when_the_script_ends_are_none_of_them_kept(
    deps_factory, monkeypatch
):
    """Two runs of one conversation, each within the limit by what it saw when it began.
    The one that ends second would take the namespace past it."""
    most = 60
    monkeypatch.setattr(limits, "MAX_STORE_TOTAL_CHARS", most)
    theirs = {"theirs": '"' + "y" * 40 + '"'}

    async def other_run_ends(arguments: dict[str, Any]) -> str:
        assert deps.store.script_store.apply(deps.agent.id, of(conv), theirs, most)
        return "xong"

    other = Tool("other_run_ends", "Đọc.", SCHEMA, other_run_ends, replay_safe=True)
    deps = agent(deps_factory, other)
    conv = deps.store.create()

    result = await ran(
        deps,
        conv,
        """
        store("mine", "x" * 30)
        store("small", 1)
        tools.other_run_ends()
        print("hết")
        """,
    )

    # It ran to its end, and is told as a script that failed that nothing of it was kept.
    said = kept_texts.STORE_NOT_KEPT.format(most=most)
    assert (result.ok, result.output) == (False, unfinished("hết", said))
    # Not the small write either, which would have fitted alone: all of them or none.
    assert held(deps) == {(of(conv), "theirs"): theirs["theirs"]}


# --- where it is kept ---


async def test_two_conversations_of_one_agent_each_keep_their_own(deps_factory):
    deps = agent(deps_factory)
    first, second = deps.store.create(), deps.store.create()
    await ran(deps, first, 'store("n", "một")')

    result = await ran(deps, second, 'print(load("n"))\nstore("n", "hai")')

    assert (result.ok, result.output) == (True, "None")
    assert held(deps) == {(of(first), "n"): '"một"', (of(second), "n"): '"hai"'}

    # What one of them drops is its own key: the other still holds the one it wrote.
    await ran(deps, first, 'store("n", None)')
    assert held(deps) == {(of(second), "n"): '"hai"'}


async def test_two_agents_keeping_under_one_name_do_not_read_each_other(deps_factory, tmp_path):
    """Two agents of one crew may each have a job called `due`, in the one database."""
    one, other = deps_factory(), deps_factory(home=tmp_path / "other-home")
    other.profile = replace(other.agent, id="coach")
    assert one.store is other.store

    await run_source('store("n", 1)', one.tools, None, job_kept(one, "due"))
    result, printed, _ = await run_source(
        'print(load("n"))\nstore("n", 2)', other.tools, None, job_kept(other, "due")
    )

    assert result.ok and printed == "None"
    assert held(one) == {("job:due", "n"): "1"} and held(other) == {("job:due", "n"): "2"}

    await run_source('store("n", None)', one.tools, None, job_kept(one, "due"))
    assert held(one) == {} and held(other) == {("job:due", "n"): "2"}


async def test_a_turn_of_the_conversation_a_job_opened_keeps_under_the_jobs_schedule(deps_factory):
    deps = agent(deps_factory)
    hub, conv = ActivityHub(deps.store), deps.store.create()
    hub.start(deps.agent.id, f"job:{deps.agent.id}/due", "[lịch] Nhắc hạn", conv.id)

    result = await ran(deps, conv, 'store("told", ["HP3-12"])')

    assert result.ok and held(deps) == {("job:due", "told"): '["HP3-12"]'}


async def test_a_turn_somebody_took_up_in_a_jobs_conversation_keeps_under_the_conversation(
    deps_factory,
):
    """The person answered the job's message: that turn is theirs, and its run names no job."""
    deps = agent(deps_factory)
    hub, conv = ActivityHub(deps.store), deps.store.create()
    hub.start(deps.agent.id, f"job:{deps.agent.id}/due", "[lịch] Nhắc hạn", conv.id)
    await ran(deps, conv, 'store("told", 1)')
    hub.start(deps.agent.id, "telegram", "Trả lời", conv.id)

    result = await ran(deps, conv, 'print(load("told"))\nstore("mine", 2)')

    assert (result.ok, result.output) == (True, "None")
    assert held(deps) == {("job:due", "told"): "1", (of(conv), "mine"): "2"}


async def test_a_script_outside_any_conversation_is_told_there_is_nowhere_and_may_carry_on(
    deps_factory,
):
    deps = agent(deps_factory)

    result = await ran(
        deps,
        None,
        """
        try:
            store("n", 1)
        except Exception as e:
            print(e)
        try:
            load("n")
        except Exception as e:
            print(e)
        print("sau")
        """,
    )

    nowhere = kept_texts.STORE_NOWHERE
    assert (result.ok, result.output) == (True, f"{nowhere}\n{nowhere}\nsau")
    assert held(deps) == {}


# --- what the model is told ---


@pytest.mark.parametrize("script_calls", ["read_only", "gated"])
def test_the_model_is_told_how_a_script_keeps_a_thing_and_when_it_is_kept(
    deps_factory, script_calls
):
    """Told whichever tools its scripts may call. A model nobody told would never keep a thing,
    and one told only the two names would take the None of a first run for a mistake, count
    on what a script that failed had written, or keep a None to mark a thing as done and read
    back a key that holds nothing."""
    told = agent(deps_factory, script_calls=script_calls).tools.get(SCRIPT_TOOL).description

    assert "`store(khoá, giá_trị)` giữ một giá trị JSON" in told
    assert "`load(khoá)` đọc lại ở lần chạy sau (chưa có thì None)" in told
    assert "`store(khoá, None)` là quên khoá đó" in told
    assert "chỉ giữ khi script chạy xong không lỗi" in told
    assert "riêng cho cuộc trò chuyện hoặc job này" in told
