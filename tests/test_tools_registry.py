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


async def test_long_output_is_truncated_with_notice():
    async def big(args):
        return "x" * (MAX_OUTPUT_CHARS + 500)

    result = await ToolRegistry([tool(run=big)]).execute("t", {})
    assert result.ok and len(result.output) < MAX_OUTPUT_CHARS + 100
    assert "500" in result.output


def test_duplicate_registration_rejected():
    reg = ToolRegistry([tool()])
    with pytest.raises(ValueError):
        reg.register(tool())


def test_specs_and_describe_expose_approval_flag():
    reg = ToolRegistry([tool("w", requires_approval=True), tool("r")])
    assert reg.names() == ["w", "r"]
    assert [s.name for s in reg.specs()] == ["w", "r"]
    assert reg.describe()[0]["requires_approval"] is True
