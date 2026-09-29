"""An exported run as Markdown a person can read. Free text goes in as the agent wrote it,
so nothing in it may reshape the file: one line for the title, and a code block a message
leaves open is closed before the next message starts."""

from __future__ import annotations

import json
import re
from typing import Any

from my_agent_crew import texts

# A fence as CommonMark reads one: at most three spaces in, three or more of one mark.
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def to_markdown(data: dict[str, Any]) -> str:
    run = data["run"]
    lines = [texts.TRAJECTORY_TITLE.format(title=_one_line(run["title"] or run["id"])), ""]
    lines += [f"> {data['notice']}", "", *_facts(run, data["slice"]), ""]
    if data["messages"] or not run["steps"]:
        lines += [texts.TRAJECTORY_MESSAGES, "", *_blocks(data["messages"])]
    else:
        lines += [texts.TRAJECTORY_STEPS, "", *(_step(step) for step in run["steps"]), ""]
    for child in data["children"]:
        heading = texts.TRAJECTORY_CHILD.format(
            agent=child["agent_id"],
            conversation=child["conversation_id"],
            call=child["tool_call_id"],
        )
        lines += [heading, "", *_blocks(child["messages"])]
    return "\n".join(lines).rstrip() + "\n"


def _facts(run: dict[str, Any], how: str) -> list[str]:
    spent = f"${run['spent_usd']:.4f}"
    if run["unknown_cost_calls"]:
        spent += texts.TRAJECTORY_UNKNOWN_COST.format(count=run["unknown_cost_calls"])
    conversation = run["conversation_id"]
    facts = {
        "id": f"`{run['id']}`",
        "agent_id": run["agent_id"],
        "source": f"`{run['source']}`",
        "status": f"`{run['status']}`",
        "summary": _one_line(run["summary"]),
        "started_at": run["started_at"],
        "finished_at": run["finished_at"],
        "steps": str(len(run["steps"])),
        "spent_usd": spent,
        "conversation_id": f"`{conversation}`" if conversation else "",
        "slice": texts.TRAJECTORY_SLICES[how],
    }
    labels = texts.TRAJECTORY_FACT_LABELS
    return [f"- {labels[key]}: {value}" for key, value in facts.items() if value]


def _blocks(messages: list[dict[str, Any]]) -> list[str]:
    if not messages:
        return [texts.TRAJECTORY_NO_MESSAGES, ""]
    lines: list[str] = []
    for message in messages:
        lines += [_heading(message), ""]
        if message["role"] == "tool":
            lines += [_fenced(message["content"]), ""]
            continue
        if message["content"]:
            lines += [_closed(message["content"]), ""]
        for call in message["tool_calls"]:
            arguments = json.dumps(call["arguments"], ensure_ascii=False, indent=2)
            lines += [texts.TRAJECTORY_CALL.format(name=call["name"]), ""]
            lines += [_fenced(arguments, "json"), ""]
    return lines


def _heading(message: dict[str, Any]) -> str:
    parts = [f"#{message['seq']}", texts.TRAJECTORY_ROLES.get(message["role"], message["role"])]
    if message["role"] == "tool" and message["name"]:
        parts.append(f"`{message['name']}`")
    if message["model"]:
        provider = message["provider"]
        parts.append(f"{provider}/{message['model']}" if provider else message["model"])
    return "### " + " · ".join(parts)


def _fenced(text: str, language: str = "") -> str:
    """A fence longer than any backtick run inside, so the text cannot close it early."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{text}\n{fence}"


def _closed(text: str) -> str:
    """The text, with a code block it opens and never closes (an answer stopped mid-block)
    closed after it, or the block would swallow every message that follows."""
    opened = ""
    for line in text.splitlines():
        match = _FENCE.match(line)
        if match is None:
            continue
        fence, rest = match.groups()
        if not opened:
            # A backtick fence's info string holds no backtick; with one it is inline code.
            if fence[0] == "~" or "`" not in rest:
                opened = fence
        elif fence[0] == opened[0] and len(fence) >= len(opened) and not rest.strip():
            opened = ""
    return f"{text}\n{opened}" if opened else text


def _step(step: dict[str, Any]) -> str:
    shown = (f"{key}: {value}" for key, value in step.items() if value not in (None, "", []))
    return "- " + _one_line(" · ".join(shown))


def _one_line(text: str) -> str:
    return " ".join(str(text).split())
