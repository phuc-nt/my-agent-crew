"""A turn that stopped to wait for a person, stored the way the loop stores one: the model's
call, the request it opened, and, once the request is closed, the tool message the turn is
told the outcome in. The words of that message are the loop's own."""

from __future__ import annotations

from my_agent_crew.agent.tool_calls import close_interrupted
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store.approvals import EXPIRED
from my_agent_crew.store.db import Store
from my_agent_crew.store.models import QUESTION, TOOL, Approval

ASK = ToolCall("q1", "ask_user", {"question": "Chạy hay bơi?"})
ASK_WITH_DEFAULT = ToolCall("q2", "ask_user", {"question": "Chạy hay bơi?", "default": "chạy"})
WRITE = ToolCall("w1", "workspace_write", {"path": "out.txt", "content": "ok"})


def waits_on(store: Store, conv_id: str, call: ToolCall) -> Approval:
    """The turn stops at `call`: a question when it asks the person, an approval otherwise."""
    stored = store.append(conv_id, Message(role="assistant", content="", tool_calls=(call,)))
    kind = QUESTION if call.name == "ask_user" else TOOL
    return store.approvals.create(conv_id, stored.id, call, kind=kind)


def nobody_answered(store: Store, conv_id: str, request: Approval) -> None:
    """The request ran out of time, and the turn is told so."""
    store.approvals.resolve(request.id, approve=False, status=EXPIRED)
    close_interrupted(store, conv_id)


def refused(store: Store, conv_id: str, request: Approval) -> None:
    """The person said no, and the turn is told so."""
    store.approvals.resolve(request.id, approve=False)
    close_interrupted(store, conv_id)


def answered(store: Store, conv_id: str, request: Approval, answer: str) -> None:
    """The person answered the question, and the turn is handed their words."""
    store.approvals.answer(request.id, answer)
    close_interrupted(store, conv_id)


def sent_again(store: Store, conv_id: str, call: ToolCall, result: str) -> None:
    """The model sends a call under an id it has used before, and the loop answers the new
    call with `result`: it ran, or it was told what became of the request the id once opened."""
    store.append(conv_id, Message(role="assistant", content="", tool_calls=(call,)))
    store.append(
        conv_id, Message(role="tool", content=result, tool_call_id=call.id, name=call.name)
    )
