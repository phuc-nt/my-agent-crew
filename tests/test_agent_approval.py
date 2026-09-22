"""Approval as a first-class event: pause, resume after approve/deny, autonomous bypass."""

import pytest

from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    DoneEvent,
    ToolResultEvent,
)
from my_agent_crew.agent.loop import ConversationBusy, run_turn
from my_agent_crew.agent.resume import resolve_approval
from my_agent_crew.agent.turn_context import JOB, WEB, set_turn_source, turn_source
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store.db import now_iso
from my_agent_crew.store.models import AWAITING_APPROVAL, IDLE
from my_agent_crew.store.runs import AWAITING, RunRecord
from my_agent_crew.texts import DENIED_TOOL
from my_agent_crew.tools import Tool
from tests.conftest import collect

WRITE = ToolCall("c1", "workspace_write", {"path": "out.txt", "content": "xin chào"})


async def test_write_pauses_for_approval(deps_factory):
    deps = deps_factory(script=[completion(tool_calls=(WRITE,)), completion("đã ghi")])
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, "ghi file"))
    assert isinstance(events[-1], ApprovalRequiredEvent)
    assert events[-1].name == "workspace_write"
    assert deps.store.get(conv.id).status == AWAITING_APPROVAL
    assert not (deps.settings.workspace_dir / "out.txt").exists()
    assert len(deps.chain.providers["scripted"].requests) == 1


async def test_approve_runs_tool_and_finishes(deps_factory):
    deps = deps_factory(script=[completion(tool_calls=(WRITE,)), completion("đã ghi")])
    conv = deps.store.create()
    paused = await collect(run_turn(deps, conv.id, "ghi file"))
    approval_id = paused[-1].approval_id
    events = await collect(resolve_approval(deps, conv.id, approval_id, approve=True))
    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result.ok and (deps.settings.workspace_dir / "out.txt").read_text() == "xin chào"
    assert isinstance(events[-1], DoneEvent)
    assert deps.store.get(conv.id).status == IDLE


async def test_deny_tells_the_model_and_does_not_write(deps_factory):
    deps = deps_factory(script=[completion(tool_calls=(WRITE,)), completion("thôi vậy")])
    conv = deps.store.create()
    paused = await collect(run_turn(deps, conv.id, "ghi file"))
    events = await collect(resolve_approval(deps, conv.id, paused[-1].approval_id, approve=False))
    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result.ok is False and result.output == DENIED_TOOL
    assert not (deps.settings.workspace_dir / "out.txt").exists()
    last = deps.chain.providers["scripted"].requests[1].messages[-1]
    assert last.role == "tool" and last.content == DENIED_TOOL
    assert isinstance(events[-1], DoneEvent)


async def test_new_message_while_awaiting_is_refused(deps_factory):
    deps = deps_factory(script=[completion(tool_calls=(WRITE,))])
    conv = deps.store.create()
    await collect(run_turn(deps, conv.id, "ghi file"))
    with pytest.raises(ConversationBusy):
        await collect(run_turn(deps, conv.id, "nữa"))


async def test_resolving_twice_is_rejected(deps_factory):
    deps = deps_factory(script=[completion(tool_calls=(WRITE,)), completion("ok")])
    conv = deps.store.create()
    paused = await collect(run_turn(deps, conv.id, "ghi"))
    await collect(resolve_approval(deps, conv.id, paused[-1].approval_id, True))
    with pytest.raises(KeyError):
        await collect(resolve_approval(deps, conv.id, paused[-1].approval_id, True))


async def test_autonomous_conversation_skips_approval(deps_factory):
    deps = deps_factory(script=[completion(tool_calls=(WRITE,)), completion("đã ghi")])
    conv = deps.store.create(autonomous=True)
    events = await collect(run_turn(deps, conv.id, "ghi file"))
    assert not any(isinstance(e, ApprovalRequiredEvent) for e in events)
    assert (deps.settings.workspace_dir / "out.txt").read_text() == "xin chào"
    assert isinstance(events[-1], DoneEvent)


async def test_mixed_calls_run_safe_ones_before_pausing(deps_factory):
    calls = (ToolCall("c0", "workspace_list", {}), WRITE)
    deps = deps_factory(script=[completion(tool_calls=calls), completion("ok")])
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, "go"))
    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert [r.name for r in results] == ["workspace_list"]
    assert isinstance(events[-1], ApprovalRequiredEvent)
    resumed = await collect(resolve_approval(deps, conv.id, events[-1].approval_id, True))
    assert [e.name for e in resumed if isinstance(e, ToolResultEvent)] == ["workspace_write"]


async def test_resuming_after_approval_keeps_the_source_of_the_original_turn(deps_factory):
    """The approval arrives from the web, but the turn is still the job that asked for it:
    a memory write approved here must still be judged as unattended."""
    seen: list[str] = []

    async def spy(args):
        seen.append(turn_source())
        return "ok"

    tool = Tool(
        name="spy", description="", parameters={"type": "object"}, run=spy, requires_approval=True
    )
    deps = deps_factory(
        script=[completion(tool_calls=(ToolCall("c1", "spy", {}),)), completion("xong")],
        extra_tools=[tool],
    )
    conv = deps.store.create()
    deps.store.runs.save(
        RunRecord(
            id="r1",
            agent_id=deps.profile.id,
            conversation_id=conv.id,
            source="job:coach/brief",
            title="brief",
            status=AWAITING,
            started_at=now_iso(),
        )
    )
    paused = await collect(run_turn(deps, conv.id, "chạy", source="job:coach/brief"))
    assert seen == []

    set_turn_source(WEB)
    await collect(resolve_approval(deps, conv.id, paused[-1].approval_id, approve=True))
    assert seen == [JOB]


async def test_always_allow_lets_the_same_tool_run_without_asking_again(deps_factory):
    script = [
        completion(tool_calls=(WRITE,)),
        completion("đã ghi"),
        completion(tool_calls=(WRITE,)),
        completion("ghi lại rồi"),
    ]
    deps = deps_factory(script=script)
    conv = deps.store.create()
    paused = await collect(run_turn(deps, conv.id, "ghi file"))
    assert paused[-1].expires_at  # the request carries its deadline
    events = await collect(
        resolve_approval(deps, conv.id, paused[-1].approval_id, approve=True, always=True)
    )
    assert isinstance(events[-1], DoneEvent)
    assert deps.store.get(conv.id).auto_approve == ("workspace_write",)

    again = await collect(run_turn(deps, conv.id, "ghi nữa"))
    assert not any(isinstance(e, ApprovalRequiredEvent) for e in again)
    assert [e.name for e in again if isinstance(e, ToolResultEvent)] == ["workspace_write"]
    assert isinstance(again[-1], DoneEvent)


async def test_always_on_a_denial_allows_nothing(deps_factory):
    deps = deps_factory(script=[completion(tool_calls=(WRITE,)), completion("thôi")])
    conv = deps.store.create()
    paused = await collect(run_turn(deps, conv.id, "ghi"))
    await collect(resolve_approval(deps, conv.id, paused[-1].approval_id, False, always=True))
    assert deps.store.get(conv.id).auto_approve == ()


async def test_the_shell_ask_list_still_pauses_an_always_allowed_tool(deps_factory):
    """Always-allow is the person's shortcut; the ask list is the guard above it."""
    call = ToolCall("c1", "shell_run", {"command": "sudo rm -rf /tmp/x"})
    deps = deps_factory(script=[completion(tool_calls=(call,))])
    conv = deps.store.create()
    deps.store.update(conv.id, auto_approve=("shell_run",))
    events = await collect(run_turn(deps, conv.id, "dọn"))
    assert isinstance(events[-1], ApprovalRequiredEvent) and events[-1].reason
