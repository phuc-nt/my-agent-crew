"""A stored tool message carries no flag for success, so the web thread tells a refused or a
failed call from a finished one by how its reply opens (`web/src/lib/tool-reply.ts`). Nothing
at runtime reads both sides, so this is what notices one of them being reworded alone."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from my_agent_crew.texts import DENIED_TOOL, EXPIRED_TOOL, TOOL_FAILED, UNKNOWN_TOOL
from my_agent_crew.texts_kit import TOOL_BLOCKED_BY_HOOK
from my_agent_crew.tools.registry import Tool, ToolError, ToolRegistry

SOURCE = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "tool-reply.ts"


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def _denied() -> str:
    [opening] = re.findall(r'^const DENIED = "([^"]+)";$', _source(), re.MULTILINE)
    return opening


def _failed() -> list[str]:
    [listed] = re.findall(r"^const FAILED = \[(.+)\];$", _source(), re.MULTILINE)
    return re.findall(r'"([^"]+)"', listed)


class _Blocker:
    """A kit hook that stops the one call named `stopped`."""

    async def before(self, name: str, args: dict[str, Any]) -> str | None:
        return "ngoài giờ" if name == "stopped" else None

    async def after(self, name: str, args: dict[str, Any], ok: bool, output: str) -> str:
        return ""


async def _refuses(args: dict[str, Any]) -> str:
    raise ToolError("không ghi được")


async def _crashes(args: dict[str, Any]) -> str:
    raise ValueError("embedded null byte")


async def _answers(args: dict[str, Any]) -> str:
    return "xong"


def test_the_web_tells_a_refusal_by_the_opening_both_refusals_share():
    assert DENIED_TOOL.startswith(_denied()) and EXPIRED_TOOL.startswith(_denied())


def test_each_opening_the_web_reads_as_a_failure_is_how_the_registry_words_one():
    """Exactly the words before the first thing filled in: a shorter opening would catch
    replies that are not failures, a longer one could never match."""
    written = [TOOL_FAILED, UNKNOWN_TOOL, TOOL_BLOCKED_BY_HOOK]
    assert _failed() == [template.partition("{")[0] for template in written]
    assert all(opening.endswith(" ") and len(opening) > 8 for opening in _failed())
    assert not any(opening.startswith(_denied()) for opening in _failed())


async def test_every_reply_the_registry_fails_a_call_with_opens_as_the_web_expects():
    tools = [
        Tool(name, "", {"type": "object", "properties": {}}, run)
        for name, run in (
            ("refuses", _refuses),
            ("crashes", _crashes),
            ("stopped", _answers),
            ("answers", _answers),
        )
    ]
    registry = ToolRegistry(tools, hooks=_Blocker())
    raised, crashed, unknown, blocked = _failed()[0], _failed()[0], _failed()[1], _failed()[2]
    for name, opening in (
        ("refuses", raised),
        ("crashes", crashed),
        ("no_such_tool", unknown),
        ("stopped", blocked),
    ):
        result = await registry.execute(name, {})
        assert not result.ok and result.output.startswith(opening), name
    done = await registry.execute("answers", {})
    assert done.ok and not any(done.output.startswith(opening) for opening in _failed())
