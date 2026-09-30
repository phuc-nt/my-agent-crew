"""The `conversation_search` tool: finding what was said in an older conversation.

Scope is built into the schema rather than trusted from the arguments: another agent's
tool has no `agent` parameter at all, so it cannot ask to search someone else's
conversations even if a model tries to add the argument anyway — the parameter simply
does not exist for it to fill in. Only the master, who runs the whole crew, gets to name
an agent or leave it out for every one of them.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import turn_conversation_id
from my_agent_crew.store import Store
from my_agent_crew.store.search import SearchHit, match_query
from my_agent_crew.tools.registry import Tool, ToolError

_SINCE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _check_since(since: str) -> str | None:
    since = since.strip()
    if not since:
        return None
    if not _SINCE_RE.match(since):
        raise ToolError(texts.CONVERSATION_SEARCH_BAD_SINCE)
    try:
        date.fromisoformat(since)
    except ValueError as exc:
        raise ToolError(texts.CONVERSATION_SEARCH_BAD_SINCE) from exc
    return since


def _format(hits: list[SearchHit], *, label_others: bool, own_agent_id: str) -> str:
    if not hits:
        return texts.CONVERSATION_SEARCH_EMPTY
    by_conversation: dict[str, list[SearchHit]] = {}
    order: list[str] = []
    for hit in hits:
        if hit.conversation_id not in by_conversation:
            by_conversation[hit.conversation_id] = []
            order.append(hit.conversation_id)
        by_conversation[hit.conversation_id].append(hit)
    blocks: list[str] = []
    for conv_id in order:
        group = by_conversation[conv_id]
        head = group[0]
        show_agent = label_others and head.agent_id != own_agent_id
        agent_label = f"[{head.agent_id}] " if show_agent else ""
        lines = [
            texts.CONVERSATION_SEARCH_CONVERSATION_LINE.format(
                agent=agent_label,
                title=head.title,
                when=head.created_at,
                conversation_id=head.conversation_id,
            )
        ]
        lines += [
            texts.CONVERSATION_SEARCH_HIT_LINE.format(role=hit.role, snippet=hit.snippet)
            for hit in group
        ]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_conversation_search_tool(store: Store, agent_id: str, is_master: bool) -> Tool:
    properties: dict[str, Any] = {
        "query": {"type": "string", "description": texts.CONVERSATION_SEARCH_PARAM_QUERY},
        "since": {"type": "string", "description": texts.CONVERSATION_SEARCH_PARAM_SINCE},
    }
    if is_master:
        properties["agent"] = {
            "type": "string",
            "description": texts.CONVERSATION_SEARCH_PARAM_AGENT,
        }

    async def run(args: dict[str, Any]) -> str:
        query = str(args.get("query", ""))
        since = _check_since(str(args.get("since", "")))
        if match_query(query) is None:
            raise ToolError(texts.CONVERSATION_SEARCH_NO_TERMS)
        if is_master:
            requested = str(args.get("agent", "")).strip()
            agent_ids = [requested] if requested else None
        else:
            agent_ids = [agent_id]
        hits = store.search.find(
            query,
            agent_ids=agent_ids,
            since=since,
            exclude_conversation=turn_conversation_id() or None,
        )
        return _format(hits, label_others=is_master, own_agent_id=agent_id)

    description = (
        texts.CONVERSATION_SEARCH_DESCRIPTION_MASTER
        if is_master
        else texts.CONVERSATION_SEARCH_DESCRIPTION_OTHER
    )
    return Tool(
        name="conversation_search",
        description=description,
        parameters={"type": "object", "properties": properties, "required": ["query"]},
        run=run,
    )
