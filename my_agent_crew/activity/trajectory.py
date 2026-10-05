"""A run written out whole, for a person debugging it or a case built from it: the run's
record, the messages it wrote into its conversation, each with the canvas note and the
memory it was read after, and what it delegated.

Unlike the conversation export this carries every tool call's arguments and result, so
whatever a tool touched comes along. Secrets are covered on the way out, long results are
cut unless the whole is asked for, and both formats open with a notice to check before
sharing. `trajectory_markdown` writes the same data out for a person to read.
"""

from __future__ import annotations

import re
from typing import Any

from my_agent_crew import texts
from my_agent_crew.activity.redact import redact_tree
from my_agent_crew.agent.turn_context import DELEGATE
from my_agent_crew.agent.turn_notes import render
from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME
from my_agent_crew.store import Conversation, Store, StoredMessage
from my_agent_crew.store.runs import RunRecord

RESULT_LIMIT = 2000
BY_SEQ, BY_TIME, NO_CONVERSATION = "by_seq", "by_time", "none"
# The first line of every delegate result, the one the web card reads too.
_NAMED_CHILD = re.compile(r"conversation=(\S+) status=")


def build(
    store: Store, run: RunRecord, secrets: list[str] | None = None, full: bool = False
) -> dict[str, Any]:
    said, how = _slice(store, run)
    data = {
        "notice": texts.TRAJECTORY_NOTICE,
        "run": run.to_dict(),
        "slice": how,
        "messages": [_message(m) for m in said],
        "children": _children(store, run, said),
    }
    # Covered before cutting: a cut through a secret would leave half of it in the file.
    data = redact_tree(data, secrets or [])
    if not full:
        for holder in [data, *data["children"]]:
            for message in holder["messages"]:
                _cut(message)
    return data


def _slice(store: Store, run: RunRecord) -> tuple[list[StoredMessage], str]:
    conv_id = run.conversation_id
    if conv_id is None:
        return [], NO_CONVERSATION
    if run.after_seq is None:
        return store.messages.stamped_between(conv_id, run.started_at, run.finished_at), BY_TIME
    return store.messages.of_run(conv_id, run.id, run.after_seq, run.started_at), BY_SEQ


def _children(store: Store, run: RunRecord, said: list[StoredMessage]) -> list[dict[str, Any]]:
    """What this run delegated. An answered call names its child on the first line of its
    result. A call still waiting is matched by its id, which a provider that sends none
    repeats as `call_0` in every turn of every conversation, so that child must also have
    been opened while this run went on. Either way it counts only when its own run names
    this conversation as the one that delegated it."""
    named: list[str] = []
    answered: set[str | None] = set()
    for stored in said:
        message = stored.message
        if message.role == "tool" and message.name == DELEGATE_TOOL_NAME:
            answered.add(message.tool_call_id)
            if found := _NAMED_CHILD.match(message.content):
                named.append(found.group(1))
    waiting = tuple(
        call.id
        for stored in said
        for call in stored.message.tool_calls
        if call.name == DELEGATE_TOOL_NAME and call.id not in answered
    )
    opened: list[Conversation] = []
    for child_id in named:
        try:
            opened.append(store.get(child_id))
        except KeyError:  # deleted since; its messages went with it
            continue
    opened += [child for child in store.children_of(waiting) if _opened_during(child, run)]
    source = f"{DELEGATE}:{run.conversation_id}"
    return [
        {
            "conversation_id": child.id,
            "agent_id": child.agent_id,
            "tool_call_id": child.parent_call_id,
            "messages": [_message(m) for m in store.history(child.id)],
        }
        for child in {child.id: child for child in opened}.values()
        if store.runs.recent(limit=1, conversation_ids=[child.id], source=source)
    ]


def _opened_during(child: Conversation, run: RunRecord) -> bool:
    return run.started_at <= child.created_at and (
        run.finished_at is None or child.created_at <= run.finished_at
    )


def _message(stored: StoredMessage) -> dict[str, Any]:
    message = stored.message
    calls = [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in message.tool_calls]
    data: dict[str, Any] = {
        "seq": stored.seq,
        "role": message.role,
        "content": message.content,
        "tool_calls": calls,
        "tool_call_id": message.tool_call_id,
        "name": message.name,
        "provider": stored.provider,
        "model": stored.model,
        "cost_usd": stored.cost_usd,
        "created_at": stored.created_at,
    }
    if stored.context:
        data["context"] = stored.context
    # What the model read in front of the message, as it read it.
    if told := render(stored.turn_notes):
        data["turn_notes"] = told
    return data


def _cut(message: dict[str, Any]) -> None:
    """Only tool results: what the agent said is what the person read, and stays whole."""
    content = message["content"]
    if message["role"] == "tool" and len(content) > RESULT_LIMIT:
        message["content"] = content[:RESULT_LIMIT] + texts.TRAJECTORY_CUT.format(
            total=len(content)
        )
