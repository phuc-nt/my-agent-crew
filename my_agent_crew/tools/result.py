"""What a tool call comes to: the text the model reads, and what the run card is told of it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NestedCall:
    """One call a script made on its own (`tool_script`). The model reads none of these,
    only what its script printed, so the run card lists them for the person: a preview of
    what was asked and of what came back, as a step of the timeline keeps them."""

    name: str
    arguments: dict[str, Any]
    ok: bool
    output: str
    ms: int
    # As on `ToolResult`: a call that paid a model is charged on its own, like any other.
    cost_usd: float | None = None
    metered: bool = False


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    output: str
    # Set by a tool that paid a model itself (`image_read`): the price, or None when the
    # upstream reported none. `metered` says the call is to be charged at all.
    cost_usd: float | None = None
    metered: bool = False
    # How the output was brought under the cap: "none", "json" (structure kept), "summary"
    # (middle paraphrased by a model) or "cut", with the size before shaping. The run card
    # shows this so a short answer built on a shortened tool output is not mistaken for one
    # built on the whole thing.
    shaped_kind: str = "none"
    original_chars: int = 0
    # Set by a tool whose output already is an answer for the person (`delegate`, when the
    # child finished): the answer whole, untouched by shaping. When that call was the
    # turn's only one, the loop hands it on instead of paying a model to retell it.
    reply: str | None = None
    # The calls a script made on its own, in order. Empty for every other tool.
    calls: tuple[NestedCall, ...] = ()
    # Set by a tool whose work was another conversation's (`delegate`): what that one
    # spent, which is this conversation's spend too. It is added as the result is written,
    # so a call made again after a restart costs its conversation once. No part of
    # `cost_usd`: the other conversation's own run already carries what it paid.
    child_spent_usd: float = 0.0
