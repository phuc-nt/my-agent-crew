"""Crash resume: the message log is the state, so a restart finishes unpaid work
instead of redoing paid steps."""

from my_agent_crew.agent.events import DoneEvent, ToolResultEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from tests.conftest import collect, make_deps


async def test_pending_tool_calls_are_settled_on_next_turn(settings, store):
    deps = make_deps(settings, store, script=[completion("kết quả đây")])
    conv = store.create()
    store.append(conv.id, Message(role="user", content="liệt kê"))
    store.append(
        conv.id,
        Message(role="assistant", tool_calls=(ToolCall("c1", "workspace_list", {}),)),
        provider="p",
        model="m",
        cost_usd=0.01,
    )
    # process died here: tool never ran, no result stored
    events = await collect(run_turn(deps, conv.id, None))
    assert isinstance(events[0].__class__, type)
    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result.tool_call_id == "c1" and result.ok
    assert isinstance(events[-1], DoneEvent)
    roles = [m.message.role for m in store.history(conv.id)]
    assert roles == ["user", "assistant", "tool", "assistant"]


async def test_partially_settled_calls_only_run_the_missing_one(settings, store):
    deps = make_deps(settings, store, script=[completion("xong")])
    conv = store.create()
    store.append(conv.id, Message(role="user", content="go"))
    calls = (ToolCall("c1", "workspace_list", {}), ToolCall("c2", "workspace_list", {}))
    store.append(conv.id, Message(role="assistant", tool_calls=calls))
    store.append(conv.id, Message(role="tool", content="old", tool_call_id="c1", name="x"))
    events = await collect(run_turn(deps, conv.id, None))
    ran = [e.tool_call_id for e in events if isinstance(e, ToolResultEvent)]
    assert ran == ["c2"]


async def test_resuming_a_finished_conversation_is_a_noop(settings, store):
    deps = make_deps(settings, store, script=[completion("should not be called")])
    conv = store.create()
    store.append(conv.id, Message(role="user", content="hi"))
    store.append(conv.id, Message(role="assistant", content="done already"))
    events = await collect(run_turn(deps, conv.id, None))
    assert isinstance(events[-1], DoneEvent) and len(events) == 1
    assert deps.chain.providers["scripted"].requests == []


async def test_pending_approval_survives_restart(settings, store):
    write = ToolCall("c1", "workspace_write", {"path": "a.txt", "content": "x"})
    deps = make_deps(settings, store, script=[completion(tool_calls=(write,)), completion("ok")])
    conv = store.create()
    paused = await collect(run_turn(deps, conv.id, "ghi"))
    approval_id = paused[-1].approval_id
    # "restart": brand-new deps over the same store
    fresh = make_deps(settings, store, script=[completion("ok")])
    again = await collect(run_turn(fresh, conv.id, None))
    assert again[-1].approval_id == approval_id
    assert fresh.chain.providers["scripted"].requests == []
