"""The fence a browser tool puts around whatever a page had a say in, and the sizes that keep
it whole.

What a page has a say in stands between two fence lines made for this one answer, under a
line saying it is data. The registry cuts an answer over the agent's cap from its end, where
the closing line stands; it may write the whole of it to a file that is read back in slices
with no fence, or hand it to a model to shorten. So no answer of a browser tool is longer
than the cap less the widest mark of a cut: a tool sizes what it fences, and an answer that
still has no room says so in place of the page."""

from __future__ import annotations

import re
import secrets

from my_agent_crew import texts_browser_fence as f
from my_agent_crew.texts import OUTPUT_TRUNCATED, TOOL_FAILED
from my_agent_crew.tools.registry import ToolError

ERROR_CHARS = 200
# Left for the notes written once a page's own text is sized.
NOTE_ROOM = 300
# The registry cuts an answer that a hook's note pushed past the cap, and marks the cut. An
# answer leaves room for the widest such mark, so the cut never reaches its closing line.
CUT_ROOM = len(OUTPUT_TRUNCATED.format(dropped=10**9))
# What the registry writes before the words of a tool that failed.
FAILED_ROOM = len(TOOL_FAILED.format(error=""))
# Chromium's own code, where it starts the error of a navigation: the one part of the
# line no page wrote. What a page throws while it is read starts with another call.
NET_CODE = re.compile(r"Page\.goto: (net::ERR_[A-Z0-9_]{1,40})(?: at |$)")


def first_line(exc: BaseException) -> str:
    """The first line of an error: what follows it is a log that quotes the page."""
    lines = str(exc).strip().splitlines()
    return (lines[0] if lines else type(exc).__name__)[:ERROR_CHARS]


def kind_of(exc: BaseException) -> str:
    """What is said of an error of the browser outside a fence: Chromium's code when the error
    starts with one, else the name of its class. The rest of the line may quote the page."""
    code = NET_CODE.match(first_line(exc))
    return code.group(1) if code else type(exc).__name__


def fence() -> tuple[str, str, str]:
    """The line that says what the fence is, and the two lines of the fence itself. The
    number in them is made anew each time: a page cannot write a line that closes it."""
    nonce = secrets.token_hex(8)
    opening, closing = f.PAGE_OPEN.format(nonce=nonce), f.PAGE_CLOSE.format(nonce=nonce)
    return f.PAGE_FENCE.format(opening=opening, closing=closing), opening, closing


def fenced(body: str) -> str:
    said, opening, closing = fence()
    return "\n".join([said, opening, body, closing])


def room(limit: int, *written: str) -> int:
    """What is left under the cap for a page's own text, beside everything else an answer
    holds, its fence and the notes written afterwards. Nothing, under a cap that small."""
    used = sum(len(part) + 1 for part in (*written, *fence()))
    return max(0, limit - used - NOTE_ROOM - CUT_ROOM)


def whole_lines(lines: list[str], budget: int) -> int:
    """How many of `lines`, from the first, the budget holds whole: a line cut in half would
    read as a name."""
    kept, used = 0, 0
    for line in lines:
        if used + len(line) + 1 > budget:
            break
        kept, used = kept + 1, used + len(line) + 1
    return kept


def with_data(limit: int, said: str, data: str, *, used: int = 0, missing: str = "") -> str:
    """`said` with `data` fenced under it when the whole stays under the cap; `said` alone
    otherwise, and `missing` after it. Never a fence a cut would open and not close."""
    whole = "\n".join(part for part in (said, fenced(data)) if part)
    if used + len(whole) + CUT_ROOM <= limit:
        return whole
    return "\n".join(part for part in (said, missing) if part)


def answer(limit: int, outside: list[str], body: str) -> str:
    """What a tool answers: its own lines, then what the page had a say in between the fence
    lines. Under a cap with no room for that, the tool's lines and why the page is missing."""
    said = "\n".join(line for line in outside if line)
    return with_data(limit, said, body, missing=f.NO_ROOM.format(limit=limit))


def failure(limit: int, said: str, data: str) -> ToolError:
    """A refusal or an error whose details a page had a say in. The details are fenced under
    the tool's own words, or left out where the cap has no room for them."""
    return ToolError(with_data(limit, said, data, used=FAILED_ROOM))


def driver_error(limit: int, said: str, exc: BaseException) -> ToolError:
    """An error of the browser: `said` is told its kind, and the line the browser wrote goes
    inside the fence."""
    words = f.BROWSER_SAID.format(error=first_line(exc))
    return failure(limit, said.format(error=kind_of(exc)), words)
