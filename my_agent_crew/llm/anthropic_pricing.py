"""What a Claude API call cost, worked out from the usage it reports.

OpenRouter puts the price in the stream; the Claude API reports only token counts, so
the price comes from this table. The rates are USD per million tokens as published on
Anthropic's pricing page (taken from the claude-api skill's model table, cached
2026-10-06). A model missing here gets no price (`None`), never a guess: the cost cap
then shows the call as unpriced instead of counting it as free or at someone else's
rate. Prices change with model releases, so a new model means a new row.
"""

from __future__ import annotations

from dataclasses import dataclass

MILLION = 1_000_000
# Writing the prompt cache costs more than reading the prompt plainly: 1.25 times the
# input rate for the default five-minute lifetime, twice for the one-hour lifetime.
WRITE_5M_FACTOR = 1.25
WRITE_1H_FACTOR = 2.0
# Claude Haiku 5.5 bills a prompt above this many tokens at its higher rates.
HAIKU_5_5_LONG_PROMPT = 100_000


@dataclass(frozen=True)
class Price:
    """USD per million tokens."""

    input: float
    output: float
    cache_read: float


HAIKU_5_5_SHORT = Price(0.10, 0.50, 0.01)
HAIKU_5_5_LONG = Price(0.50, 2.50, 0.05)

# Matched by id prefix, so a dated id (`claude-haiku-4-5-20251001`) finds its family.
# Kept longest first: `claude-opus-5-5` must win over `claude-opus-5`.
PRICES: dict[str, Price] = {
    "claude-fable-5-1": Price(10.0, 50.0, 0.25),
    "claude-mythos-5-1": Price(10.0, 50.0, 0.25),
    "claude-fable-5": Price(10.0, 50.0, 1.00),
    "claude-mythos-5": Price(10.0, 50.0, 1.00),
    "claude-opus-5-5": Price(4.0, 20.0, 0.20),
    "claude-opus-5": Price(5.0, 25.0, 0.50),
    "claude-opus-4-8": Price(5.0, 25.0, 0.50),
    "claude-opus-4-7": Price(5.0, 25.0, 0.50),
    "claude-opus-4-6": Price(5.0, 25.0, 0.50),
    "claude-sonnet-5-5": Price(2.0, 10.0, 0.20),
    "claude-sonnet-5": Price(2.0, 10.0, 0.20),
    "claude-sonnet-4-6": Price(3.0, 15.0, 0.30),
    "claude-haiku-5-5": HAIKU_5_5_SHORT,
    "claude-haiku-4-5": Price(1.0, 5.0, 0.10),
}


def family(model: str) -> str | None:
    """The table row a model id belongs to: the id itself or a longer, dated form of it."""
    for prefix in sorted(PRICES, key=len, reverse=True):
        if model == prefix or model.startswith(prefix + "-"):
            return prefix
    return None


def price_for(model: str, prompt_tokens: int) -> Price | None:
    row = family(model)
    if row is None:
        return None
    if row == "claude-haiku-5-5" and prompt_tokens > HAIKU_5_5_LONG_PROMPT:
        return HAIKU_5_5_LONG
    return PRICES[row]


def cost_usd(
    model: str,
    *,
    fresh: int,
    cache_read: int = 0,
    write_5m: int = 0,
    write_1h: int = 0,
    output: int = 0,
) -> float | None:
    """The call's price. `fresh` is the prompt that was neither read from nor written to
    the cache (the API's `input_tokens`); the four inputs together are the whole prompt."""
    price = price_for(model, fresh + cache_read + write_5m + write_1h)
    if price is None:
        return None
    total = (
        fresh * price.input
        + cache_read * price.cache_read
        + write_5m * price.input * WRITE_5M_FACTOR
        + write_1h * price.input * WRITE_1H_FACTOR
        + output * price.output
    )
    return total / MILLION
