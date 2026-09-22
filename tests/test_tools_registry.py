import pytest

from my_agent_crew.tools.registry import MAX_OUTPUT_CHARS, Tool, ToolError, ToolRegistry


def tool(name="t", run=None, requires_approval=False) -> Tool:
    async def default(args):
        return "ok"

    return Tool(name, "d", {"type": "object"}, run or default, requires_approval)


async def test_execute_returns_output_and_ok():
    reg = ToolRegistry([tool()])
    result = await reg.execute("t", {})
    assert (result.ok, result.output) == (True, "ok")


async def test_unknown_tool_is_an_error_result_not_an_exception():
    result = await ToolRegistry().execute("nope", {})
    assert result.ok is False and "nope" in result.output


async def test_tool_error_becomes_readable_failure():
    async def boom(args):
        raise ToolError("đường dẫn sai")

    result = await ToolRegistry([tool(run=boom)]).execute("t", {})
    assert result.ok is False and "đường dẫn sai" in result.output


async def test_unexpected_exception_is_contained():
    async def crash(args):
        raise KeyError("x")

    result = await ToolRegistry([tool(run=crash)]).execute("t", {})
    assert result.ok is False and "KeyError" in result.output


async def test_long_output_is_truncated_with_notice_that_fits_inside_the_cap():
    """The notice is part of what the model reads, so it is paid for out of the cap rather
    than added on top of it: a cap that can be overshot is not a cap."""

    async def big(args):
        return "x" * (MAX_OUTPUT_CHARS + 500)

    result = await ToolRegistry([tool(run=big)]).execute("t", {})
    assert result.ok and len(result.output) <= MAX_OUTPUT_CHARS
    assert "đã cắt bớt" in result.output


async def test_a_registry_can_carry_its_own_output_cap_and_keeps_it_when_narrowed():
    async def big(args):
        return "x" * 12000

    reg = ToolRegistry([tool(run=big), tool("other")], limit=16000)
    assert len((await reg.execute("t", {})).output) == 12000
    small = ToolRegistry([tool(run=big)], limit=100)
    cut = (await small.execute("t", {})).output
    assert len(cut) <= 100 and "đã cắt bớt" in cut
    assert reg.without("other").limit == 16000


async def test_a_summariser_rewrites_the_middle_of_a_long_text_output():
    async def big(args):
        return "MỞ ĐẦU. " + ("dòng nhật ký lặp lại. " * 3000) + " KẾT THÚC."

    async def summarise(prompt):
        return "ba nghìn dòng nhật ký giống nhau", 0.0004

    reg = ToolRegistry([tool(run=big)], limit=2000, summariser=summarise)
    result = await reg.execute("t", {})
    assert result.shaped_kind == "summary"
    assert result.output.startswith("MỞ ĐẦU.") and result.output.endswith("KẾT THÚC.")
    assert "ba nghìn dòng nhật ký giống nhau" in result.output
    # The summary was a model call like any other, so it is charged rather than absorbed.
    assert result.cost_usd == 0.0004 and result.metered is True


async def test_a_summariser_that_fails_leaves_the_output_cut_and_the_tool_answering():
    async def big(args):
        return "y" * 9000

    async def broken(prompt):
        raise RuntimeError("route down")

    result = await ToolRegistry([tool(run=big)], limit=2000, summariser=broken).execute("t", {})
    assert result.ok and result.shaped_kind == "cut"
    assert result.cost_usd is None and result.metered is False


async def test_a_narrowed_registry_keeps_the_summariser_its_parent_had():
    async def summarise(prompt):
        return "gọn", None

    reg = ToolRegistry([tool(), tool("other")], summariser=summarise)
    assert reg.without("other").summariser is summarise


def test_duplicate_registration_rejected():
    reg = ToolRegistry([tool()])
    with pytest.raises(ValueError):
        reg.register(tool())


def test_specs_and_describe_expose_approval_flag():
    reg = ToolRegistry([tool("w", requires_approval=True), tool("r")])
    assert reg.names() == ["w", "r"]
    assert [s.name for s in reg.specs()] == ["w", "r"]
    assert reg.describe()[0]["requires_approval"] is True
