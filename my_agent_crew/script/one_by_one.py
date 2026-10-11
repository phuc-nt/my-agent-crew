"""A batch with a call that changes things, made one call at a time in the order written.

Every call of a batch is judged before the first is made (`nested.py`): a batch with a call
the script may not make makes none of its calls. For calls made one after another that
first look cannot be the last. What one call leaves behind may change what the approval
gate says of the next, and the person may take back what they allowed while the batch runs.
So each call after the first is judged again as its turn comes, as a call the script wrote
on a line of its own is. One refused then ends the script there: what ran before it ran,
and is kept.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from my_agent_crew import texts_script as t
from my_agent_crew.script.replies import Answer
from my_agent_crew.tools.registry import Tool

# One call of a batch: the tool it names, the call as written, and its number in the script.
Asked = tuple[Tool | None, tuple[str, dict[str, Any]], int]


async def one_by_one(
    asked: Sequence[Asked],
    refusal: Callable[[Tool | None, dict[str, Any]], str | None],
    one: Callable[[Tool | None, str, dict[str, Any], int], Awaitable[Answer]],
) -> list[Answer]:
    """The answers in the order written. `refusal` says why a call may not be made now,
    and `one` makes it."""
    answers: list[Answer] = []
    ended = False
    for place, (tool, (name, arguments), number) in enumerate(asked):
        # The first was judged a moment ago, and nothing was made since.
        why = refusal(tool, arguments) if place and not ended else None
        if ended:
            answers.append(Answer(False, t.SCRIPT_BATCH_NOT_RUN))
        elif why is not None:
            ended = True
            answers.append(Answer(False, why, halt=True))
        else:
            answers.append(await one(tool, name, arguments, number))
    return answers
