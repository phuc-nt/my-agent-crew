"""What every agent is told about handing work out. The tool description, the roster and
the always-on `delegation` skill ride on the same prompt; when they disagree the model
follows the most concrete one, so they have to teach the same contract: hand over the
person's intent, and never grant through a task what the person did not."""

from __future__ import annotations

from pathlib import Path

import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.prompt import system_prompt_for
from my_agent_crew.agents.roster import crew_roster_section
from my_agent_crew.agents.templates_cli import SHARED_SKILLS, TEMPLATES_DIR
from my_agent_crew.config import Route
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.skills.loader import parse_skill
from my_agent_crew.store import Store
from my_agent_crew.tools.delegate import DELEGATE_TOOL_NAME
from my_agent_crew.tools.memory import build_memory_tools
from my_agent_crew.tools.memory_user import build_user_memory_tools
from tests.test_tools_delegate import agent, delegate

# The phrase all three model-facing texts share: consent comes from the person, not a task.
CONSENT = "người dùng đồng ý rõ"
SKILL = TEMPLATES_DIR / SHARED_SKILLS / "delegation.md"


@pytest.fixture
def runtime(deps_factory, store: Store) -> Runtime:
    base = deps_factory(routes=(Route("fake", "echo"),))
    agents = {"boss": agent(base, "boss", delegates=("worker",)), "worker": agent(base, "worker")}
    rt = Runtime(base.settings, store, agents, ActivityHub(store))
    rt.wire_delegation()
    return rt


def _sections(markdown: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    heading = ""
    for line in markdown.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
        sections[heading] = sections.get(heading, "") + line.lower() + "\n"
    return sections


async def test_a_task_grants_no_permission_anywhere_the_model_reads_it(runtime: Runtime):
    boss = runtime.deps_for("boss")
    description = boss.tools.get(DELEGATE_TOOL_NAME).description
    parent = runtime.store.create(agent_id="boss", autonomous=True)
    await delegate(runtime, parent.id, "call-p", task="tạo bảng mới", agent="worker")
    child = runtime.store.for_parent_call("call-p")

    assert "đồng ý rõ" in description
    _, roster = crew_roster_section(boss.profile, {p.id: p for p in runtime.profiles()})
    assert CONSENT in roster
    assert "cần người dùng đồng ý" in system_prompt_for(runtime.deps_for("worker"), child)


def test_the_always_on_skill_hands_over_intent_not_a_file_list():
    """The file list is how a coding lead splits work between editors. Taught as the
    default it made a coordinator invent `notes/alcohol.md` for a sentence about beer."""
    skill = parse_skill(SKILL.read_text(encoding="utf-8"), SKILL.stem)
    sections = _sections(SKILL.read_text(encoding="utf-8"))
    handing_out = sections["Khi giao việc"]

    assert skill.always
    assert "giao ý định" in handing_out and "task không cấp quyền" in handing_out
    assert "tệp được phép sửa" not in handing_out
    assert "tệp được phép sửa" in sections["Khi việc là sửa code"]


def test_a_delegated_agent_is_told_to_refuse_structural_changes_and_report_partial_work():
    receiving = _sections(SKILL.read_text(encoding="utf-8"))["Khi được giao việc"]

    assert "tạo bảng" in receiving and "cần người dùng đồng ý" in receiving
    assert "phần nào đã làm xong" in receiving


async def test_a_consent_block_goes_to_the_person_not_round_the_crew(runtime: Runtime):
    """The receiving agent stops with BLOCKED when a change needs the person's yes; a
    coordinator taught only "on BLOCKED, change the context" would hand the same change to
    someone less constrained, or make it itself."""
    boss = runtime.deps_for("boss")
    _, roster = crew_roster_section(boss.profile, {p.id: p for p in runtime.profiles()})
    parent = runtime.store.create(agent_id="boss", autonomous=True)
    await delegate(runtime, parent.id, "call-b", task="thêm tính năng", agent="worker")
    child = runtime.store.for_parent_call("call-b")
    general = _sections(SKILL.read_text(encoding="utf-8"))["Quy tắc chung"]

    assert "BLOCKED" in roster and "đừng tự làm thay hay giao cho agent khác" in roster
    assert "BLOCKED" in system_prompt_for(runtime.deps_for("worker"), child)
    assert "cần người dùng đồng ý" in general and "đừng giao cho agent khác" in general


def test_a_domain_record_goes_to_the_agent_that_keeps_it_not_to_memory(
    runtime: Runtime, tmp_path: Path
):
    """Told "remember I had two beers, to compare later", a coordinator saved it with the
    first tool called save: a note the health agent never reads, and a guess at the cause
    made up on the spot instead of asking the agent that holds the data."""
    boss = runtime.deps_for("boss")
    _, roster = crew_roster_section(boss.profile, {p.id: p for p in runtime.profiles()})
    memory = build_memory_tools(tmp_path / "memory", tmp_path / "MEMORY.md", tmp_path / "user")
    facts = build_user_memory_tools(tmp_path / "user", runtime.store, "boss")
    saves = [t for t in (*memory, *facts) if t.name in ("memory_save", "user_memory_save")]

    assert "đừng ghi vào memory thay" in roster and "đừng tự suy luận" in roster
    assert len(saves) == 2
    assert all(texts.MEMORY_IS_NOT_A_LEDGER in t.description for t in saves)
