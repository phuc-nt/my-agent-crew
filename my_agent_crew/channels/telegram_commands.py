"""Message syntax the Telegram channel answers itself, so the model never sees it (a
"/reset" that reaches the model costs a turn and a bootstrap ritual). Slash commands are
a small pick of what chat bots usually offer: open a new conversation, help, status,
tools, and approve/deny for a tool waiting on the web UI. `MENU` is registered with
Telegram at startup so the client shows these instead of whatever the previous bot code
registered."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, tzinfo
from typing import TYPE_CHECKING

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import TELEGRAM
from my_agent_crew.agents.kit_commands import Command
from my_agent_crew.store.models import AWAITING_APPROVAL

if TYPE_CHECKING:
    from my_agent_crew.channels.telegram_channel import TelegramChannel

NEW_CONVERSATION = ("new", "reset", "start")
BOT_COMMANDS = ("help",)  # answered by the bot about itself, not about the conversation
MENU = tuple((name, texts.TELEGRAM_COMMANDS[name]) for name in texts.TELEGRAM_COMMANDS)
_COMMAND = re.compile(r"^/([a-z0-9_:.-]+)(?:@\w+)?(?:\s|$)")
# What Telegram accepts in its command menu; a kit command outside this shape still works
# when typed, it just is not listed.
_MENU_NAME = re.compile(r"^[a-z0-9_]{1,32}$")
MIN_MENU_DESCRIPTION_CHARS = 3


def parse_command(text: str) -> str | None:
    """`/status`, `/status@bot` and `/status extra` all name the command `status`; a path
    or a sentence starting with "/" is not a command."""
    match = _COMMAND.match(text.strip())
    return match.group(1) if match else None


def is_builtin(command: str) -> bool:
    return command in texts.TELEGRAM_COMMANDS or command in NEW_CONVERSATION


def menu_for(commands: Sequence[Command]) -> list[tuple[str, str]]:
    """The built-in menu plus the kit commands Telegram can list."""
    extra = [
        (c.name, c.description)
        for c in commands
        if _MENU_NAME.match(c.name)
        and len(c.description) >= MIN_MENU_DESCRIPTION_CHARS
        and not is_builtin(c.name)
    ]
    return [*MENU, *extra]


async def answer_command(channel: TelegramChannel, command: str) -> str:
    if command in NEW_CONVERSATION:
        channel.open_conversation()
        return texts.TELEGRAM_NEW_CONVERSATION
    if command == "help":
        return help_text(channel.deps.agent.commands)
    if command == "status":
        return status_text(channel)
    if command == "tools":
        names = channel.deps.tools.names()
        return texts.TELEGRAM_TOOLS.format(count=len(names), names="\n".join(names))
    if command in ("approve", "deny"):
        return await decide(channel, approve=command == "approve")
    return texts.TELEGRAM_UNKNOWN_COMMAND.format(command=command)


def bot_answers(command: str) -> bool:
    """Commands the bot answers in its own voice rather than as the agent's reply."""
    return command in BOT_COMMANDS


def help_text(extra: Sequence[Command] = ()) -> str:
    """The built-in commands, then every kit command the agent has, listed or not."""
    lines = [*MENU]
    lines += [
        (c.name, c.description or texts.KIT_COMMAND_NO_DESCRIPTION)
        for c in extra
        if not is_builtin(c.name)
    ]
    return "\n".join(
        texts.TELEGRAM_HELP_LINE.format(command=name, description=description)
        for name, description in lines
    )


def local_clock(stamp: str, zone: tzinfo | None = None) -> str:
    """Runs are stamped in UTC; the person reads the chat in their own zone, so the
    status shows `HH:MM` local (the machine's zone unless one is given)."""
    return datetime.fromisoformat(stamp).astimezone(zone).strftime("%H:%M")


def status_text(channel: TelegramChannel) -> str:
    conv, deps = channel.conversation(), channel.deps
    turns = sum(1 for stored in deps.store.history(conv.id) if stored.message.role == "user")
    if conv.status == AWAITING_APPROVAL:
        pending = deps.store.approvals.pending(conv.id)
        state = texts.TELEGRAM_STATE_AWAITING.format(name=pending.tool_name if pending else "?")
    elif conv.over_budget:
        state = texts.TELEGRAM_STATE_OVER_BUDGET
    else:
        state = texts.TELEGRAM_STATE_IDLE
    runs = [run for run in channel.hub.recent() if run.conversation_id == conv.id]
    run = texts.TELEGRAM_RUN_NONE
    if runs:
        last = runs[0]
        run = texts.TELEGRAM_RUN.format(
            status=last.status,
            steps=len(last.steps),
            started=local_clock(last.started_at, deps.settings.zone),
        )
    return texts.TELEGRAM_STATUS.format(
        title=conv.title,
        turns=turns,
        spent=conv.spent_usd,
        cap=conv.cost_cap_usd,
        routes=", ".join(f"{r.provider}:{r.model}" for r in deps.chain.routes),
        state=state,
        run=run,
    )


async def decide(channel: TelegramChannel, approve: bool) -> str:
    """Resolves the pending approval of today's conversation and runs the rest of the
    turn like a normal message, so the answer comes back to the chat."""
    conv, deps = channel.conversation(), channel.deps
    pending = deps.store.approvals.pending(conv.id)
    if conv.status != AWAITING_APPROVAL or pending is None:
        return texts.TELEGRAM_NO_APPROVAL
    events = channel.inbound.decide(conv.id, pending.id, approve, source=TELEGRAM)
    return await channel.answer(events)
