from dataclasses import replace

import pytest

from my_agent_crew.config import Route
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.provider import AllRoutesFailed, ProviderChain, ProviderError
from my_agent_crew.llm.types import (
    Completion,
    Message,
    RouteFailed,
    TextDelta,
    ToolCall,
    ToolCallDelta,
)
from tests.conftest import collect

USER = [Message(role="user", content="hi")]


async def test_first_route_success_never_touches_second():
    a = ScriptedProvider([completion("from a")], name="a")
    b = ScriptedProvider([completion("from b")], name="b")
    chain = ProviderChain({"a": a, "b": b}, [Route("a", "m1"), Route("b", "m2")])
    items = await collect(chain.stream(USER, []))
    assert items[-1].message.content == "from a"
    assert items[-1].model == "m1"
    assert b.requests == []


async def test_failure_before_first_item_falls_back_in_order():
    a = ScriptedProvider([ProviderError("a down")], name="a")
    b = ScriptedProvider([completion("from b")], name="b")
    chain = ProviderChain({"a": a, "b": b}, [Route("a", "m1"), Route("b", "m2")])
    items = await collect(chain.stream(USER, []))
    assert isinstance(items[-1], Completion) and items[-1].provider == "b"
    assert len(a.requests) == 1 and len(b.requests) == 1
    assert items[0] == RouteFailed(provider="a", model="m1", error="a down")


async def test_every_fallback_is_logged_as_a_warning(caplog):
    a = ScriptedProvider([ProviderError("a down")], name="a")
    b = ScriptedProvider([completion("from b")], name="b")
    chain = ProviderChain({"a": a, "b": b}, [Route("a", "m1"), Route("b", "m2")])
    with caplog.at_level("WARNING", logger="my_agent_crew.llm.provider"):
        await collect(chain.stream(USER, []))
    assert any("a:m1" in r.message and "a down" in r.message for r in caplog.records)


async def test_all_routes_failing_raises_with_every_error():
    a = ScriptedProvider([ProviderError("a down")], name="a")
    b = ScriptedProvider([ProviderError("b down")], name="b")
    chain = ProviderChain({"a": a, "b": b}, [Route("a", "m1"), Route("b", "m2")])
    with pytest.raises(AllRoutesFailed) as info:
        await collect(chain.stream(USER, []))
    seen = [(r.provider, str(e)) for r, e in info.value.errors]
    assert seen == [("a", "a down"), ("b", "b down")]
    assert "a down" in str(info.value) and "b down" in str(info.value)


async def test_mid_stream_failure_is_not_hidden_by_fallback():
    class Flaky:
        name = "flaky"

        async def stream(self, messages, tools, model):
            yield TextDelta("partial ")
            raise ProviderError("cut off")

    b = ScriptedProvider([completion("from b")], name="b")
    chain = ProviderChain({"flaky": Flaky(), "b": b}, [Route("flaky", "m"), Route("b", "m")])
    with pytest.raises(ProviderError, match="cut off"):
        await collect(chain.stream(USER, []))
    assert b.requests == []


def test_unknown_provider_in_routes_is_rejected_at_construction():
    with pytest.raises(ValueError, match="nope"):
        ProviderChain({"a": ScriptedProvider([])}, [Route("nope", "m")])


async def test_scripted_provider_streams_deltas_then_completion():
    p = ScriptedProvider([completion("hello world, this is long enough to chunk")])
    items = await collect(p.stream(USER, [], "m"))
    deltas = [i.text for i in items if isinstance(i, TextDelta)]
    assert "".join(deltas) == items[-1].message.content
    assert len(deltas) > 1


async def test_scripted_provider_streams_each_tool_call_in_pieces_before_the_completion():
    """As a real stream does: the words first, then each call's arguments twelve characters
    at a time under the call's place in the answer, then the completion as it was scripted."""
    scripted = completion(
        "đang viết",
        tool_calls=(
            ToolCall("c1", "artifact_create", {"title": "Kế hoạch"}),
            ToolCall("c2", "workspace_list", {}),
        ),
    )
    items = await collect(ScriptedProvider([scripted]).stream(USER, [], "m"))
    assert items == [
        TextDelta("đang viết"),
        ToolCallDelta(index=0, name="artifact_create", chunk='{"title": "K'),
        ToolCallDelta(index=0, name="artifact_create", chunk='ế hoạch"}'),
        ToolCallDelta(index=1, name="workspace_list", chunk="{}"),
        replace(scripted, provider="scripted", model="m"),
    ]


async def test_scripted_provider_streams_no_piece_for_an_answer_that_calls_nothing():
    items = await collect(ScriptedProvider([completion("xong")]).stream(USER, [], "m"))
    assert [type(item) for item in items] == [TextDelta, Completion]
