"""The agent is told what a person decided on a call it waited for, and where."""

from dataclasses import replace

from my_agent_crew.agent.decision_note import delegate_reason, refusal_text, with_approval_note
from my_agent_crew.agent.events import ToolResultEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.resume import answer_question, resolve_approval
from my_agent_crew.agent.turn_context import TELEGRAM
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store.approvals import APPROVED, DENIED, EXPIRED
from my_agent_crew.store.models import Approval
from my_agent_crew.texts import DENIED_TOOL, EXPIRED_TOOL
from tests.conftest import collect

WRITE = ToolCall("c1", "workspace_write", {"path": "out.txt", "content": "xin chào"})
ASK = ToolCall("q1", "ask_user", {"question": "Màu gì?", "options": ["Đỏ", "Xanh"]})


def decided(status: str, via: str = "") -> Approval:
    approval = Approval("a1", "c1", 1, "t1", "shell_run", {}, status, "2026-11-01T08:00:00")
    return replace(approval, decided_via=via)


async def paused(deps, call: ToolCall = WRITE):
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, "làm đi"))
    return conv, events[-1].approval_id


async def test_an_approved_call_says_under_its_result_that_a_person_let_it_run(deps_factory):
    deps = deps_factory(script=[completion(tool_calls=(WRITE,)), completion("đã ghi")])
    conv, approval_id = await paused(deps)
    events = await collect(resolve_approval(deps, conv.id, approval_id, True, via=TELEGRAM))
    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result.ok
    assert result.output.endswith("người dùng đã DUYỆT trên Telegram rồi nó mới chạy.)")
    told = deps.chain.providers["scripted"].requests[1].messages[-1].content
    assert "DUYỆT trên Telegram" in told
    assert deps.store.approvals.get(approval_id).decided_via == TELEGRAM


async def test_a_denial_says_where_the_person_said_no(deps_factory):
    deps = deps_factory(script=[completion(tool_calls=(WRITE,)), completion("thôi")])
    conv, approval_id = await paused(deps)
    events = await collect(resolve_approval(deps, conv.id, approval_id, False, via=TELEGRAM))
    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result.output == f"{DENIED_TOOL} Người dùng đã bấm từ chối trên Telegram."


async def test_an_answer_keeps_where_it_came_from(deps_factory):
    deps = deps_factory(script=[completion(tool_calls=(ASK,)), completion("Đỏ nhé")])
    conv, approval_id = await paused(deps, ASK)
    await collect(answer_question(deps, conv.id, approval_id, "Đỏ", via=TELEGRAM))
    assert deps.store.approvals.get(approval_id).decided_via == TELEGRAM


def test_the_words_keep_their_openings_and_stay_quiet_when_nothing_is_known():
    assert refusal_text(decided(DENIED)) == DENIED_TOOL
    assert refusal_text(decided(EXPIRED, "chat")) == EXPIRED_TOOL, "nobody decides an expiry"
    assert refusal_text(decided(DENIED, "chat")).startswith(DENIED_TOOL)
    assert with_approval_note("ok", None) == "ok"
    assert with_approval_note("ok", decided(DENIED, "chat")) == "ok"
    note = with_approval_note("", decided(APPROVED))
    assert note.startswith("(") and "  " not in note


def test_a_blocked_child_tells_a_refusal_from_a_lapse():
    assert delegate_reason(decided(DENIED, TELEGRAM)) == (
        "người dùng từ chối duyệt shell_run trên Telegram"
    )
    assert delegate_reason(decided(DENIED)) == "người dùng từ chối duyệt shell_run"
    assert delegate_reason(decided(EXPIRED)) == "shell_run hết hạn chờ duyệt, không ai trả lời"
