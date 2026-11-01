"""Turning a Claude API failure into the `ProviderError` the route chain acts on.

What matters to the chain is whether to ask the same route again (`transient`) or move
straight on. A rate limit (429), an overloaded API (529) and a server error (5xx) pass;
a refused key, a bad request and an empty credit balance do not. Running out of credit is
its own kind, `OutOfCredit`, because the provider then stops calling for a while: every
call would fail the same way until the owner tops up or the month's credit renews.

The API's own error text goes into the message so the log says what happened. It never
contains the key, which is sent only in a header and never echoed back.
"""

from __future__ import annotations

import json
from typing import Any

from my_agent_crew.llm.provider import ProviderError

# Kinds of error the API sends, in a reply body or mid-stream, that asking again may cure.
TRANSIENT_KINDS = ("rate_limit_error", "overloaded_error", "api_error", "timeout_error")
AUTH_KINDS = ("authentication_error", "permission_error")
# An exhausted balance arrives as a 400 `invalid_request_error` whose text says so
# ("Your credit balance is too low to access the Anthropic API…"), or as 402.
CREDIT_HINT = "credit balance"
BILLING_KIND = "billing_error"
MAX_DETAIL = 300


class OutOfCredit(ProviderError):
    """The account has no credit left. Never transient: the same call fails again."""

    def __init__(self, message: str):
        super().__init__(message, transient=False)


def transient_status(status: int) -> bool:
    return status in (408, 425, 429) or status >= 500


def parse_error(raw: Any) -> tuple[str, str]:
    """`(type, message)` of an API error object, or of a JSON body carrying one."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return "", raw.strip()[:MAX_DETAIL]
    error = raw.get("error") if isinstance(raw, dict) else None
    if not isinstance(error, dict):
        return "", ""
    kind, message = error.get("type"), error.get("message")
    return (
        kind if isinstance(kind, str) else "",
        message[:MAX_DETAIL] if isinstance(message, str) else "",
    )


def _out_of_credit(status: int, kind: str, message: str) -> bool:
    return status == 402 or kind == BILLING_KIND or CREDIT_HINT in message.lower()


def http_error(status: int, body: str, model: str) -> ProviderError:
    """The error for a reply with status 400 or above."""
    kind, message = parse_error(body)
    detail = f"{kind}: {message}" if kind and message else (kind or message or "no detail")
    if status in (401, 403) or kind in AUTH_KINDS:
        return ProviderError(
            f"Anthropic rejected the API key (HTTP {status}, {kind or 'unauthorized'}): "
            "check ANTHROPIC_API_KEY"
        )
    if _out_of_credit(status, kind, message):
        return OutOfCredit(f"Anthropic credit is used up (HTTP {status}): {detail}")
    return ProviderError(
        f"HTTP {status} from {model}: {detail}", transient=transient_status(status)
    )


def stream_error(raw: Any, model: str) -> ProviderError:
    """The error for an `error` event sent in the middle of a stream."""
    kind, message = parse_error({"error": raw.get("error")} if isinstance(raw, dict) else raw)
    if _out_of_credit(0, kind, message):
        return OutOfCredit(f"Anthropic credit is used up: {kind}: {message}")
    return ProviderError(
        f"{kind or 'error'} from {model} mid-stream: {message or 'no detail'}",
        transient=kind in TRANSIENT_KINDS,
    )
