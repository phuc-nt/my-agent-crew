from my_agent_crew.agent.context_trim import (
    KEEP_TOOL_OUTPUTS,
    PINNED_TOOLS,
    TRIM_BLOCK,
    trim_tool_outputs,
)
from my_agent_crew.llm.types import Message
from my_agent_crew.tools.delegate import DELEGATE_TOOL_NAME


def tool_message(index: int, size: int = 500, name: str = "workspace_read") -> Message:
    return Message(role="tool", content=f"{index}" * size, tool_call_id=f"call-{index}", name=name)


def test_short_history_is_returned_unchanged():
    messages = [Message(role="user", content="hi"), tool_message(1)]
    assert trim_tool_outputs(messages) == messages


def stubbed(messages) -> int:
    return sum(m.content.startswith("[kết quả cũ") for m in trim_tool_outputs(messages))


def test_only_tool_results_beyond_the_window_become_stubs():
    messages = [tool_message(i) for i in range(KEEP_TOOL_OUTPUTS + 5)]
    trimmed = trim_tool_outputs(messages)
    assert [m.content.startswith("[kết quả cũ") for m in trimmed[:TRIM_BLOCK]] == [
        True
    ] * TRIM_BLOCK
    assert trimmed[TRIM_BLOCK:] == messages[TRIM_BLOCK:]
    assert "500 ký tự" in trimmed[0].content


def test_stubs_advance_a_block_at_a_time_so_the_prompt_prefix_rarely_changes():
    """A window that slid by one rewrote an early message on every step, and a provider's
    prompt cache then missed on every step. The set of stubs now changes once per block,
    and what is kept in full stays between one and two blocks."""
    counts = [stubbed([tool_message(i) for i in range(n)]) for n in range(KEEP_TOOL_OUTPUTS + 31)]
    assert counts[: KEEP_TOOL_OUTPUTS + 1] == [0] * (KEEP_TOOL_OUTPUTS + 1)
    assert counts[KEEP_TOOL_OUTPUTS + 1 : KEEP_TOOL_OUTPUTS + 11] == [TRIM_BLOCK] * TRIM_BLOCK
    assert counts[KEEP_TOOL_OUTPUTS + 11] == 2 * TRIM_BLOCK
    assert len(set(counts)) == 4  # 0, 10, 20, 30: never a value in between
    kept = [n - c for n, c in enumerate(counts) if n > KEEP_TOOL_OUTPUTS]
    assert min(kept) == TRIM_BLOCK + 1 and max(kept) == KEEP_TOOL_OUTPUTS


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


def test_a_delegate_result_stays_in_full_however_old_it_is():
    """The master asks Pong, then the coach, then comes back to Pong's topic: the answer
    Pong gave is what the master needs, and it must not have turned into a stub."""
    assert DELEGATE_TOOL_NAME in PINNED_TOOLS
    answer = tool_message(0, name=DELEGATE_TOOL_NAME)
    messages = [answer, *[tool_message(i) for i in range(1, KEEP_TOOL_OUTPUTS + 6)]]
    trimmed = trim_tool_outputs(messages)
    assert trimmed[0] == answer
    assert trimmed[1].content.startswith("[kết quả cũ")  # the window is not widened for it
    assert trimmed[-TRIM_BLOCK - 1 :] == messages[-TRIM_BLOCK - 1 :]
