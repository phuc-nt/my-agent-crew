"""The events of one tool call: it begins, a script's own calls end inside it, and it ends."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCallEvent:
    tool_call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class NestedCallEvent:
    """One call a script made, sent the moment it ended and not when the script did: the
    run card lists it and adds what it cost while the script still runs. `index` is its
    place among the calls of that script that have ended, from 0, so whoever is sent it
    twice keeps it once. The result of the script lists them all again, as written."""

    tool_call_id: str
    index: int
    call: dict[str, Any]


@dataclass(frozen=True)
class ToolResultEvent:
    tool_call_id: str
    name: str
    ok: bool
    output: str
    # How the output was brought under the cap ("none", "json" or "cut") and how long it
    # was first. Carried so a run card can say the model answered from a shortened output.
    shaped_kind: str = "none"
    original_chars: int = 0
    # What the tool paid a model (a picture, a scanned page, a long output summarised),
    # when `metered`; None there means the provider gave no price. The run adds it up.
    cost_usd: float | None = None
    metered: bool = False
    # The calls a script made on its own (`tool_script`), each as a timeline row keeps one,
    # and how much of their answers it was handed and how much it printed back.
    calls: list[dict[str, Any]] = field(default_factory=list)
    received_chars: int | None = None
    printed_chars: int | None = None

    def stored_context(self) -> str:
        """What a script's stored result keeps beside its output, as JSON: the calls it
        made and its two measures. The chat card lists them after a reload, when the run
        that showed them may be gone; the model is never sent them. Empty for every other
        tool."""
        if not self.calls and self.received_chars is None and self.printed_chars is None:
            return ""
        measures = {"received_chars": self.received_chars, "printed_chars": self.printed_chars}
        return json.dumps({"calls": self.calls} | measures, ensure_ascii=False)
