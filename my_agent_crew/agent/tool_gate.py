"""Whether a tool call may run on its own or has to wait for a person.

The rules are ordered, and the order is the product: a question never skips, the ask
list beats the allow list, the allow list beats a supervised conversation, and only
then does autonomy (or a per-tool always-allow) decide."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store.models import Conversation
from my_agent_crew.texts import SHELL_ASK_REASON
from my_agent_crew.tools.ask_user import ASK_USER_TOOL_NAME
from my_agent_crew.tools.shell import SHELL_TOOL_NAME, ask_reason, deny_reason
from my_agent_crew.tools.shell_temp_paths import deletes_only_temp_paths

if TYPE_CHECKING:  # the loop owns the deps; importing it back would be a cycle
    from my_agent_crew.agent.loop import AgentDeps

logger = logging.getLogger(__name__)


def _tool_ask_reason(deps: AgentDeps, name: str, arguments: dict[str, Any]) -> str | None:
    """A tool that must always stop for a person says so itself: `schedule_create` is the
    first of these. Returned verbatim, never wrapped — the caller reads the tool's own
    words as-is, since no fixed pattern name applies here the way `SHELL_ASK_REASON` names
    one for shell.

    Fails closed: a reason that comes back empty, or a tool that crashes while writing it,
    still stops for a person — named by the tool alone — rather than letting the call
    skip the gate or take the turn down."""
    tool = deps.tools.get(name)
    if tool is None or tool.ask_reason is None:
        return None
    try:
        reason = tool.ask_reason(arguments)
    except Exception:
        logger.exception("ask_reason for %s crashed", name)
        return name
    return reason or name


def ask_reason_for(deps: AgentDeps, name: str, arguments: dict[str, Any]) -> str | None:
    """A shell command whose shape is on the ask list is approved even when the
    conversation is autonomous; every other call keeps the old rule.

    One shape is let through: an agent deleting a temp directory it made itself. That
    tripped the list on every cleanup and stalled unattended runs, while deleting nothing
    of the person's. The exemption only holds when every path the command names resolves
    inside a system temp root — see `deletes_only_temp_paths`.

    Checked before any of that: a tool with its own `ask_reason` always wins, since that
    reason exists precisely to outrank every waiver below it.
    """
    tool_reason = _tool_ask_reason(deps, name, arguments)
    if tool_reason is not None:
        return tool_reason
    if name != SHELL_TOOL_NAME:
        return None
    command = str(arguments.get("command", ""))
    reason = ask_reason(command, deps.settings.shell_ask_patterns)
    if reason and deletes_only_temp_paths(command):
        return None
    return reason


def ask_reason_text(deps: AgentDeps, name: str, arguments: dict[str, Any]) -> str:
    """The line a person reads beside the request saying why it stopped, or "" when
    nothing did. A tool's own reason is shown exactly as it wrote it; only the shell ask
    list's bare pattern is dressed up with `SHELL_ASK_REASON`. It follows from the call and
    the agent's list, so a request read back later is given it again rather than it being
    stored."""
    tool_reason = _tool_ask_reason(deps, name, arguments)
    if tool_reason is not None:
        return tool_reason
    pattern = ask_reason_for(deps, name, arguments)
    return SHELL_ASK_REASON.format(pattern=pattern) if pattern else ""


def needs_decision(
    conv: Conversation, name: str, reason: str | None, allowed: bool = False
) -> bool:
    """Whether this call stops the turn to ask a person, in strict order:

    1. A question never skips. Autonomy means "do not ask me to authorise your tools",
       not "never speak to me"; a question that approved itself would be answered by
       nobody and tell the agent nothing.
    2. A command matching the ask list pauses regardless. That guard is additive, and it
       sits above the allow list on purpose: a person who names `rm -rf` as dangerous and
       `git` as routine means `git reset --hard` to ask, not to run.
    3. A command matching the allow list runs, autonomous or not. This is the point of
       the list — it lets a supervised agent get on with the routine parts of its job.
    4. Otherwise the old rule: autonomy, or a tool the person said to always allow.
    """
    if name == ASK_USER_TOOL_NAME:
        return True
    if reason:
        return True
    if allowed:
        return False
    return not conv.autonomous and name not in conv.auto_approve


def allowed_by_pattern(deps: AgentDeps, name: str, arguments: dict[str, Any]) -> bool:
    """A shell command whose shape the person marked routine. Only shell: every other
    tool is allowed per tool, through `auto_approve`, not per argument."""
    if name != SHELL_TOOL_NAME:
        return False
    command = str(arguments.get("command", ""))
    return ask_reason(command, deps.settings.shell_allow_patterns) is not None


def pauses_for_a_person(deps: AgentDeps, conv: Conversation, call: ToolCall) -> bool:
    """A call whose arguments never parsed asks nobody: a person would be shown nothing to
    decide on, and it is answered with the parse error whatever they chose."""
    if call.invalid:
        return False
    tool = deps.tools.get(call.name)
    denied = deny_reason(call.arguments, deps.settings.shell_deny_patterns)
    if tool is None or not tool.requires_approval or (call.name == SHELL_TOOL_NAME and denied):
        return False
    return needs_decision(
        conv,
        call.name,
        ask_reason_for(deps, call.name, call.arguments),
        allowed_by_pattern(deps, call.name, call.arguments),
    )
