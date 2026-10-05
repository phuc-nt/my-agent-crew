"""What a starting server does with the runs the last one was still working on
(`store/run_restart.py`), and how the hub holds one it takes up again (`activity/cut_runs.py`).

Every open row is closed. The newest of each conversation is handed back once, so the
server may carry it on; a run that was already a continuation is not, which is what keeps
a turn that takes the server down from doing so at every start."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store.db import Store
from my_agent_crew.store.runs import AWAITING, DONE, FAILED, RUNNING, RunRecord
from tests.conftest import collect


def working(store: Store, run_id: str, conv_id: str | None, started: str = "08:00", **fields):
    """A row as a process that died mid-turn leaves it."""
    run = RunRecord(run_id, "default", conv_id, "chat", "t", RUNNING, f"2026-10-06T{started}:00")
    for name, value in fields.items():
        setattr(run, name, value)
    store.runs.save(run)
    return run


def closed(store: Store, run_id: str) -> bool:
    run = store.runs.get(run_id)
    return (run.status, run.summary) == (FAILED, "interrupted") and run.finished_at is not None


def test_a_run_the_last_server_was_working_on_is_closed_and_handed_back_once(store):
    conv = store.create()
    working(store, "r1", conv.id, after_seq=3)

    hub = ActivityHub(store)

    [cut] = hub.cut
    assert (cut.id, cut.status, cut.summary, cut.after_seq) == ("r1", FAILED, "interrupted", 3)
    # Closed in the store too: left open, a server that takes nothing up would show it
    # working for good.
    assert closed(store, "r1") and hub.live() == []
    assert not hub.busy.busy(conv.id)
    # The next start finds nothing open, so it has nothing to hand back.
    assert ActivityHub(store).cut == []


def test_a_run_that_was_already_taken_up_once_is_closed_for_good(store):
    conv = store.create()
    working(store, "r1", conv.id, resumed=True)

    assert ActivityHub(store).cut == [] and closed(store, "r1")


def test_only_the_newest_working_run_of_a_conversation_is_handed_back(store):
    """Two open rows in one conversation is what a crash between two turns left; carrying
    the older one on would answer a message the newer turn already answered."""
    conv, other = store.create(), store.create()
    working(store, "old", conv.id, "08:00")
    working(store, "new", conv.id, "09:00")
    working(store, "elsewhere", other.id, "07:00")

    hub = ActivityHub(store)

    assert sorted(run.id for run in hub.cut) == ["elsewhere", "new"]
    assert all(closed(store, run_id) for run_id in ("old", "new", "elsewhere"))


def test_a_run_with_no_conversation_has_nothing_to_carry_on_from(store):
    working(store, "command", None)

    assert ActivityHub(store).cut == [] and closed(store, "command")


def test_a_conversation_that_waits_on_a_decision_keeps_its_paused_run_only(store):
    """The decision continues the paused run. A working row beside it is older debris."""
    conv = store.create()
    working(store, "stale", conv.id, "08:00")
    paused = RunRecord("paused", "default", conv.id, "chat", "t", AWAITING, "2026-10-06T09:00:00")
    store.runs.save(paused)
    store.approvals.create(conv.id, 1, ToolCall("c1", "shell_run", {"command": "ls"}))

    hub = ActivityHub(store)

    assert hub.cut == [] and [run.id for run in hub.live()] == ["paused"]
    assert closed(store, "stale") and store.runs.get("paused").status == AWAITING


def test_whether_a_run_was_taken_up_is_stored_with_it(store):
    conv = store.create()
    working(store, "fresh", conv.id)
    working(store, "again", conv.id, resumed=True)

    assert store.runs.get("fresh").resumed is False and store.runs.get("again").resumed is True
    assert store.runs.get("again").to_dict()["resumed"] is True


def test_an_older_database_gains_the_column_and_its_open_run_is_handed_back(tmp_path: Path):
    path = tmp_path / "agent.sqlite3"
    first = Store(path)
    conv = first.create()
    working(first, "r1", conv.id)
    first.close()
    old = sqlite3.connect(path)
    old.execute("ALTER TABLE runs DROP COLUMN resumed")
    old.commit()
    old.close()

    store = Store(path)

    assert store.runs.get("r1").resumed is False
    assert [run.id for run in ActivityHub(store).cut] == ["r1"]
    store.close()


def reopened(store: Store, **fields) -> tuple[ActivityHub, RunRecord, str]:
    conv = store.create()
    working(store, "r1", conv.id, **fields)
    hub = ActivityHub(store)
    [run] = hub.cut
    hub.reopen(run)
    return hub, run, conv.id


def test_a_run_taken_up_is_working_again_and_marked_before_its_turn_takes_a_step(store):
    hub, run, conv_id = reopened(store)

    stored = store.runs.get("r1")
    # Written down at once: a turn that kills the server on its first step is still found
    # marked by the next start.
    assert (stored.status, stored.finished_at, stored.summary, stored.resumed) == (
        RUNNING,
        None,
        "",
        True,
    )
    assert hub.holding(run) and hub.live() == [run]
    assert hub.busy.busy(conv_id)  # what is sent meanwhile waits behind it


def test_the_model_call_that_died_with_the_server_leaves_no_step(store):
    answered = {"kind": "model", "duration_ms": 12}
    dead = {"kind": "model", "_clock": 41.5}
    hub, run, _ = reopened(store, steps=[answered, dead])

    assert run.steps == [answered] and store.runs.get("r1").steps == [answered]


def test_a_step_that_ended_is_kept_whatever_came_last(store):
    tool = {"kind": "tool", "tool_call_id": "c1", "ok": None, "_clock": 3.0}
    hub, run, _ = reopened(store, steps=[{"kind": "model", "duration_ms": 12}, tool])

    assert [step["kind"] for step in run.steps] == ["model", "tool"]


def test_the_turn_that_starts_next_continues_the_run_that_was_taken_up(store):
    hub, run, conv_id = reopened(store, after_seq=7)

    started = hub.start("default", "chat", "another title", conv_id)

    assert started is run and started.after_seq == 7
    assert not hub.holding(run)
    # Only that one turn: the turn after it is a run of its own.
    hub.finish(run, status=DONE)
    assert hub.start("default", "chat", "t", conv_id).id != "r1"


def test_a_run_let_go_while_the_server_stays_up_is_closed(store):
    hub, run, conv_id = reopened(store)

    hub.interrupt(run)

    assert closed(store, "r1") and hub.live() == [] and not hub.holding(run)
    assert not hub.busy.busy(conv_id)


def test_a_run_let_go_while_the_server_goes_down_is_left_for_the_next_start(store):
    hub, run, conv_id = reopened(store)
    hub.going_down = True

    hub.interrupt(run)

    stored = store.runs.get("r1")
    assert (stored.status, stored.finished_at) == (RUNNING, None)
    assert hub.live() == [] and not hub.holding(run)
    # It was taken up once already, so the next start closes it and hands nothing back.
    assert ActivityHub(store).cut == [] and closed(store, "r1")


async def reader_stops(deps, hub: ActivityHub, conv_id: str) -> RunRecord:
    """A turn whose reader goes away after its first event."""
    events = tracked(hub, run_turn(deps, conv_id, "chào"), "default", "chat", "t", conv_id)
    await anext(events)
    await events.aclose()
    run = deps.store.runs.latest_for_conversation(conv_id)
    assert run is not None
    return run


async def test_a_turn_whose_reader_stops_is_closed_while_the_server_stays_up(deps_factory):
    deps = deps_factory(script=[completion("xin chào")])
    conv = deps.store.create()

    run = await reader_stops(deps, ActivityHub(deps.store), conv.id)

    assert (run.status, run.summary) == (FAILED, "interrupted")


async def test_a_turn_whose_reader_stops_as_the_server_goes_down_stays_open(deps_factory):
    deps = deps_factory(script=[completion("xin chào")])
    conv = deps.store.create()
    hub = ActivityHub(deps.store)
    hub.going_down = True

    run = await reader_stops(deps, hub, conv.id)

    assert (run.status, run.finished_at, run.resumed) == (RUNNING, None, False)
    assert hub.live() == [] and not hub.busy.busy(conv.id)
    assert [cut.id for cut in ActivityHub(deps.store).cut] == [run.id]


async def test_a_wait_on_a_run_that_ended_before_the_restart_is_answered_from_the_store(
    deps_factory,
):
    """A delegating turn carried on after a restart waits on a child that may have ended
    in the process that is gone: nothing here will ever raise that run's signal."""
    deps = deps_factory(script=[completion("xong")])
    conv = deps.store.create()
    events = tracked(
        ActivityHub(deps.store), run_turn(deps, conv.id, "hi"), "default", "chat", "t", conv.id
    )
    await collect(events)

    hub = ActivityHub(deps.store)
    run = await hub.wait_finished(conv.id, timeout=0.01)

    assert run is not None and run.status == DONE and run.conversation_id == conv.id


async def test_a_wait_on_a_run_taken_up_again_lasts_until_it_ends(store):
    hub, run, conv_id = reopened(store)

    assert await hub.wait_finished(conv_id, timeout=0.01) is None
    hub.finish(run, status=DONE)
    ended = await hub.wait_finished(conv_id, timeout=0.01)
    assert ended is not None and (ended.id, ended.status) == ("r1", DONE)


async def test_a_wait_on_a_conversation_that_never_ran_still_runs_out(store):
    conv = store.create()

    assert await ActivityHub(store).wait_finished(conv.id, timeout=0.01) is None
