"""A name for a conversation, taken from the first thing the person said.

A sidebar where every row reads "Cuộc trò chuyện mới" carries no information: the list
grows, and finding last Tuesday's thread means opening them one by one. So the first
message names the thread.

It happens twice. The heuristic title — the opening sentence, cut at a word — is written
before the turn runs, so the row is already meaningful by the time the answer arrives. A
model then writes a better one in the background and replaces it, but only if the
heuristic is still there: a person who renamed the thread has said what it is called, and
nothing should argue with them.

Only conversations still carrying the default title qualify, which is what keeps Telegram
and scheduled runs out — those are named after their channel or their job when they are
created, and a thread that opens fresh every day is not one anybody browses by name."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any

from my_agent_crew.llm.types import Completion, Message
from my_agent_crew.texts import CONVERSATION_TITLE_DEFAULT, TITLE_PROMPT

if TYPE_CHECKING:  # same cycle-avoidance as the other memory sections
    from my_agent_crew.agent.loop import AgentDeps

logger = logging.getLogger(__name__)

TITLE_MAX_CHARS = 60
MAX_SOURCE_CHARS = 1000
TITLE_TIMEOUT_S = 8.0

_SENTENCE_END = re.compile(r"[.!?…]+(?:\s|$)")
# What a model adds when it answers with a title instead of returning one.
_WRAPPING = ' \t"\'`*_·—-–:'

_in_flight: dict[str, asyncio.Task[None]] = {}


def _shorten(text: str, limit: int = TITLE_MAX_CHARS) -> str:
    """Cuts at the last word boundary that fits, so a title never ends mid-word."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    spaced = head.rsplit(" ", 1)[0]
    return (spaced if len(spaced) >= limit // 2 else head).rstrip(_WRAPPING)


def heuristic_title(text: str) -> str:
    """The opening sentence, flattened to one line and cut to fit a sidebar row."""
    flat = " ".join(text.split())
    if not flat:
        return ""
    match = _SENTENCE_END.search(flat)
    first = flat[: match.start()] if match else flat
    return _shorten(first.strip(_WRAPPING))


def clean_title(raw: str) -> str:
    """The model's answer reduced to a title: first line, no quoting, no trailing stop.

    Models sometimes reply with a sentence about the title, or wrap it in quotes. Taking
    the first line and stripping the decoration keeps the common cases; anything left
    that is too long is cut the same way the heuristic is."""
    first = raw.strip().splitlines()[0] if raw.strip() else ""
    return _shorten(" ".join(first.split()).strip(_WRAPPING))


def _is_untitled(conv: Any) -> bool:
    return conv.title == CONVERSATION_TITLE_DEFAULT


def _echoes_the_instructions(title: str) -> bool:
    """True when the answer is the request read back rather than a title.

    A model asked for a title sometimes repeats the instruction instead of following it,
    and the echo provider always does. Naming a thread after the prompt that asked for
    the name is worse than leaving the first sentence in place."""
    opening = " ".join(TITLE_PROMPT.split()[:4]).lower()
    return bool(opening) and opening in title.lower()


async def generate_title(deps: AgentDeps, text: str) -> tuple[str, float | None]:
    """Asks the model for a title, with what the answer cost.

    An empty title means the model had nothing usable to say; the cost is still returned,
    because an answer that was paid for was paid for whether or not it could be used."""
    prompt = Message(role="user", content=TITLE_PROMPT.format(message=text[:MAX_SOURCE_CHARS]))
    completion: Completion | None = None
    async for item in deps.chain.stream([prompt], []):
        if isinstance(item, Completion):
            completion = item
    if completion is None:
        return "", None
    title = clean_title(completion.message.content)
    cost_usd = completion.usage.cost_usd
    return ("" if _echoes_the_instructions(title) else title), cost_usd


async def _write_model_title(deps: AgentDeps, conv_id: str, text: str, heuristic: str) -> None:
    title, cost_usd = await asyncio.wait_for(generate_title(deps, text), TITLE_TIMEOUT_S)
    # Naming costs money like any other model call, so it is spent against the same cap.
    deps.store.add_spend(conv_id, cost_usd)
    if not title or title == heuristic:
        return
    if deps.store.get(conv_id).title != heuristic:
        return  # renamed by hand while the model was thinking; their name wins
    deps.store.update(conv_id, title=title)


def title_on_first_message(
    keep: object,
    deps: AgentDeps,
    conv_id: str,
    text: str,
    publish: Any = None,
    after: Any = None,
) -> str:
    """Names a still-unnamed conversation, and returns the title now on it.

    The heuristic is written inline — it costs nothing and the caller is about to show
    the thread. The model's version runs as a background task, one per conversation, so
    a person typing twice in a row does not pay for two titles.

    `after` is awaited before the model is asked, so naming queues behind the answer the
    person is waiting for instead of competing with it for the same chain. `keep` holds
    the task reference the way `schedule_summary` does; `publish` is called with the
    conversation after each write so watchers see the new name without a reload."""
    conv = deps.store.get(conv_id)
    if not _is_untitled(conv):
        return conv.title
    heuristic = heuristic_title(text)
    if not heuristic:
        return conv.title
    deps.store.update(conv_id, title=heuristic)
    _announce(deps, conv_id, publish)

    async def run() -> None:
        try:
            if after is not None:
                await after()
            await _write_model_title(deps, conv_id, text, heuristic)
            _announce(deps, conv_id, publish)
        except TimeoutError:
            logger.info("title timed out for conversation %s, keeping the first sentence", conv_id)
        except KeyError:
            # Deleted while the model was thinking. Ordinary, and nothing is left to name.
            logger.info("conversation %s went away before it could be named", conv_id)
        except Exception:  # a title is a nicety; it must never break the turn
            logger.exception("title failed for conversation %s", conv_id)

    if conv_id not in _in_flight:
        task = asyncio.create_task(run())
        _in_flight[conv_id] = task
        # Cleared from a done-callback rather than the coroutine: cancellation does not
        # run `finally` here, and a leaked entry would bar this conversation from ever
        # being named again for the life of the process.
        task.add_done_callback(lambda _: _in_flight.pop(conv_id, None))
        if callable(keep):
            keep(task)
    return heuristic


def _announce(deps: AgentDeps, conv_id: str, publish: Any) -> None:
    if callable(publish):
        publish(deps.store.get(conv_id).to_dict())
