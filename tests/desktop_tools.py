"""What the tests of the desktop tools share: the four tools of one agent on the stand-in
helper, and a way to read what an answer holds inside its fence and outside it."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from my_agent_crew import texts_desktop as t
from my_agent_crew.browser.fence import CUT_ROOM
from my_agent_crew.config_desktop import COMPUTER_ON, DesktopSettings
from my_agent_crew.desktop.client import DesktopClient
from my_agent_crew.desktop.kit import ACT, OBSERVE, SCREENSHOT, STATE
from my_agent_crew.desktop.tools import build_desktop_tools
from my_agent_crew.tools.registry import Tool, ToolError, ToolResult
from tests.desktop_helper import FakeHelper

FENCE = re.compile(r"^<<<MANHINH ([0-9a-f]{16})\n(.*)\nMANHINH \1>>>$", re.S | re.M)
NOTES = ("Notes",)


class Desk:
    """One agent's desktop tools, called by name."""

    def __init__(self, tools: list[Tool]) -> None:
        self.tools = {tool.name: tool for tool in tools}

    async def call(self, tool: str, /, **args: Any) -> str:
        answer = await self.tools[tool].run(args)
        return answer.output if isinstance(answer, ToolResult) else answer

    async def refused(self, tool: str, /, **args: Any) -> str:
        """The sentence a call is refused with; the test fails when it is carried out."""
        try:
            answer = await self.call(tool, **args)
        except ToolError as exc:
            return str(exc)
        raise AssertionError(f"{tool} was carried out: {answer}")

    async def state(self) -> str:
        return await self.call(STATE)

    async def screenshot(self, **args: Any) -> str:
        return await self.call(SCREENSHOT, **args)

    async def observe(self, **args: Any) -> str:
        return await self.call(OBSERVE, **args)

    async def act(self, **args: Any) -> str:
        return await self.call(ACT, **args)


def desk_of(
    helper: FakeHelper | Path,
    workspace: Path,
    apps: tuple[str, ...] = NOTES,
    *,
    limit: int = 20_000,
    **own: Any,
) -> Desk:
    """The tools of an agent whose file says `computer: on` and gives it `apps`. A path in
    place of a helper is a socket nobody listens on. The workspace is there, as a running
    agent's always is."""
    workspace.mkdir(parents=True, exist_ok=True)
    path = helper.path if isinstance(helper, FakeHelper) else helper
    settings = DesktopSettings(socket=str(path), mode=COMPUTER_ON, apps=tuple(apps))
    return Desk(
        build_desktop_tools(DesktopClient(path), "coach", settings, workspace, limit, **own)
    )


def parts(answer: str) -> tuple[str, str]:
    """What an answer says outside its fence and what it holds inside."""
    match = FENCE.search(answer)
    assert match, answer
    return answer[: match.start()] + answer[match.end() :], match.group(2)


def refusal_of(refusal: str) -> tuple[str, str]:
    """The sentence a refusal says, and what the helper said that stands fenced beneath it:
    nothing else, and nothing of the helper's outside the fence."""
    match = FENCE.search(refusal)
    if match is None:
        assert "\n" not in refusal and "MANHINH" not in refusal, refusal
        return refusal, ""
    opening, closing = t.SCREEN_OPEN, t.SCREEN_CLOSE
    nonce = match.group(1)
    said = t.SCREEN_FENCE.format(
        opening=opening.format(nonce=nonce), closing=closing.format(nonce=nonce)
    )
    sentence = refusal[: match.start()].removesuffix(f"\n{said}\n")
    assert refusal == "\n".join([sentence, said, match.group(0)]), refusal
    return sentence, match.group(2)


def fits(answer: str, cap: int, used: int = 0) -> bool:
    """Whether an answer comes whole through the registry's cap: no fence, or a closed one
    with room left for the widest mark of a cut."""
    if "<<<MANHINH" not in answer:
        return True
    return FENCE.search(answer) is not None and used + len(answer) + CUT_ROOM <= cap
