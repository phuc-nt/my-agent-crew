"""System prompt assembly. Behavioural rules live in the agent's persona files and
skills; this is the frame that carries them."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from my_agent_crew import texts
from my_agent_crew.agent.context_trim import trim_tool_outputs
from my_agent_crew.agent.payload_trim import attach_canvas_notes, trim_canvas_payloads
from my_agent_crew.agent.prompt_frame import frame_text, today_line
from my_agent_crew.agent.turn_context import canvas_reader_is_away, may_write_canvas
from my_agent_crew.agents.context import bootstrap_sections, turn_tail_sections
from my_agent_crew.agents.kit_commands import commands_section
from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME, crew_roster_section
from my_agent_crew.clock import day_and_time
from my_agent_crew.config import Settings
from my_agent_crew.llm.types import Message
from my_agent_crew.skills import Skill
from my_agent_crew.store import Conversation, StoredMessage
from my_agent_crew.texts_canvas import CANVAS_AWAY_BODY, CANVAS_CLOSED_BODY, CANVAS_CLOSED_TITLE
from my_agent_crew.tools.artifact_scope import CANVAS_WRITE_TOOLS
from my_agent_crew.tools.output_spill import READ_TOOL

if TYPE_CHECKING:
    from my_agent_crew.agent.loop import AgentDeps

# Above this many indexed skills the descriptions are dropped so the index stays a list
# the model can scan, not a second prompt.
INDEX_NAMES_ONLY_ABOVE = 40
INDEX_DESCRIPTION_CHARS = 120


def active_skills(skills: Sequence[Skill], attached: Sequence[str]) -> list[Skill]:
    wanted = set(attached)
    return [s for s in skills if s.always or s.name in wanted]


def _index_suffix(skill: Skill) -> str:
    """The two things the model needs before it starts guessing: whether the command is
    even on this machine, and the one command that prints the real syntax."""
    parts = []
    if skill.missing_bins:
        parts.append(texts.SKILL_INDEX_MISSING_BINS.format(bins=", ".join(skill.missing_bins)))
    if skill.cli_help:
        parts.append(texts.SKILL_INDEX_CLI_HELP.format(command=skill.cli_help))
    return (" " + " ".join(parts)) if parts else ""


def skill_index_section(skills: Sequence[Skill]) -> str:
    """The skills that are loaded but not in the prompt, one line each, so the model knows
    what `skill_read` can fetch. Empty when there is nothing to index."""
    if not skills:
        return ""
    names_only = len(skills) > INDEX_NAMES_ONLY_ABOVE
    lines = []
    for skill in skills:
        description = "" if names_only else skill.description.strip().replace("\n", " ")
        if len(description) > INDEX_DESCRIPTION_CHARS:
            description = description[: INDEX_DESCRIPTION_CHARS - 1].rstrip() + "…"
        line = texts.SKILL_INDEX_LINE.format(name=skill.name, description=description)
        if not description:
            line = line.rstrip(": ")
        lines.append(line + _index_suffix(skill))
    return f"\n{texts.SKILL_INDEX_HEADING}\n{texts.SKILL_INDEX_INTRO}\n" + "\n".join(lines) + "\n"


def canvas_closed_section(
    conv: Conversation | None, tool_names: Sequence[str]
) -> list[tuple[str, str]]:
    """A turn that cannot write a canvas hears so before the model puts a whole document into
    a call only to have it refused. The tools stay listed, so every turn of the agent shares
    one prefix; the standing prompt, with no turn, has no channel to speak of."""
    held = [name for name in CANVAS_WRITE_TOOLS if name in tool_names]
    if conv is None or not held or may_write_canvas(conv):
        return []
    return [(CANVAS_CLOSED_TITLE, CANVAS_CLOSED_BODY.format(tools=", ".join(held)))]


def canvas_away_section(
    conv: Conversation | None, tool_names: Sequence[str]
) -> list[tuple[str, str]]:
    """A turn that may write a canvas while its reader is away from the web chat hears when
    one is worth making and how to send it. An agent holding no canvas write has nothing to be
    advised on, and the standing prompt, with no turn, has no reader to speak of."""
    holds_a_write = any(name in tool_names for name in CANVAS_WRITE_TOOLS)
    if conv is None or not holds_a_write or not canvas_reader_is_away(conv):
        return []
    return [(CANVAS_CLOSED_TITLE, CANVAS_AWAY_BODY)]


def build_system_prompt(
    settings: Settings,
    skills: Sequence[Skill],
    tool_names: Sequence[str],
    sections: Sequence[tuple[str, str]] = (),
    name: str = "trợ lý",
    today: str = "",
    skill_index: Sequence[Skill] = (),
    tail_sections: Sequence[tuple[str, str]] = (),
) -> str:
    """`skills` ride in full; `skill_index` are only named, to be read on demand.
    `tail_sections` are the parts that change between turns; they and the date come last
    so the long stable prefix before them stays cacheable."""
    text = frame_text(settings, name, tool_names)
    for title, body in sections:
        text += f"\n## {title}\n{body}\n"
    for skill in skills:
        text += f"\n## Kỹ năng: {skill.name}\n{skill.body}\n"
    text += skill_index_section(skill_index)
    for title, body in tail_sections:
        text += f"\n## {title}\n{body}\n"
    return text + today_line(settings, today)


def system_prompt_for(deps: AgentDeps, conv: Conversation | None = None) -> str:
    """The system prompt this agent would be given right now.

    Shared with whatever wants to show the person what the agent is actually told, so a
    preview cannot drift from the real thing: any section added to a turn appears here by
    construction rather than by being reimplemented.

    Without a conversation it is the agent's standing prompt — the skills it always
    carries, no per-conversation attachments and no summary of a previous session.
    """
    skills = active_skills(deps.skills, conv.skills if conv else ())
    active_names = {s.name for s in skills}
    index = [s for s in deps.skills if s.name not in active_names]
    profile = deps.agent
    # A delegated turn is one job with a fresh brief; the summary of some earlier job on
    # the same channel is noise to it, and a different one for every child breaks the
    # prefix all the children of one master could otherwise share. A fork is newest on its
    # channel by rowid, so "the conversation before it" usually is the very one it was cut
    # from — whose summary covers the part after the cut that the fork exists to drop.
    previous = (
        deps.store.previous_for_channel(conv.agent_id, conv.channel, conv.id)
        if conv is not None and not conv.parent_call_id and not conv.forked_from
        else None
    )
    today = deps.settings.today()
    tool_names = deps.tools.names()
    # An agent only hears about its crew when it holds the tool to reach them: a child
    # turn runs without `delegate`, and a roster it cannot act on would only mislead it.
    roster = crew_roster_section(profile, deps.peers) if DELEGATE_TOOL_NAME in tool_names else None
    # A delegated turn opens with another agent's words, not the person's; without saying
    # so the child obeys a guessed file path as if the person had asked for it.
    delegated = (
        (texts.DELEGATED_TURN_TITLE, texts.DELEGATED_TURN_BODY)
        if conv is not None and conv.parent_call_id
        else None
    )
    extra = [s for s in (delegated, roster, commands_section(profile.commands)) if s]
    return build_system_prompt(
        deps.settings,
        skills,
        tool_names,
        sections=bootstrap_sections(profile, extra_sections=extra),
        name=profile.name,
        today=today.isoformat(),
        skill_index=index,
        tail_sections=[
            *turn_tail_sections(
                profile,
                today=today,
                previous_summary=previous.summary if previous else "",
                previous_at=day_and_time(previous.updated_at, deps.settings.zone)
                if previous
                else "",
            ),
            *canvas_closed_section(conv, tool_names),
            *canvas_away_section(conv, tool_names),
        ],
    )


def turn_messages(
    deps: AgentDeps,
    conv: Conversation,
    history: Sequence[StoredMessage],
    turn_start: int | None = None,
) -> list[Message]:
    """The exact message list one model call is given: the system frame this module
    builds, then the conversation so far with old tool output trimmed out and each person's
    message after its canvas note. When `turn_start` names the last message before this
    turn, the canvas writes made up to it lose their document text and the notes stored
    before it become a stub."""
    system = Message(role="system", content=system_prompt_for(deps, conv))
    can_reread = deps.tools.get(READ_TOOL) is not None
    messages = trim_canvas_payloads(history, turn_start)
    messages = attach_canvas_notes(history, messages, turn_start)
    return [system, *trim_tool_outputs(messages, can_reread=can_reread)]
