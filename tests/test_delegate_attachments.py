"""Charts a delegated agent attaches reach the person, not just the agent that asked.

A coach drew two charts, the master retold its answer, and neither chart arrived: the
retelling dropped the `MEDIA:` lines, and even copied they named paths in the coach's
workspace, where the master's reply is never looked up."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.config import Route
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store import Store
from my_agent_crew.tools.delegate import DELEGATE_TOOL_NAME
from my_agent_crew.tools.delegate_attachments import RELAY_DIR, dropped_attachments
from tests.conftest import collect
from tests.test_tools_delegate import agent, delegate

CHART = b"\x89PNG fake chart"
TASK = "Tình hình ngủ\nMEDIA: charts/sleep.png"


def _crew(deps_factory, store: Store, tmp_path: Path, boss_script=()) -> Runtime:
    """A boss on a scripted model and a worker with its own workspace, echoing its task."""
    base = deps_factory(script=boss_script)
    worker = agent(deps_factory(routes=(Route("fake", "echo"),)), "worker")
    coach_root = tmp_path / "coach"
    (coach_root / "charts").mkdir(parents=True)
    (coach_root / "charts" / "sleep.png").write_bytes(CHART)
    worker = replace(worker, profile=replace(worker.profile, workspace=coach_root))
    agents = {"boss": agent(base, "boss", delegates=("worker",)), "worker": worker}
    rt = Runtime(base.settings, store, agents, ActivityHub(store))
    rt.wire_delegation()
    return rt


async def test_a_childs_chart_is_copied_into_the_parents_workspace(
    deps_factory, store: Store, tmp_path: Path
):
    rt = _crew(deps_factory, store, tmp_path)
    parent = rt.store.create(agent_id="boss", autonomous=True)
    out = await delegate(rt, parent.id, "call-1", task=TASK, agent="worker")

    child = rt.store.for_parent_call("call-1")
    relayed = f"{RELAY_DIR}/{child.id}/sleep.png"
    assert f"MEDIA: {relayed}" in out and "MEDIA: charts/sleep.png" not in out
    assert (rt.deps_for("boss").agent.workspace / relayed).read_bytes() == CHART


@pytest.mark.parametrize("path", ["charts/missing.png", "../../outside.png"])
async def test_an_attachment_that_cannot_be_carried_over_is_said_in_words(
    deps_factory, store: Store, tmp_path: Path, path: str
):
    (tmp_path / "outside.png").write_bytes(CHART)
    rt = _crew(deps_factory, store, tmp_path)
    parent = rt.store.create(agent_id="boss", autonomous=True)
    out = await delegate(rt, parent.id, "call-1", task=f"x\nMEDIA: {path}", agent="worker")

    assert texts.DELEGATE_ATTACHMENT_LOST.format(path=path) in out
    assert "MEDIA:" not in out.replace(texts.DELEGATE_ATTACHMENT_LOST.format(path=path), "")


def _boss_script(final: str, **args):
    call = ToolCall("c1", DELEGATE_TOOL_NAME, {"task": TASK, "agent": "worker", **args})
    return [completion(tool_calls=(call,)), completion(final)]


async def test_a_relayed_answer_carries_the_chart_at_its_new_path(
    deps_factory, store: Store, tmp_path: Path
):
    """When the child's answer is handed on whole, the chart line it carries is already
    the copied one, so the person gets the chart without a retelling at all."""
    rt = _crew(deps_factory, store, tmp_path, _boss_script("không được gọi tới"))
    conv = rt.store.create(agent_id="boss", autonomous=True)
    await collect(run_turn(rt.deps_for("boss"), conv.id, "tôi ngủ thế nào?"))

    child = rt.store.for_parent_call("c1")
    final = rt.store.history(conv.id)[-1].message.content
    assert final.startswith("(echo) Tình hình ngủ")
    assert final.endswith(f"MEDIA: {RELAY_DIR}/{child.id}/sleep.png")


async def test_the_final_reply_gets_back_charts_the_retelling_dropped(
    deps_factory, store: Store, tmp_path: Path
):
    # `relay: false`: the boss keeps the last word, and its retelling drops the chart.
    rt = _crew(deps_factory, store, tmp_path, _boss_script("Anh ngủ ổn.", relay=False))
    conv = rt.store.create(agent_id="boss", autonomous=True)
    await collect(run_turn(rt.deps_for("boss"), conv.id, "tôi ngủ thế nào?"))

    child = rt.store.for_parent_call("c1")
    final = rt.store.history(conv.id)[-1].message.content
    assert final.startswith("Anh ngủ ổn.")
    assert final.endswith(f"MEDIA: {RELAY_DIR}/{child.id}/sleep.png")


async def test_a_reply_that_kept_the_chart_does_not_get_it_twice(
    deps_factory, store: Store, tmp_path: Path
):
    # The child conversation id is not known before the turn, so the kept line is written
    # the way the model would copy it: from the tool result it just read.
    rt = _crew(deps_factory, store, tmp_path)
    conv = rt.store.create(agent_id="boss", autonomous=True)
    parent = rt.store.create(agent_id="boss", autonomous=True)
    out = await delegate(rt, parent.id, "call-x", task=TASK, agent="worker")
    kept = next(line for line in out.split("\n") if line.startswith("MEDIA:"))
    rt.store.append(conv.id, Message(role="user", content="q"))
    rt.store.append(conv.id, Message(role="tool", content=out, name=DELEGATE_TOOL_NAME))

    reply = f"Anh ngủ ổn.\n{kept}"
    assert dropped_attachments(rt.store.history(conv.id), reply) == []
    assert dropped_attachments(rt.store.history(conv.id), "Anh ngủ ổn.") == [kept]


def test_charts_from_an_earlier_turn_are_not_attached_again(store: Store):
    conv = store.create()
    store.append(conv.id, Message(role="user", content="hôm qua"))
    store.append(conv.id, Message(role="tool", content="MEDIA: old.png", name=DELEGATE_TOOL_NAME))
    store.append(conv.id, Message(role="assistant", content="xong"))
    store.append(conv.id, Message(role="user", content="hôm nay"))

    assert dropped_attachments(store.history(conv.id), "câu trả lời mới") == []
