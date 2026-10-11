"""What a model is asked when a script asks one, and what is made of its answer.

The text a script hands over is whatever a tool gave it: a mail, a page, a note somebody else
wrote. It is put to the model as data to work on. What the model is to do is said in a message
of the server's own; the text comes after, in a message of its own, between two lines that
carry a number made for that one call, so no text can close its own fence.

That alone holds no model to anything. What holds is what is made of the answer here: of a
classification only one of the labels the script gave is ever handed back, and a summary is
cut to the length asked for, whatever the text talked the model into.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

from my_agent_crew import texts_script_llm as words
from my_agent_crew.llm.types import Message
from my_agent_crew.script.limits import ScriptError
from my_agent_crew.script.llm_calls import CLASSIFY, plain

# What a model wraps a short answer in: quotes, the marks of bold, a full stop.
WRAPPING = " \"'`*_.,:;!?()[]{}<>“”‘’«»"


def messages(name: str, asked: dict[str, Any]) -> list[Message]:
    """What to do, in the server's words; then the text alone, fenced."""
    nonce = secrets.token_hex(8)
    opening = words.LLM_DATA_OPEN.format(nonce=nonce)
    closing = words.LLM_DATA_CLOSE.format(nonce=nonce)
    fence = words.LLM_FENCE.format(opening=opening, closing=closing)
    if name == CLASSIFY:
        # One label to a line, whatever line breaks a label was written with.
        labels = "\n".join(
            words.LLM_LABEL_LINE.format(label=" ".join(label.split())) for label in asked["labels"]
        )
        told = words.LLM_CLASSIFY_SYSTEM.format(fence=fence, labels=labels)
    else:
        told = words.LLM_SUMMARISE_SYSTEM.format(fence=fence, most=asked["max_chars"])
    return [
        Message(role="system", content=told),
        Message(role="user", content=f"{opening}\n{asked['text']}\n{closing}"),
    ]


def _bare(text: str) -> str:
    return plain(text).strip(WRAPPING)


def _written_in(label: str, said: str) -> bool:
    """Whether the label stands in the answer as words of its own: `no` is not in `know`."""
    return re.search(rf"(?<!\w){re.escape(plain(label))}(?!\w)", said) is not None


def _label(answer: str, labels: list[str]) -> str | None:
    """The label an answer names, as the script wrote it. The answer is one of them, however
    it was cased and spaced; or it is one and no other once what wraps it is taken off; or
    one of them and no other is written in it. An answer that could be two is none."""
    said = plain(answer)
    for label in labels:
        if plain(label) == said:
            return label
    unwrapped = _bare(answer)
    for found in (
        [label for label in labels if unwrapped and _bare(label) == unwrapped],
        [label for label in labels if _written_in(label, said)],
    ):
        if len(found) == 1:
            return found[0]
    return None


def taken(name: str, asked: dict[str, Any], answer: str) -> str:
    """What the script is handed of a model's answer; or a `ScriptError` it may catch, which
    repeats none of what the model said."""
    if not answer.strip():
        raise ScriptError(words.LLM_NO_ANSWER)
    if name == CLASSIFY:
        label = _label(answer, asked["labels"])
        if label is None:
            raise ScriptError(words.LLM_NOT_A_LABEL)
        return label
    return answer.strip()[: asked["max_chars"]].rstrip()
