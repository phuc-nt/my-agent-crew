from my_agent_crew.agent.context_trim import KEEP_TOOL_OUTPUTS, trim_tool_outputs
from my_agent_crew.llm.types import Message


def tool_message(index: int, size: int = 500) -> Message:
    return Message(role="tool", content=f"{index}" * size, tool_call_id=f"call-{index}")


def test_short_history_is_returned_unchanged():
    messages = [Message(role="user", content="hi"), tool_message(1)]
    assert trim_tool_outputs(messages) == messages


def test_only_tool_results_beyond_the_window_become_stubs():
    messages = [tool_message(i) for i in range(KEEP_TOOL_OUTPUTS + 5)]
    trimmed = trim_tool_outputs(messages)
    assert [m.content.startswith("[kết quả cũ") for m in trimmed[:5]] == [True] * 5
    assert trimmed[5:] == messages[5:]
    assert "500 ký tự" in trimmed[0].content


def test_stubs_keep_the_tool_call_id_so_the_message_pairs_stay_valid():
    messages = [tool_message(i) for i in range(KEEP_TOOL_OUTPUTS + 1)]
    assert trim_tool_outputs(messages)[0].tool_call_id == "call-0"


def test_user_and_assistant_messages_are_never_trimmed():
    old = [Message(role="user", content="x" * 900) for _ in range(5)]
    messages = old + [tool_message(i) for i in range(KEEP_TOOL_OUTPUTS + 3)]
    assert trim_tool_outputs(messages)[:5] == old


def test_a_small_tool_result_is_left_alone_because_the_stub_would_not_be_shorter():
    messages = [tool_message(i, size=1) for i in range(KEEP_TOOL_OUTPUTS + 3)]
    assert trim_tool_outputs(messages) == messages
