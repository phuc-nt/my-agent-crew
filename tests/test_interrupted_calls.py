"""Tool calls an earlier turn left without a result — it was stopped, or the server went
down mid-call — are closed before a new message is written after them, and never run again:
whether they ran the first time is unknown. A call whose decision is known closes with it."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from my_agent_crew import texts
from my_agent_crew.agent.loop import ConversationBusy, run_turn
from my_agent_crew.agent.tool_calls import close_interrupted
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store import Store
from my_agent_crew.store.approvals import DENIED, EXPIRED
from my_agent_crew.store.models import AWAITING_APPROVAL, QUESTION
from my_agent_crew.tools.ask_user import ASK_USER_TOOL_NAME, answer_result, unanswered_result
from tests.conftest import collect
from tests.queue_helpers import SlowTool

SLOW_1, SLOW_2 = ToolCall("c1", "slow", {}), ToolCall("c2", "slow", {})
ASK = ToolCall("q1", ASK_USER_TOOL_NAME, {"question": "A hay B?", "options": ["A", "B"]})


def left_open(store: Store, conv_id: str, *calls: ToolCall) -> int:
    """A turn that asked for these calls and stopped before any result was written."""
    store.append(conv_id, Message(role="user", content="làm đi"))
    return store.append(conv_id, Message(role="assistant", tool_calls=calls)).id


def log(store: Store, conv_id: str) -> list[tuple[str, str | None, str]]:
    return [
        (m.message.role, m.message.tool_call_id, m.message.content) for m in store.history(conv_id)
    ]


def assert_every_call_answered(messages: Sequence[Message]) -> None:
    """The order a provider accepts: each call's result before anything else is said."""
    open_ids: set[str] = set()
    for message in messages:
        if message.role == "tool":
            open_ids.discard(message.tool_call_id or "")
            continue
        assert not open_ids, f"{message.role} message before results for {open_ids}"
        open_ids = {call.id for call in message.tool_calls}
    assert not open_ids


@pytest.fixture
def rigged(deps_factory):
    slow = SlowTool()
    slow.release.set()
    provider = ScriptedProvider([completion("đã hiểu")])
    deps = deps_factory(providers={"scripted": provider}, extra_tools=[slow.tool])
    return deps, provider, slow


async def test_a_new_message_closes_the_calls_left_without_a_result(rigged):
    deps, provider, slow = rigged
    conv = deps.store.create()
    left_open(deps.store, conv.id, SLOW_1, SLOW_2)
    await collect(run_turn(deps, conv.id, "tin mới"))
    assert log(deps.store, conv.id)[1:] == [
        ("assistant", None, ""),
        ("tool", "c1", texts.INTERRUPTED_TOOL),
        ("tool", "c2", texts.INTERRUPTED_TOOL),
        ("user", None, "tin mới"),
        ("assistant", None, "đã hiểu"),
    ]
    assert slow.runs == 0
    [request] = provider.requests
    assert_every_call_answered(request.messages)
    assert request.messages[-1] == Message(role="user", content="tin mới")


async def test_an_approved_call_that_never_reported_back_is_not_run_again(rigged):
    deps, _, slow = rigged
    conv = deps.store.create()
    message_id = left_open(deps.store, conv.id, SLOW_1)
    approval = deps.store.approvals.create(conv.id, message_id, SLOW_1)
    deps.store.approvals.resolve(approval.id, approve=True)
    await collect(run_turn(deps, conv.id, "tin mới"))
    assert ("tool", "c1", texts.INTERRUPTED_TOOL) in log(deps.store, conv.id)
    assert slow.runs == 0


@pytest.mark.parametrize(
    ("status", "output"), [(DENIED, texts.DENIED_TOOL), (EXPIRED, texts.EXPIRED_TOOL)]
)
async def test_a_refused_call_closes_with_its_refusal(rigged, status, output):
    deps, _, slow = rigged
    conv = deps.store.create()
    message_id = left_open(deps.store, conv.id, SLOW_1)
    approval = deps.store.approvals.create(conv.id, message_id, SLOW_1)
    deps.store.approvals.resolve(approval.id, approve=False, status=status)
    await collect(run_turn(deps, conv.id, "tin mới"))
    tool_results = [entry for entry in log(deps.store, conv.id) if entry[0] == "tool"]
    assert tool_results == [("tool", "c1", output)]
    assert slow.runs == 0


async def test_a_question_closes_with_its_answer_or_its_default(rigged):
    deps, _, _ = rigged
    answered, lapsed = deps.store.create(), deps.store.create()
    for conv in (answered, lapsed):
        message_id = left_open(deps.store, conv.id, ASK)
        question = deps.store.approvals.create(
            conv.id, message_id, ASK, kind=QUESTION, options=["A", "B"]
        )
        if conv is answered:
            deps.store.approvals.answer(question.id, "B")
        else:
            deps.store.approvals.resolve(question.id, approve=False, status=EXPIRED)
        close_interrupted(deps.store, conv.id)
    assert log(deps.store, answered.id)[-1] == ("tool", "q1", answer_result("B"))
    assert log(deps.store, lapsed.id)[-1] == ("tool", "q1", unanswered_result(ASK.arguments))


async def test_a_call_still_waiting_on_a_person_stays_open(rigged):
    deps, provider, _ = rigged
    conv = deps.store.create()
    message_id = left_open(deps.store, conv.id, SLOW_1)
    deps.store.approvals.create(conv.id, message_id, SLOW_1)
    deps.store.update(conv.id, status=AWAITING_APPROVAL)
    before = log(deps.store, conv.id)
    close_interrupted(deps.store, conv.id)
    with pytest.raises(ConversationBusy):
        await collect(run_turn(deps, conv.id, "tin mới"))
    assert log(deps.store, conv.id) == before and provider.requests == []


async def test_closing_is_a_no_op_when_every_call_has_its_result(rigged):
    deps, _, _ = rigged
    conv = deps.store.create()
    left_open(deps.store, conv.id, SLOW_1)
    deps.store.append(conv.id, Message(role="tool", content="xong", tool_call_id="c1", name="slow"))
    before = log(deps.store, conv.id)
    close_interrupted(deps.store, conv.id)
    close_interrupted(deps.store, deps.store.create().id)  # nothing said yet
    assert log(deps.store, conv.id) == before
