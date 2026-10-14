"""What the desktop tools of one agent share: the way to the helper, the agent's own settings,
and what the agent was last shown.

The tools are built for every agent whose file says `computer: on`, whether a helper runs on
the machine or not: the helper is looked for at each call, so installing it needs no restart
and its absence is one plain sentence instead of a missing tool.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from my_agent_crew import texts_desktop as t
from my_agent_crew.agent.turn_context import turn_conversation_id
from my_agent_crew.browser.fence import FAILED_ROOM
from my_agent_crew.browser.kit import one_line
from my_agent_crew.browser.policy import AskWords
from my_agent_crew.config_desktop import DesktopSettings
from my_agent_crew.desktop.client import DesktopClient, DesktopError
from my_agent_crew.desktop.policy import app_allowed
from my_agent_crew.desktop.report import with_data
from my_agent_crew.desktop.seen import Shown
from my_agent_crew.tools.registry import Tool, ToolError

STATE, SCREENSHOT = "computer_state", "computer_screenshot"
OBSERVE, ACT = "computer_observe", "computer_act"
DESKTOP_TOOLS = (STATE, SCREENSHOT, OBSERVE, ACT)
# Whose frames a call outside any conversation keeps: a script job has no conversation.
JOB_OWNER = "job"
DETAIL_CHARS, NAME_CHARS = 200, 80
# How many conversations' last frames are remembered.
OWNERS_KEPT = 64
# The shape of the helper's codes. A code this side does not know stands outside the fence,
# so one of another shape is not named.
CODE = re.compile(r"[a-z][a-z0-9_:]{0,39}")


def sentence(error: DesktopError) -> str:
    """This program's sentence for a refusal of the helper, with no word of the helper's own."""
    known = t.HELPER_ERRORS.get(error.code)
    if known is not None:
        return known.format(detail="").strip()
    code = error.code if CODE.fullmatch(error.code) else "?"
    return t.HELPER_UNKNOWN.format(code=code, detail="").strip()


def words_of(error: DesktopError) -> str:
    """The helper's own words, for the codes whose sentence leaves room for them."""
    detail = one_line(error.detail, DETAIL_CHARS)
    room = "{detail}" in t.HELPER_ERRORS.get(error.code, t.HELPER_UNKNOWN)
    return t.HELPER_DETAIL.format(detail=detail) if detail and room else ""


def said(error: DesktopError) -> str:
    """A refusal of the helper as a person reads it on the owner's screens: one line, the
    helper's own words after the sentence."""
    return " ".join(part for part in (sentence(error), words_of(error)) if part)


def refused(limit: int, error: DesktopError) -> ToolError:
    """A refusal of the helper as an agent is told it. The helper's own words stand between
    fence lines under the sentence, or are left out where the cap has no room for them."""
    words = words_of(error)
    if not words:
        return ToolError(sentence(error))
    return ToolError(with_data(limit, sentence(error), words, used=FAILED_ROOM))


@dataclass(frozen=True)
class DesktopTool(Tool):
    """A tool that comes with an agent's `computer` key instead of from its own list."""

    def to_dict(self) -> dict[str, Any]:
        # For the owner's screens: it follows the agent's `computer` key, not its allow-list.
        return {**super().to_dict(), "with_desktop": True}


@dataclass
class Kit:
    client: DesktopClient
    agent_id: str
    # The agent's own: whether it may use the desktop at all, and on which applications.
    settings: DesktopSettings
    workspace: Path
    # What the registry cuts a tool's answer at: an outline is sized to fit under it whole.
    limit: int
    # The chain pictures go to, when the machine has one.
    vision: Any = None
    # The agent's words that stop a typed text for a person.
    ask: AskWords = field(default_factory=lambda: AskWords(()))
    # Where the agent's file tools may write; its pictures go under the first of them.
    write_paths: tuple[str, ...] = ()
    # The last outline the helper gave this agent, and the conversation that was shown it.
    # One for the agent and not one a conversation: the helper keeps only its newest, so
    # what another conversation was shown before it names nothing any more.
    seen: tuple[str, Shown] | None = None
    # The last frame each conversation was given, so an unchanged screen costs no picture.
    frames: dict[str, str] = field(default_factory=dict)

    @property
    def apps(self) -> tuple[str, ...]:
        return self.settings.apps

    def owner(self) -> str:
        return turn_conversation_id() or JOB_OWNER

    def allows(self, name: Any = "", bundle_id: Any = "") -> bool:
        """Whether the application the helper names is one of the agent's own."""
        name = name if isinstance(name, str) else ""
        bundle_id = bundle_id if isinstance(bundle_id, str) else ""
        return app_allowed(self.apps, name, bundle_id)

    def listed(self) -> str:
        return ", ".join(self.apps)

    async def ask_helper(self, cmd: str, **args: Any) -> dict:
        """One request, its refusal told as a sentence the model can act on."""
        try:
            return await self.client.request(cmd, **args)
        except DesktopError as exc:
            raise refused(self.limit, exc) from exc

    def showed(self, shown: Shown | None) -> None:
        """The outline this conversation was just shown; None once the helper made a new
        one that nobody was shown yet."""
        self.seen = None if shown is None else (self.owner(), shown)

    def shown(self) -> Shown | None:
        """What this conversation was last shown, while that is still the helper's newest."""
        if self.seen is None or self.seen[0] != self.owner():
            return None
        return self.seen[1]

    def gave(self, frame_id: str) -> None:
        self.frames.pop(self.owner(), None)
        self.frames[self.owner()] = frame_id
        while len(self.frames) > OWNERS_KEPT:
            self.frames.pop(next(iter(self.frames)))
