"""Slash commands from a kit: `commands/<name>.md` is a prompt the person invokes as
`/<name> arguments`. The server swaps the command for its text before the agent reads
the message, so the agent sees the prompt, never the shorthand — the same expansion
Claude Code and opencode do, with the same placeholders (`$ARGUMENTS`, `$1`…`$9`)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from my_agent_crew import texts
from my_agent_crew.agents.kit import Kit, split_front_matter

ARGUMENTS = "$ARGUMENTS"
_POSITIONAL = re.compile(r"\$([1-9])")
_INVOCATION = re.compile(r"^/([\w:.-]+)(?:@\w+)?(?:\s+(.*))?$", re.DOTALL)
MAX_DESCRIPTION_CHARS = 200
# Built in, and ahead of any kit command of the same name: `/steer text` hands `text` to the
# turn already running instead of waiting for it to end.
STEER_COMMAND = "steer"


class EmptySteer(ValueError):
    """`/steer` with nothing to hand over; str() tells the person how to use it."""


@dataclass(frozen=True)
class Command:
    name: str
    description: str
    template: str
    path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "path": self.path}

    def render(self, arguments: str) -> str:
        """The template with the arguments in; a template that names no placeholder gets
        them appended, so `/review src/x.py` still says which file."""
        text = self.template
        used = ARGUMENTS in text or _POSITIONAL.search(text) is not None
        words = arguments.split()
        text = text.replace(ARGUMENTS, arguments)
        text = _POSITIONAL.sub(lambda m: _word(words, int(m.group(1))), text)
        if arguments and not used:
            text = f"{text}\n\n{arguments}"
        return text.strip()


def _word(words: list[str], index: int) -> str:
    return words[index - 1] if len(words) >= index else ""


def parse_command(text: str, name: str, path: str = "") -> Command:
    meta, body = split_front_matter(text)
    description = " ".join(str(meta.get("description") or "").split())
    return Command(
        name=str(meta.get("name") or name),
        description=description[:MAX_DESCRIPTION_CHARS],
        template=body,
        path=path,
    )


def load_commands(kits: Sequence[Kit]) -> tuple[Command, ...]:
    """Later kits win by name, the order `agent_kits` returns them in."""
    by_name: dict[str, Command] = {}
    for kit in kits:
        for path in kit.command_files:
            command = parse_command(
                path.read_text(encoding="utf-8"), kit.command_name(path), str(path)
            )
            by_name[command.name] = command
    return tuple(by_name.values())


def find_command(commands: Sequence[Command], name: str) -> Command | None:
    return next((c for c in commands if c.name == name), None)


def steer_text(text: str, commands: Sequence[Command]) -> str | None:
    """What a message that may jump the queue asks for, or None for an ordinary message.

    `/steer text` asks for `text` and a kit command for its prompt. Anything else, a
    `/path/like/this` and a command nobody defined included, waits its turn as written."""
    match = _INVOCATION.match(text.strip())
    if match is None:
        return None
    name, arguments = match.group(1), (match.group(2) or "").strip()
    if name == STEER_COMMAND:
        if not arguments:
            raise EmptySteer(texts.STEER_NEEDS_TEXT)
        return arguments
    command = find_command(commands, name)
    return None if command is None else command.render(arguments)


def commands_section(commands: Sequence[Command]) -> tuple[str, str] | None:
    """A prompt section naming the commands, so the agent can point the person at one."""
    if not commands:
        return None
    lines = [
        texts.KIT_COMMAND_LINE.format(
            name=c.name, description=c.description or texts.KIT_COMMAND_NO_DESCRIPTION
        )
        for c in commands
    ]
    return texts.KIT_COMMANDS_SECTION_TITLE, "\n".join([texts.KIT_COMMANDS_INTRO, *lines])
