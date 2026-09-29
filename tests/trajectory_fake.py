"""A store written the way runs leave it: a run that began where its conversation stood,
and a delegation whose result opens with the line that names the child it opened."""

from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store import Store
from my_agent_crew.store.db import new_id, now_iso
from my_agent_crew.store.runs import DONE, RunRecord
from my_agent_crew.texts import DELEGATE_RESULT_HEADER


def run_from(store: Store, conv_id: str, after_seq: int, status: str = DONE) -> RunRecord:
    run = RunRecord(
        new_id(), "default", conv_id, "chat", "t", status, now_iso(), after_seq=after_seq
    )
    store.runs.save(run)
    return run


def child_of(store: Store, parent_id: str, call_id: str, said: str) -> str:
    """A child as `_run_child` leaves it: its own conversation and a run whose source names
    the conversation that delegated."""
    child = store.create(agent_id="coach", parent_call_id=call_id)
    store.append(child.id, Message(role="user", content="việc được giao"))
    store.append(child.id, Message(role="assistant", content=said), "fake", "echo")
    source = f"delegate:{parent_id}"
    store.runs.save(
        RunRecord(new_id(), "coach", child.id, source, "t", DONE, now_iso(), after_seq=0)
    )
    return child.id


def delegate_call(store: Store, conv_id: str, call_id: str, task: str) -> None:
    store.append(conv_id, Message(role="user", content=f"nhờ {task}"))
    call = ToolCall(call_id, DELEGATE_TOOL_NAME, {"agent": "coach", "task": task})
    store.append(conv_id, Message(role="assistant", tool_calls=(call,)), "fake", "echo")


def delegating_turn(store: Store, conv_id: str, call_id: str, task: str, said: str) -> str:
    """A turn that hands `task` to a child and gets back what it `said`; the child's id."""
    delegate_call(store, conv_id, call_id, task)
    child_id = child_of(store, conv_id, call_id, said)
    header = DELEGATE_RESULT_HEADER.format(conv_id=child_id, status="done", spent=0, steps=1)
    result = Message(
        role="tool",
        content=f"{header}\noutcome=done\n{task} xong",
        tool_call_id=call_id,
        name=DELEGATE_TOOL_NAME,
    )
    store.append(conv_id, result)
    return child_id
