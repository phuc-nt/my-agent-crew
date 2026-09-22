"""Bringing a long *text* output under the cap by summarising only its middle.

JSON is handled by `output_shaping`, which keeps the structure and never asks a model
anything. Plain text has no structure to keep, and a straight cut throws away the ending,
which is where a log puts its result and a report puts its conclusion. So the opening and
the ending are kept verbatim and only the middle is replaced by a summary.

Three rules hold the whole design together:

* The verbatim parts stay verbatim. A number the model never touched cannot be a number
  the model got wrong.
* The summary is labelled as a summary. A reader, human or model, must be able to tell
  which figures came from the source and which came from a paraphrase.
* Summarising must never block the tool. No route, a failing route, a slow route, an
  empty answer — every one of them falls back to the plain cut the caller would have got
  anyway. A summary is an improvement on a cut, never a precondition for one.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from my_agent_crew.llm.types import Completion, Message

logger = logging.getLogger(__name__)

# What the model is shown between the two verbatim parts. It names the summary as a
# summary, so a figure read out of it is never mistaken for one read out of the source.
OUTPUT_SUMMARY_MIDDLE = (
    "\n\n[tóm tắt phần giữa ({dropped} ký tự), không phải nguyên văn]\n"
    "{summary}\n"
    "[hết tóm tắt, phần dưới lại là nguyên văn]\n\n"
)
OUTPUT_SUMMARY_PROMPT = (
    "Đây là phần giữa của một output dài bị cắt. Hãy tóm tắt trong {limit} ký tự,"
    " bằng tiếng Việt, giữ NGUYÊN mọi con số, tên riêng, đường dẫn và mã.\n"
    "Không thêm nhận xét, không mở đầu, chỉ nội dung tóm tắt.\n\n{text}"
)

# How the cap is split. The opening says what the output is and how it starts; the ending
# carries the total, the error or the conclusion. The rest of the cap pays for the summary.
HEAD_SHARE = 0.4
TAIL_SHARE = 0.2
# Below this there is no room for three parts plus their labels, so a plain cut is honest.
MIN_SUMMARY_CHARS = 600
# What is sent to the model. A middle larger than this is itself cut first: a summary of
# the first 24k characters is worth more than a request that times out.
MAX_SOURCE_CHARS = 24_000
SUMMARY_TIMEOUT_S = 15.0


@dataclass(frozen=True)
class Summarised:
    """The text to show the model, or None when nothing better than a cut was possible."""

    text: str
    summary_chars: int
    cost_usd: float | None


# Given a prompt, return the model's answer and what it cost. Both may be empty or None.
Summariser = Callable[[str], Awaitable[tuple[str, float | None]]]


def chain_summariser(chain: object) -> Summariser:
    """A summariser backed by a provider chain, used with an agent's own routes.

    The chain is asked with no tools and one user message, the same shape a title uses.
    `ProviderError` is not caught here: `summarise` catches everything, so a dead route
    lands in the same fallback as an empty answer."""

    async def run(prompt: str) -> tuple[str, float | None]:
        completion: Completion | None = None
        async for item in chain.stream([Message(role="user", content=prompt)], []):  # type: ignore[attr-defined]
            if isinstance(item, Completion):
                completion = item
        if completion is None:
            return "", None
        return completion.message.content.strip(), completion.usage.cost_usd

    return run


def split(text: str, limit: int) -> tuple[str, str, str]:
    """`text` as (head, middle, tail) for a cap of `limit`.

    The head and the tail are sized from the cap, not from the text, so the verbatim parts
    are the same length whether the middle was ten thousand characters or a million."""
    head_chars = int(limit * HEAD_SHARE)
    tail_chars = int(limit * TAIL_SHARE)
    return text[:head_chars], text[head_chars : len(text) - tail_chars], text[-tail_chars:]


def budget(limit: int) -> int:
    """How many characters the summary itself may use, once the verbatim parts and their
    labels are paid for."""
    labels = len(OUTPUT_SUMMARY_MIDDLE.format(dropped=0, summary=""))
    return int(limit * (1 - HEAD_SHARE - TAIL_SHARE)) - labels


async def summarise(text: str, limit: int, summariser: Summariser | None) -> Summarised | None:
    """`text` with its middle summarised, or None to fall back to a plain cut.

    None is returned for every reason a summary could fail to be an improvement: no
    summariser, a cap too small to hold three parts, a middle not worth summarising, a
    route that failed or timed out, an empty answer. The caller cuts in all of them."""
    if summariser is None or limit < MIN_SUMMARY_CHARS:
        return None
    room = budget(limit)
    if room <= 0:
        return None
    head, middle, tail = split(text, limit)
    if len(middle) <= room:
        return None  # the middle already fits; summarising it would lose the wording for nothing
    prompt = OUTPUT_SUMMARY_PROMPT.format(limit=room, text=middle[:MAX_SOURCE_CHARS])
    try:
        summary, cost_usd = await asyncio.wait_for(summariser(prompt), SUMMARY_TIMEOUT_S)
    except TimeoutError:
        logger.info("tool output summary timed out after %ss, cutting instead", SUMMARY_TIMEOUT_S)
        return None
    except Exception:  # a summary is an improvement; its failure must not fail the tool
        logger.exception("tool output summary failed, cutting instead")
        return None
    summary = " ".join(summary.split())[:room]
    if not summary:
        return None
    joined = head + OUTPUT_SUMMARY_MIDDLE.format(dropped=len(middle), summary=summary) + tail
    if len(joined) > limit:
        # The model wrote past its budget, or the labels grew. Trimming the summary rather
        # than returning something over cap keeps the one promise this module cannot break.
        over = len(joined) - limit
        summary = summary[: max(len(summary) - over, 0)]
        if not summary:
            return None
        joined = head + OUTPUT_SUMMARY_MIDDLE.format(dropped=len(middle), summary=summary) + tail
    return Summarised(joined, len(summary), cost_usd)
