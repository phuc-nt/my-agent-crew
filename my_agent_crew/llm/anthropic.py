"""Claude through the Anthropic Messages API, paid from the account's API credit.

Plain httpx like the other providers, not the Anthropic SDK: the engine already owns
the streaming, retry and fallback logic (the route chain), shares one httpx client
across providers, and needs only one endpoint. The key comes from `ANTHROPIC_API_KEY`
and is sent as the `x-api-key` header, never logged.

When the credit runs out the API refuses every call, so after the first such refusal
the provider fails at once without a request for `credit_cooldown_s`: each turn goes
straight to the next route (OpenRouter) instead of paying a round trip to hear the same
refusal. After the pause it tries again, which picks up a top-up or the monthly renewal.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator, Sequence

import httpx

from my_agent_crew.llm.anthropic_errors import OutOfCredit, http_error
from my_agent_crew.llm.anthropic_stream import ReplyReader
from my_agent_crew.llm.anthropic_wire import request_body
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import Message, StreamItem, ToolSpec

logger = logging.getLogger(__name__)

MESSAGES_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2026-10-21"
# The reply's output cap. Every current model allows at least 64K; this leaves room for
# a long document in one tool call without letting a runaway reply bill without end.
MAX_TOKENS = 32_000


class AnthropicProvider:
    name = "anthropic"
    credit_cooldown_s = 900.0

    def __init__(
        self, api_key: str, client: httpx.AsyncClient | None = None, cache_ttl: str = "5m"
    ):
        self._api_key = api_key
        self._cache_ttl = cache_ttl
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(120.0))
        self._no_credit_until = 0.0

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

    def _check_credit(self) -> None:
        left = self._no_credit_until - time.monotonic()
        if left > 0:
            raise OutOfCredit(
                f"Anthropic credit is used up; not asking again for {int(left // 60) + 1} min"
            )

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        model: str,
        reasoning: str = "",
    ) -> AsyncIterator[StreamItem]:
        self._check_credit()
        body = request_body(messages, tools, model, reasoning, MAX_TOKENS, self._cache_ttl)
        reader = ReplyReader(self.name, model)
        try:
            async with self._client.stream(
                "POST", MESSAGES_URL, json=body, headers=self._headers()
            ) as resp:
                if resp.status_code >= 400:
                    raise http_error(resp.status_code, (await resp.aread()).decode(), model)
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    for item in reader.feed(json.loads(line[5:].strip())):
                        yield item
        except OutOfCredit:
            self._no_credit_until = time.monotonic() + self.credit_cooldown_s
            logger.warning("anthropic credit used up; pausing it for %ss", self.credit_cooldown_s)
            raise
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"transport failure talking to {model}: {exc}", transient=True
            ) from exc
        except ValueError as exc:
            raise ProviderError(f"malformed stream from {model}") from exc
        yield reader.completion()
