"""A stored tool message carries no flag for success, so the web thread tells a refused or a
failed call from a finished one by how its reply opens (`web/src/lib/tool-reply.ts`). Nothing
at runtime reads both sides, so this is what notices one of them being reworded alone."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from my_agent_crew.texts import (
    APPROVAL_CALL_MISMATCH,
    DENIED_TOOL,
    EXPIRED_TOOL,
    FORK_CALL_NOT_RUN,
    INTERRUPTED_TOOL,
    LOOP_HALTED_TOOL,
    STEPS_HALTED_TOOL,
    TOOL_ARGS_CUT_OFF,
    TOOL_ARGS_INVALID,
    TOOL_FAILED,
    UNKNOWN_TOOL,
)
from my_agent_crew.texts_kit import TOOL_BLOCKED_BY_HOOK
from my_agent_crew.tools.registry import Tool, ToolError, ToolRegistry

SOURCE = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "tool-reply.ts"
# Every sentence the server fails a call with that is a sentence and nothing more, in the
# order the web lists their openings: the registry's three, arguments that were not valid or
# were cut off, a turn out of steps, a turn stopped for repeating itself, an id approved for
# another call, a conversation branched before the call ran, a run cut before it answered.
WRITTEN = [
    TOOL_FAILED,
    UNKNOWN_TOOL,
    TOOL_BLOCKED_BY_HOOK,
    TOOL_ARGS_INVALID,
    TOOL_ARGS_CUT_OFF,
    STEPS_HALTED_TOOL,
    LOOP_HALTED_TOOL,
    APPROVAL_CALL_MISMATCH,
    FORK_CALL_NOT_RUN,
    INTERRUPTED_TOOL,
]


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def fixed_words(template: str) -> str:
    """What every reply made from `template` opens with: the words before the first value
    filled in, and the whole sentence when none is."""
    return template.partition("{")[0]


def web_constant(name: str) -> str:
    """A string the web reads a reply with, taken from its source."""
    found = re.findall(rf'^const {name} = "([^"]+)";$', _source(), re.MULTILINE)
    assert len(found) == 1, f"{name} is no longer a one-line string constant in {SOURCE.name}"
    return found[0]


def web_failed() -> list[str]:
    """The openings the web reads as a failure, in the order it lists them."""
    listed = re.findall(r"^const FAILED = \[(.+?)\];$", _source(), re.MULTILINE | re.DOTALL)
    assert len(listed) == 1, f"FAILED is no longer a list of strings in {SOURCE.name}"
    return re.findall(r'"([^"]+)"', listed[0])


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
    denied = web_constant("DENIED")
    assert DENIED_TOOL.startswith(denied) and EXPIRED_TOOL.startswith(denied)


def test_each_opening_the_web_reads_as_a_failure_is_how_the_server_words_one():
    """Exactly the words before the first thing filled in, and the whole sentence when nothing
    is: a shorter opening would catch replies that are not failures, a longer one could never
    match. Two sentences that open alike before their first value share the one opening."""
    assert web_failed() == list(dict.fromkeys(fixed_words(template) for template in WRITTEN))
    whole = [template for template in WRITTEN if "{" not in template]
    for opening in web_failed():
        # One that stops before a value ends with the space the value follows, so it cannot
        # match a longer word; one that stops nowhere is a sentence the server writes whole.
        assert len(opening) > 8 and (opening.endswith(" ") or opening in whole), opening
    assert not any(opening.startswith(web_constant("DENIED")) for opening in web_failed())


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
    failed = web_failed()
    raised, crashed, unknown, blocked = failed[0], failed[0], failed[1], failed[2]
    for name, opening in (
        ("refuses", raised),
        ("crashes", crashed),
        ("no_such_tool", unknown),
        ("stopped", blocked),
    ):
        result = await registry.execute(name, {})
        assert not result.ok and result.output.startswith(opening), name
    done = await registry.execute("answers", {})
    assert done.ok and not any(done.output.startswith(opening) for opening in failed)
