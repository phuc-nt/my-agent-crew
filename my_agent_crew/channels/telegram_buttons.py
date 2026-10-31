"""The buttons under a decision the agent waits on, and what a press on one says.

A chat used to settle a request only by typing `/approve`, `/deny` or a choice's number.
Telegram can put buttons under a message instead: Allow and Deny under a tool's request,
one button per choice under a question that offers choices. A question without choices has
none, since its answer is a sentence. Each button carries the request's id, so a press
settles that request and no other, however many messages came after it.

What a press does is `telegram_press`; this module only words the buttons and reads them
back. Telegram gives a button 64 bytes of data, which an id of 12 hex digits fits easily."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from my_agent_crew import texts
from my_agent_crew.agent.events import ApprovalRequiredEvent
from my_agent_crew.store.models import QUESTION

# A choice is a button only up to here; the rest are still answered by number or in words.
MAX_CHOICE_BUTTONS = 8
LABEL_CHARS = 48
ARGUMENT_CHARS = 400
_PRESS = re.compile(r"^(y|n|q([1-9]\d?)):([0-9a-f]{1,32})$")


@dataclass(frozen=True)
class Press:
    approval_id: str
    approve: bool
    choice: int = 0  # the 1-based number of the choice pressed, 0 for Allow or Deny


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def buttons_for(event: ApprovalRequiredEvent) -> dict[str, Any] | None:
    """The inline keyboard of a request, or None when it has nothing to press."""
    rid = event.approval_id
    if event.kind == QUESTION:
        options = event.options[:MAX_CHOICE_BUTTONS]
        rows = [
            [{"text": _cut(f"{i}. {option}", LABEL_CHARS), "callback_data": f"q{i}:{rid}"}]
            for i, option in enumerate(options, start=1)
        ]
        return {"inline_keyboard": rows} if rows else None
    allow = {"text": texts.TELEGRAM_BUTTON_APPROVE, "callback_data": f"y:{rid}"}
    deny = {"text": texts.TELEGRAM_BUTTON_DENY, "callback_data": f"n:{rid}"}
    return {"inline_keyboard": [[allow, deny]]}


def call_line(event: ApprovalRequiredEvent | None) -> str:
    """What a waiting tool call would run, cut short: the person decides on the command,
    not on the tool's name. Empty for a question, which shows itself."""
    if event is None or event.kind == QUESTION:
        return ""
    arguments = _cut(json.dumps(event.arguments, ensure_ascii=False), ARGUMENT_CHARS)
    return texts.TELEGRAM_APPROVAL_CALL.format(name=event.name, arguments=arguments)


def read_press(data: str) -> Press | None:
    """A button's data back as the press it stands for; None for anything else."""
    match = _PRESS.match(data)
    if match is None:
        return None
    kind, choice, rid = match.groups()
    return Press(rid, kind == "y", int(choice) if choice else 0)
