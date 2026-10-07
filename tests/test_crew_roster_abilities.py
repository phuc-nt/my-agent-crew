"""The master is told what each agent of the running crew holds right now: read from the
runtime every time its prompt is built (`server/crew_abilities.py`), so whatever an agent
gains or loses is in the very next prompt with nobody rewriting a description."""

from __future__ import annotations

from dataclasses import replace
from itertools import takewhile

import httpx

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.agent.prompt import system_prompt_for
from my_agent_crew.agents import DEFAULT_AGENT_ID
from my_agent_crew.agents.profile import ASSISTANT
from my_agent_crew.agents.schedule import Schedule
from my_agent_crew.config_parse import Route
from my_agent_crew.llm.fake import completion
from my_agent_crew.mcp import hub
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.skills import Skill
from my_agent_crew.store import Store
from my_agent_crew.tools.registry import ToolRegistry
from tests.conftest import collect
from tests.mcp_fakes import FakeMcp, make_hub, server

SERVICES, SKILLS, JOBS, TOOLS, MODEL = (
    f"  · {kind}: "
    for kind in ("Dịch vụ ngoài (MCP)", "Kỹ năng", "Việc tự chạy theo lịch", "Công cụ", "Mô hình")
)
BRIEF = Schedule(id="brief", name="Bản tin sáng", cron="0 7 * * *", prompt="p")


def crew_of(deps_factory, store: Store, **helper) -> Runtime:
    """The master and one helper built alike, each with a toolbox and skills of its own."""
    base = deps_factory([completion("ok"), completion("ok")])

    def own(profile) -> AgentDeps:
        tools = ToolRegistry([base.tools.get(name) for name in base.tools.names()])
        return replace(base, profile=profile, tools=tools, skills=list(base.skills))

    peer = replace(base.profile, id="helper", name="Helper", mode=ASSISTANT, **helper)
    agents = {DEFAULT_AGENT_ID: own(base.profile), "helper": own(peer)}
    peers = {agent_id: deps.agent for agent_id, deps in agents.items()}
    for deps in agents.values():
        deps.peers = peers
    rt = Runtime(base.settings, store, agents, ActivityHub(store))
    rt.wire_delegation()
    return rt


def told(rt: Runtime) -> list[str]:
    """What the master's prompt says, right now, under the helper's line of the roster."""
    lines = system_prompt_for(rt.default).splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("- helper — ")) + 1
    return list(takewhile(lambda line: line.startswith("  · "), lines[start:]))


def said(rt: Runtime, kind: str) -> str | None:
    return next((line.removeprefix(kind) for line in told(rt) if line.startswith(kind)), None)


def test_a_tool_an_agent_is_given_is_in_the_masters_next_prompt(deps_factory, store):
    rt = crew_of(deps_factory, store)
    helper = rt.deps_for("helper")
    assert said(rt, TOOLS) == "như của bạn"

    helper.tools.register(replace(helper.tools.get("workspace_read"), name="garmin_sync"))
    assert said(rt, TOOLS) == "như của bạn, thêm: garmin_sync"

    helper.tools = helper.tools.without("garmin_sync", "shell_run")
    assert said(rt, TOOLS) == "như của bạn, không có: shell_run"


def test_the_tool_that_hands_work_out_is_nobodys_to_compare(deps_factory, store):
    rt = crew_of(deps_factory, store)
    assert "delegate" in rt.default.tools.names()
    assert "delegate" not in rt.deps_for("helper").tools.names()
    # The helper lacks it and is still "like yours": a turn handed work never holds it.
    assert said(rt, TOOLS) == "như của bạn"


def test_a_skill_an_agent_is_given_is_told_with_what_it_is_for(deps_factory, store):
    rt = crew_of(deps_factory, store)
    assert said(rt, SKILLS) == "như của bạn"
    rt.deps_for("helper").skills.append(Skill("goodreads", "Tra sách trên Goodreads", "…"))
    assert said(rt, SKILLS) == "như của bạn, thêm: goodreads (Tra sách trên Goodreads)"


def test_only_the_jobs_that_will_run_are_told(deps_factory, store):
    schedules = (
        BRIEF,
        replace(BRIEF, id="off", name="Đang tắt", enabled=False),
        replace(BRIEF, id="tidy", name="Dọn bộ nhớ", prompt=None, consolidate=True),
    )
    rt = crew_of(deps_factory, store, schedules=schedules)
    assert said(rt, JOBS) == "Bản tin sáng"

    rt.scheduler.set_enabled("helper/off", True)
    assert said(rt, JOBS) == "Bản tin sáng, Đang tắt"
    rt.scheduler.set_enabled("helper/brief", False)
    rt.scheduler.set_enabled("helper/off", False)
    assert said(rt, JOBS) is None


def test_a_job_nobody_named_is_told_by_its_id(deps_factory, store):
    rt = crew_of(deps_factory, store, schedules=(BRIEF, replace(BRIEF, id="weekly", name="")))
    assert said(rt, JOBS) == "Bản tin sáng, weekly"


def test_a_job_made_in_a_chat_is_told_as_soon_as_it_exists(deps_factory, store):
    rt = crew_of(deps_factory, store, schedules=(BRIEF,))
    row = {
        "agent_id": "helper",
        "name": "Nhắc uống nước",
        "cron": "0 9 * * *",
        "every": None,
        "prompt": "p",
        "skills": [],
        "created_by_conversation": "c1",
    }
    store.created_schedules.add(row, cap=20)
    assert said(rt, JOBS) == "Bản tin sáng, Nhắc uống nước"
    # A job of the master's own is not the helper's to be handed work for.
    store.created_schedules.add({**row, "agent_id": DEFAULT_AGENT_ID, "name": "Của tôi"}, cap=20)
    assert said(rt, JOBS) == "Bản tin sáng, Nhắc uống nước"


def test_the_model_is_told_with_where_a_stuck_turn_moves_only_when_it_can(deps_factory, store):
    rt = crew_of(deps_factory, store)
    helper = rt.deps_for("helper")
    assert said(rt, MODEL) == "m"

    # The route tried first is the one a turn of it runs on; the rest only stand behind it.
    routes = (Route("scripted", "small"), Route("scripted", "spare"))
    helper.settings = replace(helper.settings, routes=routes, escalation_route=Route("x", "big"))
    # Named, and no provider to move to: a turn of it never moves there.
    assert said(rt, MODEL) == "small"
    helper.escalation = helper.chain
    assert said(rt, MODEL) == "small; khi bí thì tự chuyển sang big"


async def with_notion(deps_factory, store, fake: FakeMcp | None = None, **settings) -> Runtime:
    """The helper names the server (twice over, and one that is not configured), and the
    crew connects the way a start does."""
    rt = crew_of(deps_factory, store, mcp=("notion", "gone", "notion"))
    rt.mcp = make_hub(fake or FakeMcp(), server(**settings))
    await rt.mcp.connect()
    rt.mcp.attach(rt.agents)
    return rt


async def test_a_server_an_agent_is_given_is_told_with_whether_it_writes(deps_factory, store):
    rt = await with_notion(deps_factory, store, description="Sổ ghi chú của người dùng")
    assert said(rt, SERVICES) == "notion (đọc và ghi) — Sổ ghi chú của người dùng"
    # The master holds none of it: the roster is the only place it hears of the server.
    assert not [name for name in rt.default.tools.names() if name.startswith("mcp__")]
    assert "mcp__notion" not in "".join(told(rt))
    assert said(rt, TOOLS) == "như của bạn, thêm: tool_search"


async def test_a_server_whose_tools_all_only_read_is_told_so(deps_factory, store):
    rt = await with_notion(deps_factory, store, read_only=["search"])
    assert said(rt, SERVICES) == "notion (đọc và ghi)"

    rt = await with_notion(deps_factory, store, read_only=["*"])
    assert said(rt, SERVICES) == "notion (chỉ đọc)"

    # The one tool that writes is kept from agents: what the helper holds only reads.
    hidden = {"create-page": "hidden"}
    rt = await with_notion(deps_factory, store, read_only=["search"], tool_exposure=hidden)
    assert said(rt, SERVICES) == "notion (chỉ đọc)"


async def test_a_server_kept_from_agents_is_not_told_at_all(deps_factory, store):
    rt = await with_notion(deps_factory, store, exposure="hidden")
    assert rt.mcp.links["notion"].status == hub.CONNECTED
    assert said(rt, SERVICES) is None


async def test_a_server_that_wants_a_sign_in_is_told_as_waiting_for_the_owner(deps_factory, store):
    rt = await with_notion(deps_factory, store, FakeMcp(oauth=True))
    assert rt.mcp.links["notion"].status == hub.SIGNED_OUT
    assert said(rt, SERVICES) == f"notion ({texts.CREW_SERVICE_SIGNED_OUT})"


async def test_a_server_that_went_down_is_told_as_out_of_reach_until_it_is_back(
    deps_factory, store
):
    fake = FakeMcp()
    rt = await with_notion(deps_factory, store, fake)
    assert said(rt, SERVICES) == "notion (đọc và ghi)"

    fake.before = lambda request, message: httpx.Response(503)
    await rt.mcp.connect(["notion"])
    rt.mcp.attach(rt.agents)
    assert rt.mcp.links["notion"].status == hub.FAILED
    assert said(rt, SERVICES) == f"notion ({texts.CREW_SERVICE_DOWN})"

    fake.before = None
    await rt.mcp.connect(["notion"])
    rt.mcp.attach(rt.agents)
    assert said(rt, SERVICES) == "notion (đọc và ghi)"


async def test_a_turn_of_the_master_reads_it_and_a_turn_handed_work_does_not(deps_factory, store):
    rt = await with_notion(deps_factory, store)
    master = rt.deps_for(DEFAULT_AGENT_ID)
    await collect(run_turn(master, store.create(agent_id=DEFAULT_AGENT_ID).id, "chào"))
    system = master.chain.providers["scripted"].requests[0].messages[0].content
    assert "- helper — Helper (assistant)" in system
    assert "\n  · Dịch vụ ngoài (MCP): notion (đọc và ghi)\n" in system
    assert texts.CREW_ROSTER_ABILITIES_NOTE in system

    child = rt.deps_for_child(DEFAULT_AGENT_ID)
    assert child.crew is master.crew
    assert texts.CREW_ROSTER_ABILITIES_NOTE not in system_prompt_for(child)
    assert "  · " not in system_prompt_for(child)
