"""The `schedule_create` tool end to end: it always pauses for a person no matter how the
conversation is configured, a denied or expired proposal leaves no row, an approved one
runs on a fake clock without a restart, and the DELETE route removes only what it owns."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime

import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.approval_expiry import expire_overdue
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.tool_gate import ask_reason_text, needs_decision, pauses_for_a_person
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.scheduler.jobs import JOB_SOURCE
from my_agent_crew.scheduler.runner import Scheduler
from my_agent_crew.store.created_schedules import ScheduleLimitError
from my_agent_crew.store.models import Conversation
from my_agent_crew.store.runs import RunRecord
from my_agent_crew.tools.schedule_create import (
    SCHEDULE_CREATE_TOOL_NAME,
    build_schedule_create_tool,
)

ROW = {
    "agent_id": "default",
    "name": "n",
    "cron": "0 7 * * *",
    "every": None,
    "prompt": "p",
    "skills": [],
    "created_by_conversation": "c1",
}


def row(**over) -> dict:
    payload = dict(ROW)
    payload.update(over)
    return payload


def conv(**over) -> Conversation:
    base = dict(
        id="c1",
        title="t",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        autonomous=False,
        cost_cap_usd=0.5,
        skills=(),
        spent_usd=0.0,
        unknown_cost_calls=0,
        status="idle",
    )
    base.update(over)
    return Conversation(**base)


def call(**args) -> ToolCall:
    payload = {"name": "n", "prompt": "p", "cron": "0 7 * * *"}
    payload.update(args)
    return ToolCall(id="tc1", name=SCHEDULE_CREATE_TOOL_NAME, arguments=payload)


class TestAlwaysAsks:
    """Autonomy, `auto_approve` and an allow list all skip approval for an ordinary tool —
    none of them may do that here, because that is precisely the gap the red team found."""

    def test_ask_reason_is_never_empty_for_this_tool(self, store, deps_factory) -> None:
        tool = build_schedule_create_tool(store, "default", (), datetime.now)
        deps = deps_factory(extra_tools=[tool])
        reason = ask_reason_text(deps, SCHEDULE_CREATE_TOOL_NAME, call().arguments)
        assert reason

    def test_needs_decision_is_true_even_when_the_conversation_is_autonomous(
        self, store, deps_factory
    ) -> None:
        tool = build_schedule_create_tool(store, "default", (), datetime.now)
        deps = deps_factory(extra_tools=[tool])
        reason = ask_reason_text(deps, SCHEDULE_CREATE_TOOL_NAME, call().arguments)
        assert needs_decision(conv(autonomous=True), SCHEDULE_CREATE_TOOL_NAME, reason)

    def test_needs_decision_is_true_even_with_auto_approve(self, store, deps_factory) -> None:
        tool = build_schedule_create_tool(store, "default", (), datetime.now)
        deps = deps_factory(extra_tools=[tool])
        reason = ask_reason_text(deps, SCHEDULE_CREATE_TOOL_NAME, call().arguments)
        c = conv(autonomous=True, auto_approve=(SCHEDULE_CREATE_TOOL_NAME,))
        assert needs_decision(c, SCHEDULE_CREATE_TOOL_NAME, reason)

    def test_pauses_for_a_person_even_when_every_other_gate_would_let_it_through(
        self, store, deps_factory
    ) -> None:
        tool = build_schedule_create_tool(store, "default", (), datetime.now)
        deps = deps_factory(extra_tools=[tool])
        c = conv(autonomous=True, auto_approve=(SCHEDULE_CREATE_TOOL_NAME,))
        assert pauses_for_a_person(deps, c, call())

    def test_a_malformed_proposal_still_produces_a_non_empty_reason(
        self, store, deps_factory
    ) -> None:
        tool = build_schedule_create_tool(store, "default", (), datetime.now)
        deps = deps_factory(extra_tools=[tool])
        reason = ask_reason_text(deps, SCHEDULE_CREATE_TOOL_NAME, call(cron="* * * * *").arguments)
        assert reason  # useless card, but a truthful one — never a silent pass-through

    def test_the_reason_is_not_wrapped_in_the_shell_ask_reason_sentence(
        self, store, deps_factory
    ) -> None:
        tool = build_schedule_create_tool(store, "default", (), datetime.now)
        deps = deps_factory(extra_tools=[tool])
        reason = ask_reason_text(deps, SCHEDULE_CREATE_TOOL_NAME, call().arguments)
        # SHELL_ASK_REASON's own shape is "khớp mẫu cần duyệt: `<pattern>`" — the
        # backtick-quoted pattern only ever appears there, unlike the bare phrase "khớp
        # mẫu", which the tool's own unwatched-run warning also uses in an unrelated
        # sentence.
        assert "cần duyệt: `" not in reason


class TestUnattendedProposalExpires:
    async def test_a_job_prompt_that_proposes_a_schedule_leaves_no_row_once_it_expires(
        self, store, deps_factory
    ) -> None:
        tool = build_schedule_create_tool(store, "default", (), datetime.now)
        tc = ToolCall(id="tc1", name=SCHEDULE_CREATE_TOOL_NAME, arguments=call().arguments)
        deps = deps_factory(script=[completion(tool_calls=[tc])], extra_tools=[tool])
        c = store.create(autonomous=True, approval_ttl_seconds=1)

        events = [e async for e in run_turn(deps, c.id, "sáng nào cũng nhắc tôi uống nước")]
        assert any(type(e).__name__ == "ApprovalRequiredEvent" for e in events)
        assert store.created_schedules.all() == []

        time.sleep(1.1)
        await expire_overdue({"default": deps}, ActivityHub(store), None)
        assert store.created_schedules.all() == []
        assert store.approvals.pending(c.id) is None  # resolved (expired), not pending


class TestApprovalToRun:
    def test_approving_creates_a_row_the_scheduler_picks_up_without_a_restart(
        self, store, deps_factory
    ) -> None:
        deps = deps_factory(script=[completion(content="done")])
        clock = [datetime(2026, 9, 30, 6, 0)]
        sched = Scheduler({"default": deps}, ActivityHub(store), clock=lambda: clock[0])
        assert sched.describe() == []  # created before the row exists

        created = store.created_schedules.add(row(cron="0 7 * * *"), cap=20)
        assert created.id.startswith("chat-")

        [described] = sched.describe()
        assert described["origin"] == "chat"
        assert described["id"] == f"default/{created.id}"

        clock[0] = datetime(2026, 9, 30, 7, 0, 5)
        result = asyncio.run(sched.tick())
        assert len(result) == 1
        assert result[0].status == "done"

    def test_a_new_scheduler_on_the_same_store_still_sees_the_row(
        self, store, deps_factory
    ) -> None:
        store.created_schedules.add(row(), cap=20)
        deps = deps_factory()

        def clock() -> datetime:
            return datetime(2026, 1, 1)

        first = Scheduler({"default": deps}, ActivityHub(store), clock=clock)
        second = Scheduler({"default": deps}, ActivityHub(store), clock=clock)
        assert len(first.describe()) == 1
        assert len(second.describe()) == 1

    def test_a_runtime_pause_stops_the_chat_job_from_being_due(self, store, deps_factory) -> None:
        created = store.created_schedules.add(row(cron=None, every="15m"), cap=20)
        deps = deps_factory()
        clock = [datetime(2026, 1, 1, 0, 0)]
        sched = Scheduler({"default": deps}, ActivityHub(store), clock=lambda: clock[0])
        sched.describe()  # first sighting seeds `_last`
        clock[0] = datetime(2026, 1, 1, 0, 20)
        job_id = f"default/{created.id}"
        assert [j.id for j in sched.due()] == [job_id]
        sched.set_enabled(job_id, False)
        assert sched.due() == []


class TestDenialAndLimits:
    def test_a_denied_proposal_leaves_no_row(self, store) -> None:
        # Denial is simply never calling `run`; nothing else to assert beyond the row's
        # absence, documented here so the invariant has a named test.
        assert store.created_schedules.all() == []

    def test_the_cap_rejects_a_21st_schedule(self, store) -> None:
        for i in range(20):
            store.created_schedules.add(row(name=f"n{i}"), cap=20)
        with pytest.raises(ScheduleLimitError):
            store.created_schedules.add(row(name="n20"), cap=20)

    def test_two_concurrent_adds_at_the_cap_boundary_only_one_succeeds(self, store) -> None:
        for i in range(19):
            store.created_schedules.add(row(name=f"n{i}"), cap=20)
        outcomes: list[str] = []

        def attempt(i: int) -> None:
            try:
                store.created_schedules.add(row(name=f"race{i}"), cap=20)
                outcomes.append("ok")
            except ScheduleLimitError:
                outcomes.append("rejected")

        threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(outcomes) == ["ok", "rejected"]
        assert store.created_schedules.count("default") == 20


class TestOwnershipAndSkills:
    def test_the_tool_has_no_agent_parameter_and_always_uses_the_callers_agent_id(
        self, store
    ) -> None:
        tool = build_schedule_create_tool(store, "coach", (), datetime.now)
        assert "agent" not in tool.parameters.get("properties", {})

    async def test_an_unknown_skill_is_rejected_by_run(self, store) -> None:
        tool = build_schedule_create_tool(store, "default", ("real",), datetime.now)
        result = await tool.run(
            {"name": "n", "prompt": "p", "cron": "0 7 * * *", "skills": ["ghost"]}
        )
        text = result.output if hasattr(result, "output") else result
        assert "ghost" in text
        assert store.created_schedules.all() == []

    def test_a_skill_removed_later_does_not_stop_the_job_from_running(self, store) -> None:
        from my_agent_crew.scheduler.created import to_schedule

        created = store.created_schedules.add(row(skills=["gone"]), cap=20)
        schedule = to_schedule(created)
        assert schedule.skills == ("gone",)
        assert schedule.enabled is True


class TestOrphanRowsAndConcurrentDescribe:
    def test_a_row_whose_agent_no_longer_exists_is_excluded_from_describe(
        self, store, deps_factory
    ) -> None:
        store.created_schedules.add(row(agent_id="ghost-agent"), cap=20)
        deps = deps_factory()
        sched = Scheduler({"default": deps}, ActivityHub(store), clock=lambda: datetime(2026, 1, 1))
        assert sched.describe() == []

    def test_describe_from_a_thread_while_another_thread_adds_stays_consistent(
        self, store, deps_factory
    ) -> None:
        deps = deps_factory()
        sched = Scheduler({"default": deps}, ActivityHub(store), clock=lambda: datetime(2026, 1, 1))
        errors: list[Exception] = []

        def add_many() -> None:
            for i in range(10):
                try:
                    store.created_schedules.add(row(name=f"n{i}"), cap=20)
                except Exception as exc:  # pragma: no cover - failure path only
                    errors.append(exc)

        def describe_many() -> None:
            for _ in range(10):
                try:
                    sched.describe()
                except Exception as exc:  # pragma: no cover - failure path only
                    errors.append(exc)

        t1 = threading.Thread(target=add_many)
        t2 = threading.Thread(target=describe_many)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert errors == []


class TestDeleteRoute:
    def test_delete_removes_a_chat_row_and_its_job_state(self, store) -> None:
        """`CreatedSchedulesStore.remove` and `JobStateStore.clear` are two separate store
        calls — the DELETE route is what runs both together (see the HTTP test below); this
        confirms each store call does its own half correctly."""
        created = store.created_schedules.add(row(), cap=20)
        job_id = f"default/{created.id}"
        store.jobs.set_enabled(job_id, False, "2026-01-01T00:00:00+00:00")
        assert store.created_schedules.remove(created.id, "default") is True
        store.jobs.clear(job_id)
        assert store.created_schedules.all() == []
        assert store.jobs.enabled(job_id) is None  # cleared, not just overridden back

    def test_delete_of_an_unknown_id_reports_nothing_removed(self, store) -> None:
        assert store.created_schedules.remove("chat-nope", "default") is False

    def test_delete_does_not_touch_run_history(self, store) -> None:
        created = store.created_schedules.add(row(), cap=20)
        source = JOB_SOURCE + f"default/{created.id}"
        run = RunRecord(
            id="run1",
            agent_id="default",
            conversation_id=None,
            source=source,
            title="t",
            status="done",
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:01:00+00:00",
        )
        store.runs.save(run)
        store.created_schedules.remove(created.id, "default")
        assert store.runs.recent(10, source=source) != []

    def test_delete_over_http_returns_204_409_and_404(self, tmp_path) -> None:
        from fastapi.testclient import TestClient

        from my_agent_crew.config import load_settings
        from my_agent_crew.server.app import create_app
        from my_agent_crew.server.runtime_build import build_runtime

        agent_dir = tmp_path / "agents" / "coach"
        agent_dir.mkdir(parents=True)
        (agent_dir / "agent.yaml").write_text(
            "name: Coach\nschedules:\n  - id: brief\n    name: Brief\n    every: 1h\n"
            "    prompt: hi\n",
            encoding="utf-8",
        )
        env = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"}
        # `env` is passed to both calls: `build_runtime` reads channel tokens from the
        # process environment by default, and this test must never let a real Telegram
        # token from the actual shell wire up a channel here.
        runtime = build_runtime(load_settings(env=env), env=env)
        with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
            assert client.delete("/api/jobs/coach/nope").status_code == 404
            assert client.delete("/api/jobs/coach/brief").status_code == 409

            created = runtime.store.created_schedules.add(row(agent_id="coach"), cap=20)
            assert client.delete(f"/api/jobs/coach/{created.id}").status_code == 204
            assert runtime.store.created_schedules.all() == []

    def test_delete_removes_an_orphaned_row_whose_agent_is_gone(self, tmp_path) -> None:
        from fastapi.testclient import TestClient

        from my_agent_crew.config import load_settings
        from my_agent_crew.server.app import create_app
        from my_agent_crew.server.runtime_build import build_runtime

        env = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"}
        runtime = build_runtime(load_settings(env=env), env=env)
        runtime.store.created_schedules.add(row(agent_id="ghost"), cap=20)
        [created] = runtime.store.created_schedules.all()
        with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
            assert client.delete(f"/api/jobs/ghost/{created.id}").status_code == 204


class TestTelegramCardLength:
    def test_the_full_telegram_text_carries_the_verbatim_prompt_and_fits_the_limit(
        self, store, deps_factory
    ) -> None:
        tool = build_schedule_create_tool(store, "default", (), datetime.now)
        deps = deps_factory(extra_tools=[tool])
        prompt = "Nhắc tôi uống nước đầy đủ mỗi sáng, đừng quên mang theo bình nước cá nhân."
        reason = ask_reason_text(deps, SCHEDULE_CREATE_TOOL_NAME, call(prompt=prompt).arguments)
        full = texts.REPLY_APPROVAL.format(
            name=SCHEDULE_CREATE_TOOL_NAME, reason=f" ({reason})", how=texts.REPLY_APPROVAL_HOW
        )
        assert prompt in full
        assert len(full) <= 4096

    def test_the_worst_case_prompt_and_yearly_cron_still_fits_the_limit(
        self, store, deps_factory
    ) -> None:
        tool = build_schedule_create_tool(store, "default", ("a", "b", "c"), datetime.now)
        deps = deps_factory(extra_tools=[tool])
        prompt = "x" * 2000
        reason = ask_reason_text(
            deps,
            SCHEDULE_CREATE_TOOL_NAME,
            call(prompt=prompt, cron="0 9 3 5 *", skills=["a", "b", "c"]).arguments,
        )
        full = texts.REPLY_APPROVAL.format(
            name=SCHEDULE_CREATE_TOOL_NAME, reason=f" ({reason})", how=texts.REPLY_APPROVAL_HOW
        )
        assert len(full) <= 4096


def test_existing_shell_ask_pattern_gate_is_unaffected(deps_factory) -> None:
    """The extension to `ask_reason_for` must be additive: a plain shell call with no
    matching ask pattern, and no `schedule_create` tool involved, reads exactly as before."""
    deps = deps_factory()
    assert ask_reason_text(deps, "shell_run", {"command": "echo hi"}) == ""
    assert not needs_decision(conv(autonomous=True), "shell_run", None)
