import pytest

from my_agent_crew.llm.anthropic_wire import (
    CACHE,
    NO_RESULT,
    effort_for,
    request_body,
    to_wire,
    tool_id,
    tools_to_wire,
)
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import AudioPart, Message, ToolCall, ToolSpec

TOOL = ToolSpec("workspace_list", "List files", {"type": "object", "properties": {}})


def test_the_leading_system_messages_become_the_system_field_marked_for_the_cache():
    system, wire = to_wire(
        [
            Message(role="system", content="You are the crew."),
            Message(role="system", content="Today is Sunday."),
            Message(role="user", content="hi"),
        ]
    )
    assert [b["text"] for b in system] == ["You are the crew.", "Today is Sunday."]
    assert "cache_control" not in system[0] and system[-1]["cache_control"] == CACHE
    assert wire == [
        {"role": "user", "content": [{"type": "text", "text": "hi", "cache_control": CACHE}]}
    ]


def test_a_tool_round_trip_maps_to_tool_use_and_tool_result_blocks():
    call = ToolCall(id="call_1", name="workspace_list", arguments={"path": "."})
    _, wire = to_wire(
        [
            Message(role="user", content="list"),
            Message(role="assistant", content="Looking.", tool_calls=(call,)),
            Message(role="tool", content="a.txt", tool_call_id="call_1", name="workspace_list"),
        ]
    )
    assert [m["role"] for m in wire] == ["user", "assistant", "user"]
    assert wire[1]["content"] == [
        {"type": "text", "text": "Looking."},
        {"type": "tool_use", "id": "call_1", "name": "workspace_list", "input": {"path": "."}},
    ]
    result = wire[2]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "call_1"
    assert result["content"] == "a.txt" and result["cache_control"] == CACHE


def test_results_of_several_calls_and_a_following_user_message_share_one_message_results_first():
    calls = (ToolCall("a", "t", {}), ToolCall("b", "t", {}))
    _, wire = to_wire(
        [
            Message(role="user", content="go"),
            Message(role="assistant", tool_calls=calls),
            Message(role="tool", content="one", tool_call_id="a"),
            Message(role="tool", content="two", tool_call_id="b"),
            Message(role="user", content="and now?"),
        ]
    )
    assert len(wire) == 3
    assert [b["type"] for b in wire[2]["content"]] == ["tool_result", "tool_result", "text"]
    assert wire[1]["content"][0]["type"] == "tool_use"  # no empty text block before it


def test_a_call_left_without_a_result_is_answered_and_a_stray_result_kept_as_text():
    _, wire = to_wire(
        [
            Message(role="user", content="go"),
            Message(role="assistant", tool_calls=(ToolCall("a", "t", {}),)),
            Message(role="tool", content="lost", tool_call_id="zzz"),
        ]
    )
    blocks = wire[2]["content"]
    assert blocks[0] == {
        "type": "tool_result",
        "tool_use_id": "a",
        "content": NO_RESULT,
        "is_error": True,
    }
    assert blocks[1]["type"] == "text" and "lost" in blocks[1]["text"]


def test_ids_written_by_another_provider_are_made_valid_the_same_way_on_both_sides():
    assert tool_id("functions.web_search:0") == "functions_web_search_0"
    _, wire = to_wire(
        [
            Message(role="user", content="go"),
            Message(role="assistant", tool_calls=(ToolCall("fn.x:1", "t", {}),)),
            Message(role="tool", content="ok", tool_call_id="fn.x:1"),
        ]
    )
    assert wire[1]["content"][0]["id"] == wire[2]["content"][0]["tool_use_id"] == "fn_x_1"


def test_a_history_opening_with_the_assistant_gets_a_user_message_first():
    _, wire = to_wire(
        [Message(role="assistant", content="Hello"), Message(role="user", content="hi")]
    )
    assert wire[0]["role"] == "user" and wire[1]["role"] == "assistant"


def test_a_later_system_message_becomes_user_text():
    _, wire = to_wire(
        [
            Message(role="user", content="hi"),
            Message(role="system", content="The job was cancelled."),
        ]
    )
    assert len(wire) == 1
    assert [b["text"] for b in wire[0]["content"]] == ["hi", "The job was cancelled."]


def test_pictures_go_before_the_text_as_image_blocks():
    _, wire = to_wire(
        [
            Message(
                role="user",
                content="what is this?",
                images=("data:image/jpeg;base64,QUJD", "https://example.org/a.png"),
            )
        ]
    )
    first, second, text = wire[0]["content"]
    assert first["source"] == {"type": "base64", "media_type": "image/jpeg", "data": "QUJD"}
    assert second["source"] == {"type": "url", "url": "https://example.org/a.png"}
    assert text["text"] == "what is this?"


def test_audio_is_refused_before_any_request_so_the_chain_moves_on():
    with pytest.raises(ProviderError) as caught:
        to_wire([Message(role="user", content="x", audio=(AudioPart("AAA", "ogg"),))])
    assert caught.value.transient is False


def test_tools_carry_their_schema_and_the_last_one_marks_the_cache():
    wire = tools_to_wire([TOOL, ToolSpec("b", "B", {"type": "object"})])
    assert wire[0] == {
        "name": "workspace_list",
        "description": "List files",
        "input_schema": TOOL.parameters,
    }
    assert wire[-1]["cache_control"] == CACHE and "cache_control" not in wire[0]


def test_a_request_uses_at_most_three_cache_breakpoints():
    body = request_body(
        [Message(role="system", content="s"), Message(role="user", content="u")],
        [TOOL],
        "claude-sonnet-5-5",
        "",
        32000,
    )
    marks = str(body).count("cache_control")
    assert marks == 3 and body["stream"] is True and body["max_tokens"] == 32000
    assert "temperature" not in body and "thinking" not in body and "output_config" not in body


@pytest.mark.parametrize(
    ("model", "reasoning", "effort"),
    [
        ("claude-sonnet-5-5", "high", "high"),
        ("claude-opus-5-5", "minimal", "low"),
        ("claude-haiku-5-5", "medium", "medium"),
        ("claude-haiku-4-5", "high", None),
        ("claude-sonnet-4-5", "high", None),
        ("some-new-model", "high", None),
        ("claude-sonnet-5-5", "", None),
    ],
)
def test_effort_is_sent_only_to_models_that_take_it(model, reasoning, effort):
    assert effort_for(model, reasoning) == effort
    body = request_body([Message(role="user", content="u")], [], model, reasoning, 100)
    assert body.get("output_config") == ({"effort": effort} if effort else None)
