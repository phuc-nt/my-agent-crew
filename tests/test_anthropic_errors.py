"""Each Claude API failure tells the route chain whether to ask again or move on."""

import httpx
import pytest

from my_agent_crew.llm.anthropic import AnthropicProvider
from my_agent_crew.llm.anthropic_errors import OutOfCredit
from my_agent_crew.llm.provider import ProviderError
from tests.anthropic_helpers import (
    HI,
    KEY,
    block,
    delta,
    end,
    error_body,
    provider_with,
    sse,
    start,
)
from tests.conftest import collect


async def test_a_refusal_before_any_word_raises_before_any_item():
    body = sse(start(), block(0, type="thinking", thinking=""), *end("refusal"))
    stream = provider_with(body).stream(HI, [], "claude-opus-5-5")
    with pytest.raises(ProviderError) as caught:
        await stream.__anext__()
    assert "refusal" in str(caught.value)


async def test_a_stream_that_stops_before_the_end_is_a_passing_failure():
    body = sse(start(), block(0, type="text", text=""), delta(0, type="text_delta", text="Hal"))
    with pytest.raises(ProviderError) as caught:
        await collect(provider_with(body).stream(HI, [], "claude-sonnet-5-5"))
    assert caught.value.transient is True


@pytest.mark.parametrize(
    ("status", "kind", "message", "transient"),
    [
        (429, "rate_limit_error", "slow down", True),
        (529, "overloaded_error", "Overloaded", True),
        (500, "api_error", "Internal", True),
        (503, "api_error", "Unavailable", True),
        (400, "invalid_request_error", "messages: bad", False),
        (404, "not_found_error", "model: claude-x", False),
    ],
)
async def test_http_failures_say_whether_asking_again_may_help(status, kind, message, transient):
    p = provider_with(error_body(kind, message), status=status)
    with pytest.raises(ProviderError) as caught:
        await collect(p.stream(HI, [], "claude-sonnet-5-5"))
    assert caught.value.transient is transient
    assert not isinstance(caught.value, OutOfCredit)
    assert kind in str(caught.value) and str(status) in str(caught.value)


@pytest.mark.parametrize("status", [401, 403])
async def test_a_rejected_key_says_which_variable_to_check_and_never_shows_the_key(status):
    p = provider_with(error_body("authentication_error", "invalid x-api-key"), status=status)
    with pytest.raises(ProviderError) as caught:
        await collect(p.stream(HI, [], "claude-sonnet-5-5"))
    assert caught.value.transient is False
    assert "ANTHROPIC_API_KEY" in str(caught.value) and KEY not in str(caught.value)


async def test_a_mid_stream_overload_is_a_passing_failure():
    body = sse(start(), {"type": "error", "error": {"type": "overloaded_error", "message": "x"}})
    with pytest.raises(ProviderError) as caught:
        await collect(provider_with(body).stream(HI, [], "claude-sonnet-5-5"))
    assert caught.value.transient is True


async def test_a_malformed_stream_is_not_retried():
    with pytest.raises(ProviderError) as caught:
        await collect(provider_with("data: {not json\n\n").stream(HI, [], "claude-sonnet-5-5"))
    assert caught.value.transient is False


async def test_a_transport_failure_is_a_passing_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    p = AnthropicProvider(KEY, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(ProviderError) as caught:
        await collect(p.stream(HI, [], "claude-sonnet-5-5"))
    assert caught.value.transient is True
