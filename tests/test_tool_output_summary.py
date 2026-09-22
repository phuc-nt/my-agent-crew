"""Long text output keeps its opening and its ending, and has its middle summarised.

The point of every test here is the same one: a summary is an improvement on a cut, so
anything that goes wrong with it must land back on the cut rather than on the caller.
"""

import pytest

from my_agent_crew.tools.output_shaping import shape_output_async
from my_agent_crew.tools.output_summary import budget, split, summarise

LIMIT = 2000


def long_text(chars: int) -> str:
    """Text with a distinct opening and ending, so a test can say which part survived."""
    filler = "phần giữa lặp đi lặp lại. " * (chars // 26 + 1)
    return "MỞ ĐẦU: báo cáo tháng chín.\n" + filler[:chars] + "\nKẾT: tổng cộng 1234 đồng."


def answering(text: str, cost_usd: float | None = 0.0001):
    async def run(prompt: str) -> tuple[str, float | None]:
        run.prompt = prompt  # type: ignore[attr-defined]
        return text, cost_usd

    return run


@pytest.mark.asyncio
async def test_the_opening_and_the_ending_survive_word_for_word():
    text = long_text(20_000)
    result = await summarise(text, LIMIT, answering("Tóm tắt phần giữa."))
    assert result is not None
    assert result.text.startswith("MỞ ĐẦU: báo cáo tháng chín.")
    assert result.text.endswith("KẾT: tổng cộng 1234 đồng.")
    assert "Tóm tắt phần giữa." in result.text
    assert len(result.text) <= LIMIT


@pytest.mark.asyncio
async def test_the_summary_is_labelled_so_it_is_not_read_as_the_source():
    result = await summarise(long_text(20_000), LIMIT, answering("Ba đơn hàng."))
    assert result is not None
    assert "không phải nguyên văn" in result.text
    assert "lại là nguyên văn" in result.text


@pytest.mark.asyncio
async def test_the_prompt_tells_the_model_to_keep_the_numbers():
    summariser = answering("xong")
    await summarise(long_text(20_000), LIMIT, summariser)
    assert "giữ NGUYÊN mọi con số" in summariser.prompt  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_a_model_that_fails_leaves_the_caller_with_a_plain_cut():
    async def broken(prompt: str) -> tuple[str, float | None]:
        raise RuntimeError("route down")

    assert await summarise(long_text(20_000), LIMIT, broken) is None


@pytest.mark.asyncio
async def test_an_empty_answer_is_not_worth_showing():
    assert await summarise(long_text(20_000), LIMIT, answering("   ")) is None


@pytest.mark.asyncio
async def test_without_a_summariser_nothing_is_attempted():
    assert await summarise(long_text(20_000), LIMIT, None) is None


@pytest.mark.asyncio
async def test_a_cap_too_small_for_three_parts_is_left_to_the_cut():
    assert await summarise(long_text(20_000), 300, answering("x")) is None


@pytest.mark.asyncio
async def test_a_model_writing_past_its_budget_still_comes_back_under_the_cap():
    result = await summarise(long_text(20_000), LIMIT, answering("dài " * 5000))
    assert result is not None and len(result.text) <= LIMIT


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [600, 1000, 2000, 8000])
@pytest.mark.parametrize("answer", ["ngắn", "vừa phải " * 50, "dài " * 5000])
async def test_a_summarised_output_is_never_longer_than_the_cap(limit: int, answer: str):
    result = await summarise(long_text(60_000), limit, answering(answer))
    assert result is None or len(result.text) <= limit


@pytest.mark.asyncio
async def test_what_the_summary_cost_is_reported_so_it_can_be_charged():
    result = await summarise(long_text(20_000), LIMIT, answering("xong", cost_usd=0.002))
    assert result is not None and result.cost_usd == 0.002


def test_the_verbatim_shares_are_sized_from_the_cap_not_from_the_text():
    head, middle, tail = split(long_text(50_000), LIMIT)
    assert len(head) == int(LIMIT * 0.4)
    assert len(tail) == int(LIMIT * 0.2)
    assert len(middle) > 40_000
    assert budget(LIMIT) > 0


@pytest.mark.asyncio
async def test_json_is_shaped_structurally_and_never_sent_to_a_model():
    """Numbers are the whole point of a JSON output, so it never reaches a paraphrase."""

    async def never(prompt: str) -> tuple[str, float | None]:
        raise AssertionError("JSON must not be summarised")

    text = '{"ledger": ' + str([{"id": i, "amount": 1000 + i} for i in range(400)]) + "}"
    text = text.replace("'", '"')
    shaped = await shape_output_async(text, LIMIT, never)
    assert shaped.kind == "json"


@pytest.mark.asyncio
async def test_a_shaped_text_output_says_it_was_summarised_and_what_it_cost():
    shaped = await shape_output_async(long_text(20_000), LIMIT, answering("gọn", cost_usd=0.003))
    assert shaped.kind == "summary"
    assert shaped.cost_usd == 0.003
    assert shaped.original_chars > 20_000


@pytest.mark.asyncio
async def test_an_output_that_already_fits_is_never_summarised():
    async def never(prompt: str) -> tuple[str, float | None]:
        raise AssertionError("a short output must be left alone")

    shaped = await shape_output_async("ngắn", LIMIT, never)
    assert shaped.kind == "none" and shaped.text == "ngắn"
