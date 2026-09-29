"""What one eval run did, read back from the JSON the server already serves: the
conversation's messages, the conversations it delegated to, and the approvals the client saw
go by. Pure: nothing here talks to the server."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from eval_check import Ask, Call, Delegate, Observed


def child_ids(runs: Sequence[Mapping[str, Any]], conv_id: str) -> list[str]:
    """The other conversations of a run family, in the order they started."""
    ordered = sorted(runs, key=lambda run: run["started_at"])
    return list(
        dict.fromkeys(r["conversation_id"] for r in ordered if r["conversation_id"] != conv_id)
    )


def observe(
    conversation: Mapping[str, Any],
    children: Sequence[Mapping[str, Any]],
    approvals: Sequence[Mapping[str, Any]],
    spent_usd: float,
    unknown_cost_calls: int = 0,
    error: str = "",
) -> Observed:
    """`conversation` and each of `children` are `GET /conversations/{id}`; `approvals` are
    the `approval_required` payloads the client answered, each with the `turn` it came in."""
    messages = conversation.get("messages", [])
    turn_of_call: dict[str, int] = {}
    calls = list(_calls(messages, str(conversation["agent_id"]), turn_of_call))
    last_turn = max(1, sum(1 for m in messages if m["role"] == "user"))
    for child in children:
        turn = turn_of_call.get(str(child.get("parent_call_id")), last_turn)
        calls.extend(_calls(child.get("messages", []), str(child["agent_id"]), {}, fixed_turn=turn))
    return Observed(
        reply=_reply(messages),
        tool_calls=tuple(calls),
        approvals=tuple(
            Ask(int(a["turn"]), str(a["name"]), dict(a.get("arguments") or {}))
            for a in approvals
            if a.get("kind", "tool") == "tool"
        ),
        delegates=tuple(Delegate(str(c["agent_id"]), None) for c in children),
        spent_usd=spent_usd,
        unknown_cost_calls=unknown_cost_calls,
        error=error,
    )


def _calls(
    messages: Sequence[Mapping[str, Any]],
    agent: str,
    turn_of_call: dict[str, int],
    fixed_turn: int | None = None,
) -> Iterator[Call]:
    turn = 0
    for message in messages:
        if message["role"] == "user":
            turn += 1
        for call in message.get("tool_calls") or []:
            at = fixed_turn if fixed_turn is not None else turn
            turn_of_call[str(call["id"])] = at
            yield Call(at, agent, str(call["name"]), dict(call.get("arguments") or {}))


def _reply(messages: Sequence[Mapping[str, Any]]) -> str:
    """The last thing the agent said since the last thing it was told."""
    said = ""
    for message in messages:
        if message["role"] == "user":
            said = ""
        elif message["role"] == "assistant" and message.get("content"):
            said = str(message["content"])
    return said
