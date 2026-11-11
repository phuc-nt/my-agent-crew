"""`GET /api/activity/usage`: what the crew used over a window, as counts by name. It is
read to decide what can be deleted, so it must count what really ran, keep to the window,
and never repeat what a call was given or what anyone wrote."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from my_agent_crew.activity.usage_report import NO_OUTCOME, usage_report
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store import Store
from my_agent_crew.store.counters import COMMAND, PROMPT_TRIM, utc_day
from my_agent_crew.store.runs import DONE, FAILED, HALTED, RunRecord
from tests.conftest import collect

PRIVATE = "số tài khoản riêng"


def stamp(days_ago: float = 0) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat(timespec="seconds")


def run(
    run_id: str, steps: list[dict], agent: str = "a", source: str = "chat", **more
) -> RunRecord:
    more = {"status": DONE, "started_at": stamp()} | more
    return RunRecord(run_id, agent, None, source, "Việc", steps=steps, **more)


def tool_step(name: str, ok: bool | None = True, **more) -> dict:
    return {"kind": "tool", "name": name, "arguments": {}, "ok": ok, "output": "xong"} | more


def model_step(prompt: int | None, cached: int | None) -> dict:
    return {"kind": "model", "provider": "p", "prompt_tokens": prompt, "cached_tokens": cached}


async def test_the_route_counts_what_a_turn_did_and_repeats_none_of_its_words(served):
    call = ToolCall("c1", "slow", {"note": PRIVATE})
    app = served([completion(tool_calls=[call]), completion("xong rồi"), completion("ừ")])
    app.slow.release.set()
    agent = app.runtime.default.agent.id
    await collect(app.runtime.inbound.stream(app.conv.id, f"làm với {PRIVATE}"))
    await collect(app.runtime.inbound.stream(app.conv.id, f"/steer thêm {PRIVATE}"))

    answer = await app.client.get("/api/activity/usage")
    assert answer.status_code == 200
    data = answer.json()
    assert (data["days"], data["runs"]) == (30, 2)
    assert data["tools"] == {agent: {"slow": {"calls": 1, "failed": 0}}}
    assert data["commands"] == {agent: {"steer": 1}}
    cache = data["cache_by_agent"][agent]
    assert (cache["model_calls"], cache["unknown_calls"]) == (3, 3)  # the script names no cache
    assert cache["cached_share"] is None
    assert data["providers"]["scripted"]["calls"] == 3
    for nothing in ("skills", "delegations", "schedules", "hooks", "prompt_trims"):
        assert data[nothing] == {}
    assert PRIVATE not in answer.text and "xong rồi" not in answer.text


async def test_the_window_is_the_last_days_asked_for(served):
    app = served([])
    store = app.runtime.store
    store.runs.save(run("old", [tool_step("fetch_url")], started_at=stamp(40)))
    store.runs.save(run("new", [tool_step("web_search")], started_at=stamp(2)))
    old_day = utc_day(datetime.now(UTC) - timedelta(days=40))
    store.counters.add(PROMPT_TRIM, "a", day=old_day)
    store.counters.add(PROMPT_TRIM, "a")

    month = (await app.client.get("/api/activity/usage")).json()
    assert (month["runs"], list(month["tools"]["a"])) == (1, ["web_search"])
    assert month["prompt_trims"] == {"a": 1}
    longer = (await app.client.get("/api/activity/usage?days=60")).json()
    assert (longer["days"], longer["runs"]) == (60, 2)
    assert sorted(longer["tools"]["a"]) == ["fetch_url", "web_search"]
    assert longer["prompt_trims"] == {"a": 2}
    for refused in ("0", "-3", "5000", "nhiều"):
        assert (await app.client.get(f"/api/activity/usage?days={refused}")).status_code == 422


def test_tools_are_counted_per_agent_with_their_failures_and_what_scripts_called():
    runs = [
        run("r1", [tool_step("mcp__notes__find"), tool_step("mcp__notes__find", ok=False)]),
        run("r2", [tool_step("shell_run", ok=None)], agent="b"),
        run(
            "r3",
            [
                tool_step("script_run", calls=[{"name": "fetch_url"}, {"name": "fetch_url"}]),
                tool_step("fetch_url", shaped={"kind": "cut", "original_chars": 90000}),
            ],
        ),
    ]
    report = usage_report(runs, [], {})
    assert report["tools"]["a"]["mcp__notes__find"] == {"calls": 2, "failed": 1}
    assert report["tools"]["b"] == {"shell_run": {"calls": 1, "failed": 0}}
    assert report["tools_from_scripts"] == {"a": {"fetch_url": 2}}
    assert report["shaped_outputs"] == {"a": {"cut": 1}}


def test_skills_read_are_counted_by_name_and_a_name_that_is_none_is_not_repeated():
    read = [
        tool_step("skill_read", arguments={"name": "delegation"}),
        tool_step("skill_read", arguments={"name": " delegation "}),
        tool_step("skill_read", arguments={"name": f"{PRIVATE} và một câu dài"}),
        tool_step("skill_read", arguments={}),
    ]
    report = usage_report([run("r1", read)], [], {})
    assert report["skills"] == {"a": {"delegation": 2, "?": 2}}


def test_delegations_are_counted_by_what_the_task_came_to():
    said = "conversation=abc status=done spent=$0.01 steps=3 outcome={} {}"
    steps = [
        tool_step("delegate", output=said.format("done", PRIVATE)),
        tool_step("delegate", ok=False, output=said.format("blocked", "reason=denied")),
        tool_step("delegate", ok=False, output=said.format("failed", "reason=timeout")),
        tool_step("delegate", ok=False, output="Không có agent nào tên đó."),
        tool_step("delegate", ok=None, output=""),  # still waiting: it came to nothing yet
    ]
    report = usage_report([run("r1", steps)], [], {})
    assert report["delegations"] == {"a": {"done": 1, "blocked": 1, "failed": 1, NO_OUTCOME: 1}}
    assert report["tools"]["a"]["delegate"] == {"calls": 5, "failed": 3}


def test_schedules_are_counted_per_job_by_how_the_run_ended():
    runs = [
        run("r1", [], source="job:a/morning"),
        run("r2", [], source="job:a/morning", status=FAILED),
        run("r3", [], source="job:a/morning", status=HALTED),
        run("r4", [], source="job:a/weekly"),
        run("r5", [], source="chat"),
    ]
    report = usage_report(runs, [], {})
    assert report["schedules"] == {
        "a/morning": {"runs": 3, "done": 1, "failed": 1, "other": 1},
        "a/weekly": {"runs": 1, "done": 1, "failed": 0, "other": 0},
    }


def test_the_cached_share_counts_only_calls_whose_provider_said():
    steps = [model_step(1000, 750), model_step(1000, 0), model_step(500, None), model_step(0, 0)]
    providers = {
        "p": {"calls": 4, "cost_usd": 0.2, "prompt_tokens": 2000, "cached_tokens": 500},
        "q": {"calls": 0, "cost_usd": 0.0, "prompt_tokens": 0, "cached_tokens": 0},
    }
    report = usage_report([run("r1", steps)], [], providers)
    assert report["cache_by_agent"] == {
        "a": {
            "model_calls": 4,
            "prompt_tokens": 2000,
            "cached_tokens": 750,
            "unknown_calls": 1,
            "cached_share": 0.375,
        }
    }
    assert report["providers"]["p"] == providers["p"] | {"cached_share": 0.25}
    assert report["providers"]["q"]["cached_share"] is None


def test_what_the_day_counters_hold_is_laid_out_by_agent_and_name():
    store = Store(":memory:")
    for kind, name in [("hook", "PreToolUse: guard"), ("hook", "PreToolUse: guard")]:
        store.counters.add(kind, "a", name)
    store.counters.add("hook_block", "a", "PreToolUse: guard")
    store.counters.add("spill", "a", "fetch_url")
    store.counters.add(COMMAND, "b", "mk:plan")
    store.counters.add(PROMPT_TRIM, "b")
    report = usage_report([], store.counters.since(utc_day()), {})
    assert report["hooks"] == {"a": {"PreToolUse: guard": {"runs": 2, "blocks": 1}}}
    assert report["spilled_outputs"] == {"a": {"fetch_url": 1}}
    assert report["commands"] == {"b": {"mk:plan": 1}}
    assert report["prompt_trims"] == {"b": 1}
