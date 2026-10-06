"""`tool_search`: how an agent finds the MCP tools it was not told of up front.

A server can list dozens of tools, and telling a model of all of them on every call costs
context it mostly does not use. So only the tools let in `direct` are told and the rest
wait here. The agent asks in a few words, the answer names the best matches, and from the
next call on those are told like any other: `agent.declared_tools` reads the answers back
out of the conversation, so what was loaded is still loaded after a restart.

The search is BM25 over each tool's name, its description and the names and descriptions
of its parameters. Nothing is fetched: these are the tools the servers listed when they
connected, and only the ones this agent holds.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from my_agent_crew import texts_mcp as t
from my_agent_crew.mcp.tools import McpTool, summary
from my_agent_crew.tools.registry import Tool, ToolError

SEARCH_TOOL = "tool_search"
DEFAULT_LIMIT, MAX_LIMIT = 5, 10
K1, B = 1.2, 0.75
# A word of a tool's name counts as this many of its description's.
NAME_WEIGHT = 3
# A schema is the server's to write, and is read no deeper than this.
MAX_SCHEMA_DEPTH = 8
# How a loaded tool is written in an answer, and how it is read back out of one. The
# description is one line, so nothing a server wrote can start a line of its own.
LINE = "- {name}: {description}"
LOADED_LINE = re.compile(r"^- (mcp__\w+):", re.MULTILINE)

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_WORD = re.compile(r"[a-z0-9]+")

PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": t.TOOL_SEARCH_QUERY},
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_LIMIT,
            "description": t.TOOL_SEARCH_LIMIT.format(default=DEFAULT_LIMIT, most=MAX_LIMIT),
        },
    },
    "required": ["query"],
}


@dataclass(frozen=True)
class SearchTool(Tool):
    def to_dict(self) -> dict[str, Any]:
        # For the owner's screens: it comes with an agent's servers, not its allow-list.
        return {**super().to_dict(), "with_mcp": True}


def _singular(word: str) -> str:
    plural = len(word) > 3 and word.endswith("s") and not word.endswith("ss")
    return word[:-1] if plural else word


def words(text: str) -> list[str]:
    """The words a search compares: lower case, accents folded, `createPage` and
    `create_page` both two words, and a plural's `s` dropped so `pages` finds `page`."""
    # `đ` is a letter of its own, not a `d` with a mark: folding leaves it as it is.
    spaced = _CAMEL.sub(" ", text).lower().replace("đ", "d")
    plain = "".join(
        ch for ch in unicodedata.normalize("NFD", spaced) if not unicodedata.combining(ch)
    )
    return [_singular(word) for word in _WORD.findall(plain)]


def _schema_text(schema: Any, depth: int = 0) -> Iterator[str]:
    """The names and descriptions of a tool's parameters, nested ones included."""
    if depth > MAX_SCHEMA_DEPTH:
        return
    if isinstance(schema, list):
        for item in schema:
            yield from _schema_text(item, depth + 1)
    elif isinstance(schema, dict):
        described = schema.get("description")
        if isinstance(described, str):
            yield described
        for key, value in schema.items():
            if key == "properties" and isinstance(value, dict):
                # Parameters by name, not a schema: one may well be called `description`.
                for name, inner in value.items():
                    yield str(name)
                    yield from _schema_text(inner, depth + 1)
            else:
                yield from _schema_text(value, depth + 1)


def _document(tool: McpTool) -> Counter[str]:
    # The description opens with the name of the tool's server, so that is a word of it.
    rest = " ".join((tool.description, *_schema_text(tool.parameters)))
    return Counter(words(tool.remote) * NAME_WEIGHT + words(rest))


def rank(tools: Sequence[McpTool], query: str) -> list[McpTool]:
    """Every tool the query matches, best first: the ones it names outright, then by BM25."""
    documents = [_document(tool) for tool in tools]
    sizes = [sum(document.values()) for document in documents]
    average = sum(sizes) / len(sizes) if sizes else 0.0
    asked = set(words(query))
    named = set(re.split(r"[\s,]+", query))
    weight = {
        word: math.log(1 + (len(tools) - holders + 0.5) / (holders + 0.5))
        for word in asked
        if (holders := sum(1 for document in documents if document[word]))
    }
    found = []
    for tool, document, size in zip(tools, documents, sizes, strict=True):
        score = sum(
            idf * seen * (K1 + 1) / (seen + K1 * (1 - B + B * size / average))
            for word, idf in weight.items()
            if (seen := document[word])
        )
        exact = tool.name in named or tool.remote in named
        if exact or score > 0:
            found.append((not exact, -score, tool.name, tool))
    return [row[3] for row in sorted(found, key=lambda row: row[:3])]


def _limit(raw: Any) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        return DEFAULT_LIMIT
    return max(1, min(raw, MAX_LIMIT))


def _servers(about: Mapping[str, str]) -> str:
    return "; ".join(
        t.TOOL_SEARCH_SERVER.format(name=name, description=said) if said else name
        for name, said in about.items()
    )


def _counts(tools: Sequence[McpTool]) -> str:
    held = Counter(tool.server for tool in tools)
    return ", ".join(t.TOOL_SEARCH_COUNT.format(name=name, count=n) for name, n in held.items())


def search_tool(tools: Sequence[McpTool], about: Mapping[str, str]) -> Tool:
    """One agent's `tool_search`, over the tools it holds that are not told up front.
    `about` is what the owner wrote of each of their servers: the model reads it to know
    what is worth looking for."""
    held = tuple(tools)

    async def run(arguments: dict[str, Any]) -> str:
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ToolError(t.TOOL_SEARCH_NO_QUERY)
        found = rank(held, query)
        if not found:
            return t.TOOL_SEARCH_NONE.format(servers=_counts(held))
        loaded = found[: _limit(arguments.get("limit"))]
        lines = [t.TOOL_SEARCH_LOADED.format(count=len(loaded))]
        lines += [
            LINE.format(name=tool.name, description=summary(tool.description)) for tool in loaded
        ]
        if len(found) > len(loaded):
            lines.append(t.TOOL_SEARCH_MORE.format(count=len(found) - len(loaded)))
        return "\n".join(lines)

    return SearchTool(
        name=SEARCH_TOOL,
        description=t.TOOL_SEARCH_DESCRIPTION.format(servers=_servers(about)),
        parameters=PARAMETERS,
        run=run,
        # It reads what the agent already holds, so it never asks and may be made again.
        replay_safe=True,
    )
