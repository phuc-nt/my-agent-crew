"""A tool call id is only unique within the provider that made it up; before uuid ids
(`llm/openai_compat.py`) two different calls, even in two different conversations, could
carry the same bare id. An approval is keyed by `(conversation_id, tool_call_id)`, so a
second call reusing an id already approved for a different tool or different arguments in
the SAME conversation must not be let through on that stale decision — it is refused and
asked again under its own name, never silently run as whatever the old approval covered."""

from __future__ import annotations

from my_agent_crew.agent.events import ApprovalRequiredEvent, DoneEvent, ToolResultEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.resume import resolve_approval
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.texts import APPROVAL_CALL_MISMATCH
from my_agent_crew.tools import Tool
from tests.conftest import collect

WRITE = ToolCall("c1", "workspace_write", {"path": "out.txt", "content": "một"})
OTHER_WRITE = ToolCall("c1", "workspace_write", {"path": "out.txt", "content": "khác"})
SPY_CALL = ToolCall("c1", "spy", {})


def _spy_tool(seen: list[str]) -> Tool:
    async def run(args: dict) -> str:
        seen.append("ran")
        return "ok"

    return Tool(
        name="spy",
        description="",
        parameters={"type": "object"},
        run=run,
        requires_approval=True,
    )


async def test_a_reused_id_naming_a_different_tool_is_refused(deps_factory):
    seen: list[str] = []
    deps = deps_factory(
        script=[
            completion(tool_calls=(WRITE,)),
            completion("đã ghi"),
            completion(tool_calls=(SPY_CALL,)),
            completion("xong"),
        ],
        extra_tools=[_spy_tool(seen)],
    )
    conv = deps.store.create()
    paused = await collect(run_turn(deps, conv.id, "ghi file"))
    await collect(resolve_approval(deps, conv.id, paused[-1].approval_id, approve=True))

    resumed = await collect(run_turn(deps, conv.id, "gọi spy"))

    result = next(e for e in resumed if isinstance(e, ToolResultEvent))
    assert result.ok is False and result.output == APPROVAL_CALL_MISMATCH
    assert seen == []  # spy never ran either
    assert isinstance(resumed[-1], DoneEvent)


async def test_a_reused_id_naming_different_arguments_is_refused(deps_factory):
    deps = deps_factory(
        script=[
            completion(tool_calls=(WRITE,)),
            completion("đã ghi"),
            completion(tool_calls=(OTHER_WRITE,)),
            completion("xong"),
        ]
    )
    conv = deps.store.create()
    paused = await collect(run_turn(deps, conv.id, "ghi file"))
    await collect(resolve_approval(deps, conv.id, paused[-1].approval_id, approve=True))
    assert (deps.settings.workspace_dir / "out.txt").read_text() == "một"

    resumed = await collect(run_turn(deps, conv.id, "ghi lại"))

    result = next(e for e in resumed if isinstance(e, ToolResultEvent))
    assert result.ok is False and result.output == APPROVAL_CALL_MISMATCH
    assert (deps.settings.workspace_dir / "out.txt").read_text() == "một"  # unchanged


async def test_a_second_call_needing_approval_still_asks_with_a_fresh_id(deps_factory):
    """The mismatch guard must not swallow an ordinary second approval: a call with a new
    id, waiting on its own new approval, still pauses and is answered normally."""
    deps = deps_factory(
        script=[
            completion(tool_calls=(WRITE,)),
            completion("đã ghi"),
            completion(
                tool_calls=(
                    ToolCall("c2", "workspace_write", {"path": "two.txt", "content": "hai"}),
                ),
            ),
            completion("xong"),
        ]
    )
    conv = deps.store.create()
    paused = await collect(run_turn(deps, conv.id, "ghi file"))
    await collect(resolve_approval(deps, conv.id, paused[-1].approval_id, approve=True))

    resumed = await collect(run_turn(deps, conv.id, "ghi nữa"))

    assert isinstance(resumed[-1], ApprovalRequiredEvent)
    final = await collect(resolve_approval(deps, conv.id, resumed[-1].approval_id, approve=True))
    result = next(e for e in final if isinstance(e, ToolResultEvent))
    assert result.ok is True


async def test_a_matching_reused_id_still_runs_as_before(deps_factory):
    """The same call id, same tool, same arguments as an approved call: this is the
    ordinary always-allow / resumed-turn path, not a collision, and must keep working."""
    deps = deps_factory(script=[completion(tool_calls=(WRITE,)), completion("đã ghi")])
    conv = deps.store.create()
    paused = await collect(run_turn(deps, conv.id, "ghi file"))

    events = await collect(resolve_approval(deps, conv.id, paused[-1].approval_id, approve=True))

    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result.ok is True and result.output != APPROVAL_CALL_MISMATCH
    assert (deps.settings.workspace_dir / "out.txt").read_text() == "một"
