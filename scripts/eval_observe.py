"""What one eval run did, read back from the JSON the server already serves: the
conversation's messages, the conversations it delegated to, the canvases it has, and the
approvals the client saw go by. Pure: nothing here talks to the server.

A turn starts at the message that holds the next text the eval sent. The server writes notes of
its own as the person's messages, the loop guard's above all, and those start no turn."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from eval_check import Ask, Call, Delegate, Observed
from eval_paste import Canvas

# Line 2 of a delegate result: what the handed-off task came to.
_OUTCOME = re.compile(r"outcome=(\S+)(?: reason=.*)?")


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
    *,
    sent: Sequence[str],
    unknown_cost_calls: int = 0,
    error: str = "",
    canvases: Sequence[Mapping[str, Any]] = (),
) -> Observed:
    """`conversation` and each of `children` are `GET /conversations/{id}`; `approvals` are
    the `approval_required` payloads the client answered, each with the `turn` it came in;
    `sent` the texts the eval sent, in order; `canvases` each canvas the conversation has, as
    `GET /artifacts/{id}` serves it. A conversation that does not hold every text sent fails
    the run, unless the run already failed."""
    messages = conversation.get("messages", [])
    turns = turn_numbers(messages, sent)
    held = turns[-1] if turns else 0
    if held < len(sent) and not error:
        error = f"the conversation holds {held} of the {len(sent)} messages the eval sent"
    turn_of_call: dict[str, int] = {}
    calls = list(_calls(messages, turns, str(conversation["agent_id"]), turn_of_call))
    outcomes = _outcomes(messages)
    for child in children:
        turn = turn_of_call.get(str(child.get("parent_call_id")), max(1, held))
        child_messages = child.get("messages", [])
        calls.extend(_calls(child_messages, [turn] * len(child_messages), str(child["agent_id"])))
    return Observed(
        reply=_reply(messages, turns),
        said=tuple(
            str(m["content"]) for m in messages if m["role"] == "assistant" and m.get("content")
        ),
        canvases=tuple(
            Canvas(str(c.get("title") or ""), str(c.get("content") or "")) for c in canvases
        ),
        tool_calls=tuple(calls),
        approvals=tuple(
            Ask(int(a["turn"]), str(a["name"]), dict(a.get("arguments") or {}))
            for a in approvals
            if a.get("kind", "tool") == "tool"
        ),
        delegates=tuple(
            Delegate(str(c["agent_id"]), outcomes.get(str(c.get("parent_call_id"))))
            for c in children
        ),
        spent_usd=spent_usd,
        unknown_cost_calls=unknown_cost_calls,
        error=error,
    )


def turn_numbers(messages: Sequence[Mapping[str, Any]], sent: Sequence[str]) -> list[int]:
    """The turn each message is in: how many of the texts in `sent` the conversation holds
    up to it, in order; 0 before the first."""
    turns, held = [], 0
    for message in messages:
        if held < len(sent) and message["role"] == "user" and message.get("content") == sent[held]:
            held += 1
        turns.append(held)
    return turns


def _calls(
    messages: Sequence[Mapping[str, Any]],
    turns: Sequence[int],
    agent: str,
    turn_of_call: dict[str, int] | None = None,
) -> Iterator[Call]:
    for message, turn in zip(messages, turns, strict=True):
        for call in message.get("tool_calls") or []:
            if turn_of_call is not None:
                turn_of_call[str(call["id"])] = turn
            yield Call(turn, agent, str(call["name"]), dict(call.get("arguments") or {}))


def _outcomes(messages: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """What each delegation came to, by the id of the call that made it. A result written
    before the outcome line existed has none, and its delegation reads as None."""
    found: dict[str, str] = {}
    for message in messages:
        lines = str(message.get("content") or "").split("\n", 2)
        if message["role"] == "tool" and len(lines) > 1 and (hit := _OUTCOME.fullmatch(lines[1])):
            found[str(message.get("tool_call_id"))] = hit.group(1)
    return found


def _reply(messages: Sequence[Mapping[str, Any]], turns: Sequence[int]) -> str:
    """The last thing the agent said in the last turn."""
    last = turns[-1] if turns else 0
    said = [
        str(message["content"])
        for message, turn in zip(messages, turns, strict=True)
        if turn == last and message["role"] == "assistant" and message.get("content")
    ]
    return said[-1] if said else ""
