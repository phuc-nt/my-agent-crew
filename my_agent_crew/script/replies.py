"""What the parent answers when the process that runs a script asks for something.

The process asks one of three things, each as one JSON line: a tool call, several calls made
together, or a question (what it may call, what it kept, what a model makes of a text). Each
is answered with one line, and in each the answer is the caller's to give, since the caller
holds the tools. A question about the tools is answered at once; one put to a model is
waited for, as a tool call is. A line that is none of these, or is shaped wrongly, is not
answered: the process has stopped making sense, and `runner.py` ends it. The calls
themselves are never looked into here beyond their shape; what a script may call is for the
caller to say.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any

from my_agent_crew import texts_script as t
from my_agent_crew.script.limits import MAX_BATCH, Halt, ScriptError


@dataclass(frozen=True)
class Answer:
    """What one tool call of a script came to. `halt` ends the script there, uncatchable:
    it is for a call the script may not make at all, not for one that failed."""

    ok: bool
    output: str
    halt: bool = False


Calls = list[tuple[str, dict[str, Any]]]
CallTool = Callable[[str, dict[str, Any]], Awaitable[Answer]]
# Makes the calls of a batch and answers each, in the order given. `ScriptError` refuses the
# batch as a whole, which the script may catch; the answers are as many as the calls.
CallMany = Callable[[Calls], Awaitable[list[Answer]]]
# Answers a question of the script's: a value, or `ScriptError` to refuse. What it hands back
# may be the value or something to wait on for it; `Halt` ends the script there instead.
Lookup = Callable[[str, dict[str, Any]], Any]


def no_lookups(kind: str, arguments: dict[str, Any]) -> Any:
    raise ScriptError(t.SCRIPT_NO_LOOKUPS)


async def no_batches(calls: Calls) -> list[Answer]:
    raise ScriptError(t.SCRIPT_NO_BATCHES)


def _pair(item: Any, first: str) -> tuple[str, dict[str, Any]] | None:
    """What a call or a lookup is written as: its name (a lookup's kind) and its arguments."""
    if type(item) is not dict:
        return None
    name, arguments = item.get(first), item.get("arguments")
    return (name, arguments) if type(name) is str and type(arguments) is dict else None


async def _looked_up(lookup: Lookup, kind: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """A question answered where it stands is answered as it was before any had to be
    waited for; one that must be waited for is, and comes to the same three ends."""
    try:
        answer = lookup(kind, arguments)
        if inspect.isawaitable(answer):
            answer = await answer
    except ScriptError as refused:
        return {"failed": str(refused)}
    except Halt as ended:
        return {"halted": str(ended)}
    return {"answer": answer}


def _batch(raw: Any) -> Calls | None:
    """The calls of a batch as the process wrote them. It holds the process to what it was
    told: between one call and `MAX_BATCH`, each with a name and arguments."""
    if type(raw) is not list or not 0 < len(raw) <= MAX_BATCH:
        return None
    calls: Calls = []
    for item in raw:
        pair = _pair(item, "name")
        if pair is None:
            return None
        calls.append(pair)
    return calls


async def _batched(calls: Calls, many: CallMany) -> dict[str, Any]:
    try:
        answers = await many(calls)
    except ScriptError as refused:
        return {"failed": str(refused)}
    return {"answers": [asdict(answer) for answer in answers]}


async def reply(
    message: Any, call: CallTool, many: CallMany, lookup: Lookup
) -> dict[str, Any] | None:
    """The line to send back for a message of the process, or None when it is not one that
    can be answered. Only the shape is judged before the caller is asked: whatever `call`,
    `many` and `lookup` raise is not the process's doing."""
    if type(message) is not dict:
        return None
    if "ask" in message:
        asked = _pair(message["ask"], "kind")
        return None if asked is None else await _looked_up(lookup, *asked)
    if "calls" in message:
        calls = _batch(message["calls"])
        return None if calls is None else await _batched(calls, many)
    one = _pair(message.get("call"), "name")
    return None if one is None else asdict(await call(*one))
