"""Slash commands from a kit: expanded before the agent reads them, on the web and on
Telegram alike, and listed next to the built-in Telegram commands."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agents.kit import Kit
from my_agent_crew.agents.kit_commands import (
    Command,
    commands_section,
    expand,
    find_command,
    load_commands,
    parse_command,
)
from my_agent_crew.channels.telegram_commands import MENU, help_text, menu_for
from my_agent_crew.config import Route
from my_agent_crew.inbound import Inbound
from tests.test_channels_telegram import message

# The Telegram fixtures (`fake`, `make_channel`) come from that module.
pytest_plugins = ["tests.test_channels_telegram"]

HELLO = Command("hello", "Chào theo tên.", "Say hello to $ARGUMENTS in Vietnamese.")
PAIR = Command("pair", "", "First: $1. Second: $2.")
PLAIN = Command("mk:plan", "Lập kế hoạch.", "Write a plan.")


def test_expand_replaces_placeholders_or_appends_the_arguments():
    commands = (HELLO, PAIR, PLAIN)
    assert expand("/hello An", commands) == "Say hello to An in Vietnamese."
    assert expand("/hello@bot  An Bình ", commands) == "Say hello to An Bình in Vietnamese."
    assert expand("/pair a b c", commands) == "First: a. Second: b."
    assert expand("/pair a", commands) == "First: a. Second: ."
    assert expand("/mk:plan", commands) == "Write a plan."
    appended = expand("/mk:plan for auth\nwith tests", commands)
    assert appended == "Write a plan.\n\nfor auth\nwith tests"
    assert expand("/unknown x", commands) == "/unknown x"
    assert expand("/usr/bin/x", commands) == "/usr/bin/x"
    assert expand("hi /hello", commands) == "hi /hello"
    assert find_command(commands, "pair") is PAIR and find_command(commands, "x") is None


def test_parse_and_load_commands_read_front_matter_and_let_later_kits_win(tmp_path: Path):
    parsed = parse_command("---\ndescription: Review   it\n---\nReview $ARGUMENTS.", "review")
    assert parsed == Command("review", "Review it", "Review $ARGUMENTS.")
    assert parse_command("Plain body", "plain").description == ""
    for kit_name, body in (("first", "one"), ("second", "two")):
        path = tmp_path / kit_name / ".agents" / "commands" / "review.md"
        path.parent.mkdir(parents=True)
        path.write_text(body)
    kits = [Kit(tmp_path / n / ".agents", tmp_path, "home") for n in ("first", "second")]
    [command] = load_commands(kits)
    assert command.template == "two" and command.path.endswith("second/.agents/commands/review.md")
    assert commands_section(()) is None
    title, body = commands_section((HELLO, PAIR))
    assert title == texts.KIT_COMMANDS_SECTION_TITLE
    assert "/hello — Chào theo tên." in body and texts.KIT_COMMAND_NO_DESCRIPTION in body


def with_commands(deps, *commands: Command):
    return replace(deps, profile=replace(deps.agent, commands=tuple(commands)))


async def test_inbound_expands_a_kit_command_before_the_turn(deps_factory):
    deps = with_commands(deps_factory(routes=(Route("fake", "echo"),)), HELLO)
    inbound = Inbound({deps.agent.id: deps}, ActivityHub(deps.store))
    conv = inbound.conversation_for(deps.agent.id, "chat")
    reply = await inbound.reply(conv.id, "/hello An")
    assert reply.text == "(echo) Say hello to An in Vietnamese."
    assert (await inbound.reply(conv.id, "/nope An")).text == "(echo) /nope An"


async def test_telegram_passes_kit_commands_to_the_agent_and_lists_them(
    make_channel, deps_factory, fake
):
    deps = with_commands(deps_factory(routes=(Route("fake", "echo"),)), HELLO, PAIR, PLAIN)
    channel = make_channel(deps)
    await channel.register_menu()
    fake.updates = [message(1, "/hello An"), message(2, "/mk:plan x"), message(3, "/help")]
    await channel.poll_once()
    fake.updates = [message(4, "/loop 5m"), message(5, "/status")]
    await channel.poll_once()
    hello, plan, help_lines, unknown, status = fake.sent
    assert hello == "(echo) Say hello to An in Vietnamese."
    assert plan == "(echo) Write a plan.\n\nx"
    assert unknown == texts.TELEGRAM_UNKNOWN_COMMAND.format(command="loop")
    assert status.startswith(channel.conversation().title)  # built-ins still win
    assert "/hello — Chào theo tên." in help_lines and "/mk:plan — Lập kế hoạch." in help_lines
    assert f"/pair — {texts.KIT_COMMAND_NO_DESCRIPTION}" in help_lines
    assert help_text() == "\n".join(f"/{n} — {d}" for n, d in MENU)
    # Telegram's menu takes only names it accepts, with a description of some length.
    menu = [(m["command"], m["description"]) for m in fake.menu]
    assert menu == [*MENU, ("hello", "Chào theo tên.")]
    assert menu_for((Command("status", "Shadowing a built-in.", "x"),)) == list(MENU)
