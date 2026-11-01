import json

import httpx
import pytest

from my_agent_crew.llm.anthropic import API_VERSION, MESSAGES_URL
from my_agent_crew.llm.tool_call_buffer import CUT_OFF
from my_agent_crew.llm.types import (
    Completion,
    ReasoningDelta,
    StreamStarted,
    TextDelta,
    ToolCallDelta,
    ToolSpec,
)
from tests.anthropic_helpers import HI, KEY, block, delta, end, provider_with, sse, start
from tests.conftest import collect


async def test_a_text_reply_streams_and_completes_with_usage_and_cost():
    captured: list[httpx.Request] = []
    body = sse(
        start(cache_read_input_tokens=1000),
        block(0, type="thinking", thinking=""),
        delta(0, type="signature_delta", signature="sig"),
        block(1, type="text", text=""),
        delta(1, type="text_delta", text="Xin "),
        delta(1, type="text_delta", text="chào"),
        *end("end_turn", output=4),
    )
    p = provider_with(body, capture=captured)
    items = await collect(p.stream(HI, [], "claude-sonnet-5-5", reasoning="low"))

    assert isinstance(items[0], StreamStarted)
    assert [i.text for i in items if isinstance(i, TextDelta)] == ["Xin ", "chào"]
    done = items[-1]
    assert isinstance(done, Completion)
    assert done.message.content == "Xin chào" and done.finish_reason == "stop"
    assert done.provider == "anthropic" and done.model == "claude-sonnet-5-5"
    assert done.usage.prompt_tokens == 1010 and done.usage.cached_tokens == 1000
    assert done.usage.cost_usd == pytest.approx((10 * 2 + 1000 * 0.2 + 4 * 10) / 1e6)

    request = captured[0]
    assert str(request.url) == MESSAGES_URL
    assert request.headers["x-api-key"] == KEY
    assert request.headers["anthropic-version"] == API_VERSION
    sent = json.loads(request.content)
    assert sent["system"][0]["text"] == "sys" and sent["output_config"] == {"effort": "low"}


async def test_a_tool_call_streams_its_pieces_and_completes_as_a_call():
    body = sse(
        start(),
        block(0, type="text", text=""),
        delta(0, type="text_delta", text="Checking."),
        block(1, type="tool_use", id="toolu_1", name="workspace_list", input={}),
        delta(1, type="input_json_delta", partial_json='{"pa'),
        delta(1, type="input_json_delta", partial_json='th": "."}'),
        block(2, type="tool_use", id="toolu_2", name="clock", input={}),
        *end("tool_use"),
    )
    tools = [ToolSpec("workspace_list", "List", {"type": "object"})]
    items = await collect(provider_with(body).stream(HI, tools, "claude-opus-5-5"))

    pieces = [i for i in items if isinstance(i, ToolCallDelta)]
    assert [(p.index, p.name, p.chunk) for p in pieces] == [
        (0, "workspace_list", '{"pa'),
        (0, "workspace_list", 'th": "."}'),
    ]
    done = items[-1]
    assert done.finish_reason == "tool_calls"
    first, second = done.message.tool_calls
    assert (first.id, first.name, first.arguments) == ("toolu_1", "workspace_list", {"path": "."})
    assert (second.name, second.arguments, second.invalid) == ("clock", {}, "")


async def test_a_call_cut_off_at_the_output_limit_is_marked_so():
    body = sse(
        start(),
        block(0, type="tool_use", id="toolu_1", name="write", input={}),
        delta(0, type="input_json_delta", partial_json='{"text": "long'),
        *end("max_tokens"),
    )
    done = (await collect(provider_with(body).stream(HI, [], "claude-sonnet-5-5")))[-1]
    assert done.finish_reason == "length"
    assert done.message.tool_calls[0].invalid.startswith(CUT_OFF)


async def test_shown_thinking_passes_on_as_reasoning():
    body = sse(
        start(),
        block(0, type="thinking", thinking=""),
        delta(0, type="thinking_delta", thinking="Hmm."),
        block(1, type="text", text=""),
        delta(1, type="text_delta", text="Yes."),
        *end("end_turn"),
    )
    items = await collect(provider_with(body).stream(HI, [], "claude-sonnet-5-5"))
    assert [type(i) for i in items[:3]] == [StreamStarted, ReasoningDelta, TextDelta]
