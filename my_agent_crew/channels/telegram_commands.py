"""Message syntax the Telegram channel answers itself, so the model never sees it (a
"/reset" that reaches the model costs a turn and a bootstrap ritual). Slash commands are
a small pick of what chat bots usually offer: open a new conversation, help, status,
tools, the agents on the bot, and approve/deny for a tool waiting on the web UI. `MENU`
is registered with Telegram at startup so the client shows these instead of whatever the
previous bot code registered. `@<agent id>` at the start of a message picks an agent when
one bot serves several."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import TELEGRAM
from my_agent_crew.store.models import AWAITING_APPROVAL

if TYPE_CHECKING:
    from my_agent_crew.channels.telegram_channel import TelegramChannel

NEW_CONVERSATION = ("new", "reset", "start")
CHANNEL_COMMANDS = ("help", "agents")  # answered by the bot, not by an agent
MENU = tuple((name, texts.TELEGRAM_COMMANDS[name]) for name in texts.TELEGRAM_COMMANDS)
_COMMAND = re.compile(r"^/([a-z_]+)(?:@\w+)?(?:\s|$)")
_MENTION = re.compile(r"^@([A-Za-z0-9_-]+)(?:\s+|$)")


def parse_command(text: str) -> str | None:
    """`/status`, `/status@bot` and `/status extra` all name the command `status`; a path
    or a sentence starting with "/" is not a command."""
    match = _COMMAND.match(text.strip())
    return match.group(1) if match else None


def parse_mention(text: str) -> tuple[str | None, str]:
    """`@pong hỏi gì` → ("pong", "hỏi gì"); `@Pong` alone → ("pong", ""); no leading
    mention → (None, text). Agent ids are lower-case, so the mention is lowered too."""
    match = _MENTION.match(text.strip())
    if not match:
        return None, text
    return match.group(1).lower(), text.strip()[match.end() :].strip()


async def route_mention(channel: TelegramChannel, text: str) -> tuple[str | None, str, bool]:
    """Resolves who a message is for. Returns the agent id, the text left after the
    mention, and whether the message named that agent itself — `/new` needs to tell "cut
    this agent" from "cut the whole chat". `(None, "", False)` means the channel already
    answered: an unknown agent id, or a bare `@id` that only switches. The pick is
    remembered for the messages that follow."""
    mention, text = parse_mention(text) if channel.shared else (None, text)
    if mention is None:
        return channel.current_agent(), text, False
    if mention not in channel.agents:
        unknown = texts.TELEGRAM_AGENT_UNKNOWN.format(
            agent_id=mention, agents=channel.agents_text()
        )
        await channel.say(unknown)
        return None, "", False
    channel.remember_agent(mention)
    if not text:
        name = channel.agents[mention].agent.name
        await channel.say(texts.TELEGRAM_AGENT_SWITCHED.format(name=name, agent_id=mention))
        return None, "", False
    return mention, text, True


async def answer_command(
    channel: TelegramChannel, agent_id: str, command: str, addressed: bool = False
) -> str:
    if command in NEW_CONVERSATION:
        return open_conversations(channel, agent_id, addressed)
    if command == "help":
        return help_text(channel)
    if command == "agents":
        return channel.agents_text()
    if command == "status":
        return status_text(channel, agent_id)
    if command == "tools":
        names = channel.agents[agent_id].tools.names()
        return texts.TELEGRAM_TOOLS.format(count=len(names), names="\n".join(names))
    if command in ("approve", "deny"):
        return await decide(channel, agent_id, approve=command == "approve")
    return texts.TELEGRAM_UNKNOWN_COMMAND.format(command=command)


def bot_answers(channel: TelegramChannel, command: str, addressed: bool) -> bool:
    """Commands the bot answers in its own voice, with no agent prefix: the ones about the
    bot itself, and a bare `/new` on a shared bot, which acts on every agent at once."""
    return command in CHANNEL_COMMANDS or (
        command in NEW_CONVERSATION and channel.shared and not addressed
    )


def open_conversations(channel: TelegramChannel, agent_id: str, addressed: bool) -> str:
    """A plain `/new` cuts every agent on the bot: the chat is one window, so a person who
    asks for a fresh start means the window, not whichever agent happens to be current.
    `@pong /new` names an agent and cuts only that one."""
    if addressed or not channel.shared:
        channel.open_conversation(agent_id)
        if not channel.shared:
            return texts.TELEGRAM_NEW_CONVERSATION
        name = channel.agents[agent_id].agent.name
        return texts.TELEGRAM_NEW_CONVERSATION_ONE.format(name=name)
    for one in channel.agents:
        channel.open_conversation(one)
    names = ", ".join(deps.agent.name for deps in channel.agents.values())
    return texts.TELEGRAM_NEW_CONVERSATION_ALL.format(agents=names)


def help_text(channel: TelegramChannel | None = None) -> str:
    lines = "\n".join(
        texts.TELEGRAM_HELP_LINE.format(command=name, description=description)
        for name, description in MENU
    )
    if channel is not None and channel.shared:
        return f"{lines}\n\n{channel.agents_text()}"
    return lines


def status_text(channel: TelegramChannel, agent_id: str) -> str:
    conv = channel.conversation(agent_id)
    deps = channel.agents[agent_id]
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
            status=last.status, steps=len(last.steps), started=last.started_at[11:16]
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


async def decide(channel: TelegramChannel, agent_id: str, approve: bool) -> str:
    """Resolves the pending approval of the agent's conversation of today and runs the
    rest of the turn like a normal message, so the answer comes back to the chat."""
    conv = channel.conversation(agent_id)
    deps = channel.agents[agent_id]
    pending = deps.store.approvals.pending(conv.id)
    if conv.status != AWAITING_APPROVAL or pending is None:
        return texts.TELEGRAM_NO_APPROVAL
    events = channel.inbound.decide(conv.id, pending.id, approve, source=TELEGRAM)
    return await channel.answer(agent_id, events)
