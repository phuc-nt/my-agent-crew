"""A run written out whole, for a person debugging it or a case built from it: the run's
record, the messages it wrote into its conversation, and what it delegated.

Unlike the conversation export this carries every tool call's arguments and result, so
whatever a tool touched comes along. Secrets are covered on the way out, long results are
cut unless the whole is asked for, and both formats open with a notice to check before
sharing.
"""

from __future__ import annotations

import json
import re
from typing import Any

from my_agent_crew import texts
from my_agent_crew.activity.redact import redact_tree
from my_agent_crew.agent.turn_context import DELEGATE
from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME
from my_agent_crew.store import Store, StoredMessage
from my_agent_crew.store.runs import RunRecord

RESULT_LIMIT = 2000
BY_SEQ, BY_TIME, NO_CONVERSATION = "by_seq", "by_time", "none"


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
    """What this run delegated. A call id alone is no proof: a provider that sends none gets
    the same `call_0` in every conversation, so a child counts only when its own run names
    this conversation as the one that delegated it."""
    called = tuple(
        call.id
        for stored in said
        for call in stored.message.tool_calls
        if call.name == DELEGATE_TOOL_NAME
    )
    source = f"{DELEGATE}:{run.conversation_id}"
    return [
        {
            "conversation_id": child.id,
            "agent_id": child.agent_id,
            "tool_call_id": child.parent_call_id,
            "messages": [_message(m) for m in store.history(child.id)],
        }
        for child in store.children_of(called)
        if store.runs.recent(limit=1, conversation_ids=[child.id], source=source)
    ]


def _message(stored: StoredMessage) -> dict[str, Any]:
    message = stored.message
    calls = [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in message.tool_calls]
    return {
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


def _cut(message: dict[str, Any]) -> None:
    """Only tool results: what the agent said is what the person read, and stays whole."""
    content = message["content"]
    if message["role"] == "tool" and len(content) > RESULT_LIMIT:
        message["content"] = content[:RESULT_LIMIT] + texts.TRAJECTORY_CUT.format(
            total=len(content)
        )


def to_markdown(data: dict[str, Any]) -> str:
    run = data["run"]
    lines = [texts.TRAJECTORY_TITLE.format(title=run["title"] or run["id"]), ""]
    lines += [f"> {data['notice']}", "", *_facts(run, data["slice"]), ""]
    if data["messages"] or not run["steps"]:
        lines += [texts.TRAJECTORY_MESSAGES, "", *_blocks(data["messages"])]
    else:
        lines += [texts.TRAJECTORY_STEPS, "", *(_step(step) for step in run["steps"]), ""]
    for child in data["children"]:
        heading = texts.TRAJECTORY_CHILD.format(
            agent=child["agent_id"],
            conversation=child["conversation_id"],
            call=child["tool_call_id"],
        )
        lines += [heading, "", *_blocks(child["messages"])]
    return "\n".join(lines).rstrip() + "\n"


def _facts(run: dict[str, Any], how: str) -> list[str]:
    spent = f"${run['spent_usd']:.4f}"
    if run["unknown_cost_calls"]:
        spent += texts.TRAJECTORY_UNKNOWN_COST.format(count=run["unknown_cost_calls"])
    conversation = run["conversation_id"]
    facts = {
        "id": f"`{run['id']}`",
        "agent_id": run["agent_id"],
        "source": f"`{run['source']}`",
        "status": f"`{run['status']}`",
        "summary": _one_line(run["summary"]),
        "started_at": run["started_at"],
        "finished_at": run["finished_at"],
        "steps": str(len(run["steps"])),
        "spent_usd": spent,
        "conversation_id": f"`{conversation}`" if conversation else "",
        "slice": texts.TRAJECTORY_SLICES[how],
    }
    labels = texts.TRAJECTORY_FACT_LABELS
    return [f"- {labels[key]}: {value}" for key, value in facts.items() if value]


def _blocks(messages: list[dict[str, Any]]) -> list[str]:
    if not messages:
        return [texts.TRAJECTORY_NO_MESSAGES, ""]
    lines: list[str] = []
    for message in messages:
        lines += [_heading(message), ""]
        if message["role"] == "tool":
            lines += [_fenced(message["content"]), ""]
            continue
        if message["content"]:
            lines += [message["content"], ""]
        for call in message["tool_calls"]:
            arguments = json.dumps(call["arguments"], ensure_ascii=False, indent=2)
            lines += [texts.TRAJECTORY_CALL.format(name=call["name"]), ""]
            lines += [_fenced(arguments, "json"), ""]
    return lines


def _heading(message: dict[str, Any]) -> str:
    parts = [f"#{message['seq']}", texts.TRAJECTORY_ROLES.get(message["role"], message["role"])]
    if message["role"] == "tool" and message["name"]:
        parts.append(f"`{message['name']}`")
    if message["model"]:
        provider = message["provider"]
        parts.append(f"{provider}/{message['model']}" if provider else message["model"])
    return "### " + " · ".join(parts)


def _fenced(text: str, language: str = "") -> str:
    """A fence longer than any backtick run inside, so the text cannot close it early."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{text}\n{fence}"


def _step(step: dict[str, Any]) -> str:
    shown = (f"{key}: {value}" for key, value in step.items() if value not in (None, "", []))
    return "- " + _one_line(" · ".join(shown))


def _one_line(text: str) -> str:
    return " ".join(str(text).split())
