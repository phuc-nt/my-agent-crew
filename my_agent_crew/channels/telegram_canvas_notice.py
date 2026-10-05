"""The list a chat is sent of the canvases a turn wrote.

A chat shows no canvas: what an agent writes is read on the web. So after a turn's words the
chat is told which canvases the turn wrote, at the version it left each, and where the web
shows them.

What a turn wrote is read from the results of its own tools, never from its reply: a write's
result opens with the tag, and a delegated task's result names what the child wrote. A live
turn is read as its events pass; a run delivered later, a job's brief, is read from the tool
messages it stored. The list names only what the agent still reaches, by the rule a canvas is
sent to the chat by, so one deleted since, or written by a child and out of the delegator's
reach, is left out and not said to exist.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterable, Sequence

from my_agent_crew import texts
from my_agent_crew.activity.redact import env_secrets, redact
from my_agent_crew.agent.events import Event, ToolResultEvent
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME
from my_agent_crew.artifacts.tag import Tag, parse_artifact_tag
from my_agent_crew.channels.telegram_canvas_file import canvas_in_reach, canvas_link
from my_agent_crew.store import Store
from my_agent_crew.store.runs import RunRecord
from my_agent_crew.tools.artifact_scope import CANVAS_WRITE_TOOLS
from my_agent_crew.tools.delegate_outcome import canvas_tags

MAX_LISTED = 10  # the canvases one list names; the rest are counted in its last line


def tags_of(name: str, output: str) -> list[Tag]:
    """The canvases the result of the tool `name` says were written. A write that changed
    nothing wrote nothing, and a tool that only reads names none whatever its result says."""
    if name in CANVAS_WRITE_TOOLS:
        tag = parse_artifact_tag(output)
        found = [tag] if tag is not None else []
    elif name == DELEGATE_TOOL_NAME:
        found = canvas_tags(output)
    else:
        found = []
    return [tag for tag in found if not tag.unchanged]


def merged(tags: Iterable[Tag]) -> list[Tag]:
    """Each canvas once, at the newest version written, in the order they were first written."""
    newest: dict[str, Tag] = {}
    for tag in tags:
        held = newest.get(tag.id)
        if held is None or tag.version > held.version:
            newest[tag.id] = tag
    return list(newest.values())


class WrittenCanvases:
    """What a live turn wrote, gathered from its events as they pass."""

    def __init__(self) -> None:
        self._seen: list[Tag] = []

    @property
    def tags(self) -> list[Tag]:
        return merged(self._seen)

    async def watch(self, events: AsyncIterator[Event]) -> AsyncIterator[Event]:
        """The events as they came, each one and in order; what breaks the turn still does."""
        async for event in events:
            if isinstance(event, ToolResultEvent):
                self._seen.extend(tags_of(event.name, event.output))
            yield event


def written_by(store: Store, conv_id: str, run: RunRecord | None) -> list[Tag]:
    """What `run` wrote in the conversation, from the tool messages it stored. A run that
    stopped for an approval nobody answered was delivered once while it waited, and that
    delivery named what it had written by then: the tool message saying the approval lapsed
    marks where it read up to, and only what follows the last one is named now. A run from
    before runs knew where they began names nothing."""
    if run is None or run.after_seq is None:
        return []
    stored = store.messages.of_run(conv_id, run.id, run.after_seq, run.started_at)
    tools = [s.message for s in stored if s.message.role == "tool"]
    lapsed = [i for i, message in enumerate(tools) if message.content == texts.EXPIRED_TOOL]
    since = tools[lapsed[-1] + 1 :] if lapsed else tools
    return merged(tag for message in since for tag in tags_of(message.name or "", message.content))


def notice_text(deps: AgentDeps, tags: Sequence[Tag], conv_id: str | None) -> str:
    """The list, or "" when none of `tags` names a canvas the agent reaches from the
    conversation. A title is whatever the model chose, so it leaves with the secrets this
    process knows covered, like the caption of a canvas sent as a file."""
    named = [
        (tag, summary)
        for tag in tags
        if (summary := canvas_in_reach(deps, tag.id, conv_id)) is not None
    ]
    if not named:
        return ""
    secrets, web_url = env_secrets(os.environ), deps.settings.web_url
    lines = [texts.TELEGRAM_CANVAS_HEADER]
    for tag, summary in named[:MAX_LISTED]:
        title = redact(summary.title, secrets)
        lines.append(texts.TELEGRAM_CANVAS_LINE.format(title=title, version=tag.version))
        if web_url:
            lines.append(texts.TELEGRAM_CANVAS_LINK_LINE.format(link=canvas_link(web_url, tag.id)))
    if len(named) > MAX_LISTED:
        lines.append(texts.TELEGRAM_CANVAS_MORE.format(n=len(named) - MAX_LISTED))
    if not web_url:
        lines.append(texts.TELEGRAM_CANVAS_OPEN_WEB)
    return "\n".join(lines)
