"""Asking the person mid-turn: the pause, the answer, and the deadline nobody met.

A question reuses the approval machinery for the pause and the resume, but it must not
inherit the approve/deny meaning. The tests below pin the two places that differ: an
autonomous conversation still stops to ask, and a question nobody answered is not a
refusal — it hands back its default and the turn carries on.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.approval_expiry import expire_overdue
from my_agent_crew.agent.events import ApprovalRequiredEvent, DoneEvent, ToolResultEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.resume import answer_question, resolve_approval
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store.approvals import ANSWERED
from my_agent_crew.store.models import AWAITING_APPROVAL, IDLE, QUESTION
from my_agent_crew.tools.ask_user import ASK_USER_UNANSWERED, ASK_USER_UNANSWERED_NO_DEFAULT
from tests.conftest import collect

ASKING = ToolCall(
    "q1",
    "ask_user",
    {
        "question": "Dời hạn sang thứ sáu?",
        "options": ["có", "không"],
        "default": "giữ nguyên hạn cũ",
    },
)
BARE = ToolCall("q2", "ask_user", {"question": "Chọn mục nào?"})


def asked(deps, text: str = "xem hạn"):
    """Run a turn that asks, and return the pause event."""
    return completion(tool_calls=(ASKING,)), text


async def test_asking_pauses_the_turn_and_carries_the_choices(deps_factory):
    deps = deps_factory(script=[completion(tool_calls=(ASKING,)), completion("ok")])
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, "xem hạn"))
    pause = events[-1]
    assert isinstance(pause, ApprovalRequiredEvent)
    assert pause.kind == QUESTION and pause.options == ["có", "không"]
    assert pause.arguments["question"] == "Dời hạn sang thứ sáu?"
    assert deps.store.get(conv.id).status == AWAITING_APPROVAL
    # The model was asked once and is not asked again until somebody answers.
    assert len(deps.chain.providers["scripted"].requests) == 1


async def test_an_autonomous_conversation_still_stops_to_ask(deps_factory):
    """Autonomy means 'do not ask me to authorise your tools', not 'never speak to me'.
    A question that approved itself would be answered by nobody and tell the agent
    nothing, so the one pause autonomy does not skip is this one."""
    deps = deps_factory(script=[completion(tool_calls=(ASKING,)), completion("ok")])
    conv = deps.store.create(autonomous=True)
    events = await collect(run_turn(deps, conv.id, "xem hạn"))
    assert isinstance(events[-1], ApprovalRequiredEvent) and events[-1].kind == QUESTION


async def test_answering_hands_the_words_to_the_model_and_finishes(deps_factory):
    deps = deps_factory(script=[completion(tool_calls=(ASKING,)), completion("đã dời")])
    conv = deps.store.create()
    paused = await collect(run_turn(deps, conv.id, "xem hạn"))
    events = await collect(
        answer_question(deps, conv.id, paused[-1].approval_id, "có, dời sang thứ sáu")
    )
    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result.ok and "dời sang thứ sáu" in result.output
    # What the model reads next is the answer, not a refusal.
    last = deps.chain.providers["scripted"].requests[1].messages[-1]
    assert last.role == "tool" and "dời sang thứ sáu" in last.content
    assert isinstance(events[-1], DoneEvent)
    assert deps.store.get(conv.id).status == IDLE
    assert deps.store.approvals.get(paused[-1].approval_id).status == ANSWERED


async def test_a_question_cannot_be_closed_by_approving_it(deps_factory):
    """The web sends approve/deny and answers through the same panel. Approving a
    question would close the row with no text in it, and the agent would resume having
    learned nothing from a pause it took on purpose."""
    deps = deps_factory(script=[completion(tool_calls=(ASKING,)), completion("ok")])
    conv = deps.store.create()
    paused = await collect(run_turn(deps, conv.id, "xem hạn"))
    with pytest.raises(KeyError):
        await collect(resolve_approval(deps, conv.id, paused[-1].approval_id, approve=True))


async def test_answering_a_tool_approval_is_refused(deps_factory):
    write = ToolCall("c1", "workspace_write", {"path": "out.txt", "content": "x"})
    deps = deps_factory(script=[completion(tool_calls=(write,)), completion("ok")])
    conv = deps.store.create()
    paused = await collect(run_turn(deps, conv.id, "ghi"))
    with pytest.raises(KeyError):
        await collect(answer_question(deps, conv.id, paused[-1].approval_id, "ừ chạy đi"))
    assert not (deps.settings.workspace_dir / "out.txt").exists()


async def test_nobody_answered_so_the_agent_goes_on_with_its_default(deps_factory):
    """The failure this prevents: a night job asks, nobody is awake, and the run stops
    dead. Expiry is a refusal for a tool and an instruction for a question."""
    deps = deps_factory(script=[completion(tool_calls=(ASKING,)), completion("giữ nguyên")])
    conv = deps.store.create()
    await collect(run_turn(deps, conv.id, "xem hạn"))
    later = datetime.now(UTC) + timedelta(seconds=deps.settings.approval_ttl_seconds + 1)

    closed = await expire_overdue({deps.agent.id: deps}, ActivityHub(deps.store), now=later)

    assert len(closed) == 1
    last = deps.chain.providers["scripted"].requests[1].messages[-1]
    assert last.role == "tool"
    assert last.content == ASK_USER_UNANSWERED.format(default="giữ nguyên hạn cũ")
    assert deps.store.get(conv.id).status == IDLE


async def test_a_question_with_no_default_still_tells_the_agent_to_decide(deps_factory):
    deps = deps_factory(script=[completion(tool_calls=(BARE,)), completion("tôi tự chọn")])
    conv = deps.store.create()
    await collect(run_turn(deps, conv.id, "chọn hộ"))
    later = datetime.now(UTC) + timedelta(seconds=deps.settings.approval_ttl_seconds + 1)

    await expire_overdue({deps.agent.id: deps}, ActivityHub(deps.store), now=later)

    last = deps.chain.providers["scripted"].requests[1].messages[-1]
    assert last.content == ASK_USER_UNANSWERED_NO_DEFAULT


async def test_the_tool_never_actually_runs_when_it_was_answered(deps_factory):
    """`ask_user` has a body only for the expired case. An answered question must be
    served from its stored row, or the person's words would be thrown away."""
    deps = deps_factory(script=[completion(tool_calls=(ASKING,)), completion("xong")])
    conv = deps.store.create()
    paused = await collect(run_turn(deps, conv.id, "xem hạn"))
    events = await collect(answer_question(deps, conv.id, paused[-1].approval_id, "không"))
    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert "Không ai trả lời" not in result.output and '"answer": "không"' in result.output
