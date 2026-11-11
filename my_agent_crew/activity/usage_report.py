"""What the crew used over a window, as counts by name: which tools, skills, hooks, commands,
jobs and delegations ran and how often, how much of the prompts came from the cache, what
each provider cost. Read from the runs' steps, the usage ledger and the day counters
(`store/counters.py`); made to decide what can be deleted, so a thing nobody used shows as
absent or zero.

Names and numbers only. A step keeps a preview of a call's arguments and of its output; of
those this reads the skill a `skill_read` named and the `outcome=` word of a delegation,
and nothing else leaves."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME
from my_agent_crew.store import counters
from my_agent_crew.store.runs import DONE, FAILED, RunRecord

SKILL_TOOL = "skill_read"
JOB_PREFIX = "job:"
# A delegation that never reached a child (an unknown agent, a refusal) names no outcome.
NO_OUTCOME = "no_child"
NAME_CHARS = 120
_OUTCOME = re.compile(r"\boutcome=([a-z_]+)")
_SKILL_NAME = re.compile(r"^[\w.:-]{1,120}$")


def _tree() -> defaultdict[str, Any]:
    return defaultdict(lambda: defaultdict(int))


def _share(cached: int, prompt: int) -> float | None:
    return round(cached / prompt, 4) if prompt else None


def _tool_step(out: dict[str, Any], agent: str, step: dict[str, Any]) -> None:
    name = str(step.get("name") or "")[:NAME_CHARS]
    tally = out["tools"][agent].setdefault(name, {"calls": 0, "failed": 0})
    tally["calls"] += 1
    tally["failed"] += step.get("ok") is False
    for nested in step.get("calls") or []:
        if isinstance(nested, dict) and nested.get("name"):
            out["tools_from_scripts"][agent][str(nested["name"])[:NAME_CHARS]] += 1
    if isinstance(step.get("shaped"), dict):
        out["shaped_outputs"][agent][str(step["shaped"].get("kind"))] += 1
    if name == SKILL_TOOL:
        skill = (step.get("arguments") or {}).get("name")
        # A name the preview cut, or one that is no name at all, is not repeated.
        known = isinstance(skill, str) and _SKILL_NAME.match(skill.strip())
        out["skills"][agent][skill.strip() if known else "?"] += 1
    if name == DELEGATE_TOOL_NAME and step.get("ok") is not None:
        found = _OUTCOME.search(str(step.get("output") or ""))
        out["delegations"][agent][found.group(1) if found else NO_OUTCOME] += 1


def _model_step(cache: dict[str, dict[str, int]], agent: str, step: dict[str, Any]) -> None:
    prompt, cached = step.get("prompt_tokens"), step.get("cached_tokens")
    tally = cache.setdefault(
        agent, {"model_calls": 0, "prompt_tokens": 0, "cached_tokens": 0, "unknown_calls": 0}
    )
    tally["model_calls"] += 1
    if prompt and cached is None:
        tally["unknown_calls"] += 1  # the provider did not say: left out of the share
    elif prompt:
        tally["prompt_tokens"] += prompt
        tally["cached_tokens"] += cached


def _job(jobs: dict[str, dict[str, int]], run: RunRecord) -> None:
    tally = jobs.setdefault(
        run.source[len(JOB_PREFIX) :], {"runs": 0, "done": 0, "failed": 0, "other": 0}
    )
    tally["runs"] += 1
    tally["done" if run.status == DONE else "failed" if run.status == FAILED else "other"] += 1


def _counted(out: dict[str, Any], rows: Iterable[dict[str, Any]]) -> None:
    for row in rows:
        kind, agent, name, count = row["kind"], row["agent_id"], row["name"], row["count"]
        if kind == counters.PROMPT_TRIM:
            out["prompt_trims"][agent] = out["prompt_trims"].get(agent, 0) + count
        elif kind == counters.SPILL:
            out["spilled_outputs"][agent][name] += count
        elif kind == counters.COMMAND:
            out["commands"][agent][name] += count
        elif kind in (counters.HOOK_RUN, counters.HOOK_BLOCK):
            tally = out["hooks"][agent].setdefault(name, {"runs": 0, "blocks": 0})
            tally["runs" if kind == counters.HOOK_RUN else "blocks"] += count


def usage_report(
    runs: Iterable[RunRecord],
    counted: Iterable[dict[str, Any]],
    providers: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """The counts, keyed by agent and then by name wherever an agent is known."""
    out: dict[str, Any] = {
        "runs": 0,
        "tools": defaultdict(dict),
        "tools_from_scripts": _tree(),
        "shaped_outputs": _tree(),
        "skills": _tree(),
        "delegations": _tree(),
        "schedules": {},
        "hooks": defaultdict(dict),
        "commands": _tree(),
        "prompt_trims": {},
        "spilled_outputs": _tree(),
    }
    cache: dict[str, dict[str, int]] = {}
    for run in runs:
        out["runs"] += 1
        if run.source.startswith(JOB_PREFIX):
            _job(out["schedules"], run)
        for step in run.steps:
            if step.get("kind") == "tool":
                _tool_step(out, run.agent_id, step)
            elif step.get("kind") == "model":
                _model_step(cache, run.agent_id, step)
    _counted(out, counted)
    for tally in cache.values():
        tally["cached_share"] = _share(tally["cached_tokens"], tally["prompt_tokens"])
    out["cache_by_agent"] = cache
    out["providers"] = {
        name: row | {"cached_share": _share(row["cached_tokens"], row["prompt_tokens"])}
        for name, row in sorted(providers.items())
    }
    return out
