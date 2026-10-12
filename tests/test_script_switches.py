"""The two switches an owner has over what an agent does with scripts.

`script_calls: none` hands the agent no `tool_script`, whatever it holds and whatever a
server lets a script call; the script of a schedule, which the owner wrote, still runs and
still only reads. `script_llm: false` leaves the agent's scripts no model to ask, in a turn
and in a job. Both are read from the agent's own file (`agents/profile_settings.py`), set by
the editor, written back as the next start reads them, and followed by the running agent
with no restart: from its next turn and the next run of a schedule of its, while a turn
under way ends as it began. What the other words of `script_calls` do is in
`test_script_calls_setting.py`.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from textwrap import dedent

import httpx
import pytest
from fastapi.testclient import TestClient

from my_agent_crew import texts_script as t
from my_agent_crew import texts_script_llm as asking
from my_agent_crew.activity.step_previews import preview
from my_agent_crew.agents import default_profile
from my_agent_crew.agents.profile_yaml import load_yaml_profiles, parse_profile
from my_agent_crew.config import Settings, load_settings
from my_agent_crew.llm.fake import EchoProvider, ScriptedProvider, completion
from my_agent_crew.mcp.tool_search import SEARCH_TOOL
from my_agent_crew.script import limits
from my_agent_crew.script.scope import SCRIPT_TOOL, callable_tools
from my_agent_crew.script.tool import hand_script
from my_agent_crew.server.agent_assembly import build_agent_deps
from my_agent_crew.server.app import create_app
from my_agent_crew.server.crew_abilities import crew_abilities
from my_agent_crew.server.runtime_build import build_runtime
from my_agent_crew.store.runs import DONE, FAILED
from my_agent_crew.tools.shell import SHELL_TOOL_NAME
from tests.mcp_fakes import FakeMcp, make_hub, server
from tests.test_crew_roster_abilities import TOOLS as TOLD_TOOLS
from tests.test_crew_roster_abilities import crew_of, said
from tests.test_mcp_tool_search import CREATE_NAME, SEARCH_NAME
from tests.test_script_calls_setting import home_settings, manifest, write_agent
from tests.test_script_gate import agent, played, ran, shelled
from tests.test_script_job import crew as job_crew
from tests.test_script_job_gate import DUE, scheduled
from tests.test_script_model_calls import CATCHES, NOT_HERE, SORTING
from tests.test_script_store import Waits
from tests.test_script_tool import OPENED, Reads, erred, halted, play, unfinished
from tests.test_script_turns import reading

BOOLEAN = (
    "agent coach: script_calls must be none, read_only or gated, not a boolean (YAML reads a"
    " bare off, no, false, on, yes or true as one): write none to hand the agent no"
    " tool_script, or the one of the three meant"
)
NOT_A_SWITCH = "agent coach: script_llm must be true or false"


def read(home: Path) -> dict:
    return {profile.id: profile for profile in load_yaml_profiles(home_settings(home))}


# --- `script_calls: none`, as a file says it ---


def test_a_file_that_says_none_is_read_as_that_word(tmp_path: Path) -> None:
    write_agent(tmp_path, "quiet", "name: Quiet\nscript_calls: none\n")

    quiet = read(tmp_path)["quiet"]

    assert quiet.settings.script_calls == "none"
    assert quiet.to_dict()["script_calls"] == "none"


@pytest.mark.parametrize("word", ["off", "no", "false", "on", "yes", "true", "Off", "NO"])
def test_a_file_that_switches_it_with_a_yaml_boolean_is_told_which_word_to_write(
    tmp_path: Path, word: str
) -> None:
    """`off` is what switching something off is first written as, and YAML hands it over
    as a boolean: left to mean the default, the agent would keep the tool it was denied."""
    write_agent(tmp_path, "coach", f"name: Coach\nscript_calls: {word}\n")

    with pytest.raises(ValueError) as refused:
        load_yaml_profiles(home_settings(tmp_path))

    assert str(refused.value) == BOOLEAN


# --- what `none` takes from the agent, and what it leaves ---


@pytest.fixture
async def assembled(settings: Settings, store):
    """An agent as the server builds it from its profile, with what its file sets."""
    providers = {"scripted": ScriptedProvider([]), "fake": EchoProvider()}
    async with httpx.AsyncClient() as client:

        def build(**sets):
            made = default_profile(settings)
            made = replace(made, settings=replace(made.settings, **sets))
            return build_agent_deps(made, providers, client, store)

        yield build


async def test_an_agent_told_to_write_no_script_is_built_without_the_script_tool(assembled):
    reads, quiet = assembled(), assembled(script_calls="none")

    assert reads.tools.names()[-1] == SCRIPT_TOOL
    # It holds every tool a script of the other would call, and no script tool over them.
    assert callable_tools(quiet.tools) and SCRIPT_TOOL not in quiet.tools.names()
    assert quiet.tools.names() == reads.tools.names()[:-1]


async def test_a_servers_tool_a_script_may_call_brings_it_no_script_tool(deps_factory):
    hub = make_hub(FakeMcp(), server(**OPENED))
    await hub.connect()
    reads, quiet = deps_factory(), deps_factory(script_calls="none")
    own = quiet.tools.names()
    for deps in (reads, quiet):
        deps.profile = replace(deps.agent, mcp=("notion",))
        hub.attach({"default": deps})

    assert reads.tools.names() == [*own, SEARCH_TOOL, SCRIPT_TOOL, SEARCH_NAME, CREATE_NAME]
    # The server's tools are its own all the same: found with `tool_search`, called directly.
    assert quiet.tools.names() == [*own, SEARCH_TOOL, SEARCH_NAME, CREATE_NAME]
    hub.attach({"default": quiet})  # handed out again, as when a server comes back
    assert SCRIPT_TOOL not in quiet.tools.names()


async def test_the_script_of_a_schedule_still_runs_for_an_agent_handed_no_script_tool(
    deps_factory,
):
    source = 'print("đọc:", tools.rows_read())'
    rig = job_crew(
        deps_factory, source, tools=[reading("rows_read")], settings={"script_calls": "none"}
    )
    hand_script(rig.deps)  # as the server hands it out: nothing
    assert SCRIPT_TOOL not in rig.deps.tools.names()

    run = await rig.due()

    assert (run.status, run.summary, run.conversation_id) == (DONE, "đọc: rows_read", None)
    assert [call["name"] for call in run.steps[0]["calls"]] == ["rows_read"]


async def test_that_script_only_reads_as_one_of_an_agent_whose_scripts_only_read(deps_factory):
    deps, shell = agent(deps_factory, script_calls="none")
    assert SCRIPT_TOOL not in deps.tools.names()

    run = await scheduled(deps, dedent(shelled("ls -la")).strip()).run_job(DUE)

    reason = t.SCRIPT_ASKS_FIRST.format(name=SHELL_TOOL_NAME, instead="gọi trực tiếp")
    told = unfinished("trước", halted(3, reason))
    assert (run.status, run.steps[0]["output"]) == (FAILED, preview(told))
    assert shell.ran == []


def test_the_master_is_told_such_an_agent_holds_no_script_tool(deps_factory, store):
    rt = crew_of(deps_factory, store)
    assert said(rt, TOLD_TOOLS) == "như của bạn"
    helper = rt.deps_for("helper")
    gated = replace(helper.settings, script_calls="gated")
    helper.settings = gated
    rt.wire_delegation()
    assert crew_abilities(rt)["helper"].script_writes is True

    # Its file changed to `none`: the next hand-out takes the tool back and hands none.
    helper.settings = replace(gated, script_calls="none")
    rt.wire_delegation()

    assert SCRIPT_TOOL not in helper.tools.names()
    assert SCRIPT_TOOL not in crew_abilities(rt)["helper"].tools
    assert crew_abilities(rt)["helper"].script_writes is False
    assert said(rt, TOLD_TOOLS) == f"như của bạn, không có: {SCRIPT_TOOL}"


# --- `script_llm` ---


def test_scripts_ask_the_agents_model_unless_its_own_file_says_not(tmp_path: Path) -> None:
    assert Settings.__dataclass_fields__["script_llm"].default is True
    write_agent(tmp_path, "frugal", "name: Frugal\nscript_llm: false\n")
    write_agent(tmp_path, "asking", "name: Asking\nscript_llm: true\n")
    write_agent(tmp_path, "silent", "name: Silent\n")

    profiles = read(tmp_path)

    assert profiles["frugal"].settings.script_llm is False
    assert profiles["frugal"].to_dict()["script_llm"] is False
    for left in ("asking", "silent", "default"):
        assert profiles[left].settings.script_llm is True
        assert profiles[left].to_dict()["script_llm"] is True


def test_it_is_never_taken_from_the_settings_an_agent_inherits(tmp_path: Path) -> None:
    inherited = replace(home_settings(tmp_path), script_llm=False)

    made = parse_profile("coach", tmp_path / "agents" / "coach", {"name": "Coach"}, inherited)

    assert made.settings.script_llm is True


@pytest.mark.parametrize(
    "value", ["false", "true", "no", "off", "", 0, 1, None, ["false"]], ids=repr
)
def test_only_a_real_boolean_switches_it(tmp_path: Path, value) -> None:
    """`"false"` taken for a truth would leave the scripts paying for a model on exactly
    the agent somebody meant to stop."""
    raw = {"name": "Coach", "script_llm": value}
    with pytest.raises(ValueError) as refused:
        parse_profile("coach", tmp_path / "agents" / "coach", raw, home_settings(tmp_path))
    assert str(refused.value) == NOT_A_SWITCH


@pytest.mark.parametrize("mode", ["read_only", "gated"])
def test_an_agent_whose_scripts_ask_no_model_is_told_of_none(deps_factory, mode):
    tools = [Reads("row_read").tool]
    asks = deps_factory(extra_tools=tools, script_calls=mode)
    frugal = deps_factory(extra_tools=tools, script_calls=mode, script_llm=False)
    for deps in (asks, frugal):
        hand_script(deps)

    told, untold = (deps.tools.get(SCRIPT_TOOL).description for deps in (asks, frugal))
    assert "llm.classify(text, labels)" in told and "llm" not in untold
    # Nothing else of what it is told changes: only the paragraph about the model is gone.
    assert told.startswith(untold) and told != untold


async def test_a_script_that_asks_all_the_same_is_refused_and_no_model_is_asked(deps_factory):
    model = ScriptedProvider([completion("Rác.", cost_usd=0.004)])
    frugal = deps_factory(
        providers={"scripted": model}, extra_tools=[Reads("row_read").tool], script_llm=False
    )
    hand_script(frugal)

    caught = await play(frugal.tools, CATCHES)
    uncaught = await play(frugal.tools, SORTING)

    # A mistake of the script's like any other: it may catch it, and made no call.
    assert (caught.ok, caught.output) == (True, f"bắt được: {NOT_HERE}\nchạy tiếp")
    assert (uncaught.ok, uncaught.output) == (False, unfinished(erred(2, NOT_HERE)))
    assert caught.calls == uncaught.calls == () and model.requests == []


ASKS_ON = """
    for n in range(12):
        try:
            llm.classify("mua ngay kẻo hết", ["rác", "thường"])
        except Exception:
            print("lần", n)
    """


async def test_an_asking_refused_for_want_of_a_model_is_still_one_the_script_counts(deps_factory):
    model = ScriptedProvider([completion("Rác.", cost_usd=0.004)])
    frugal = deps_factory(
        providers={"scripted": model}, extra_tools=[Reads("row_read").tool], script_llm=False
    )
    hand_script(frugal)

    result = await play(frugal.tools, ASKS_ON)

    # A script counts what it asked however it was answered, so one that catches each
    # refusal and asks on is ended by the asking past the most it may make.
    most = limits.MAX_LLM_CALLS
    refused = [f"lần {n}" for n in range(most)]
    ended = halted(4, asking.LLM_TOO_MANY_CALLS.format(most=most))
    assert (result.ok, result.output) == (False, unfinished(*refused, ended))
    # None of them was a call anyone made: nothing is on the run card and no model heard.
    assert result.calls == () and model.requests == []


async def test_a_schedules_script_of_such_an_agent_asks_no_model_either(deps_factory):
    rig = job_crew(
        deps_factory,
        SORTING,
        "Nhắn lại:",
        says=[completion("Rác.", cost_usd=0.004)],
        settings={"script_llm": False},
    )

    run = await rig.due()

    assert (run.status, run.conversation_id) == (FAILED, None)
    assert run.steps[0]["output"] == preview(unfinished(erred(1, NOT_HERE)))
    assert run.steps[0].get("calls", []) == [] and run.spent_usd == 0
    assert rig.model.requests == [] and rig.deps.store.list() == []


# --- set from the web, on an agent that is running ---


@pytest.fixture
def served(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
        yield client, runtime, home


def script_tool_of(runtime):
    return runtime.deps_for("coder").tools.get(SCRIPT_TOOL)


def patch(client, **profile):
    return client.patch("/api/agents/coder", json={"profile": profile})


def test_the_editor_takes_the_script_tool_from_a_running_agent_and_hands_it_back(served):
    client, runtime, home = served
    assert script_tool_of(runtime) is not None

    reply = patch(client, script_calls="none")

    assert reply.status_code == 200 and reply.json()["restart_required"] == []
    assert reply.json()["profile"]["script_calls"] == "none"
    assert client.get("/api/agents/coder").json()["script_calls"] == "none"
    assert script_tool_of(runtime) is None
    assert SCRIPT_TOOL not in reply.json()["profile"]["tools"]
    held = {tool["name"] for tool in client.get("/api/agents/coder").json()["tools"]}
    assert "workspace_read" in held and SCRIPT_TOOL not in held
    # Written as the next start reads it: the word, and not YAML's null.
    assert "script_calls: none\n" in manifest(home)
    assert read(home)["coder"].settings.script_calls == "none"

    reply = patch(client, script_calls="read_only")

    assert reply.status_code == 200 and script_tool_of(runtime) is not None
    assert read(home)["coder"].settings.script_calls == "read_only"


def test_the_editor_takes_the_model_from_a_running_agents_scripts_and_hands_it_back(served):
    client, runtime, home = served
    assert client.get("/api/agents/coder").json()["script_llm"] is True
    assert "llm.classify" in script_tool_of(runtime).description

    reply = patch(client, script_llm=False)

    assert reply.status_code == 200 and reply.json()["restart_required"] == []
    assert reply.json()["profile"]["script_llm"] is False
    assert client.get("/api/agents/coder").json()["script_llm"] is False
    assert runtime.deps_for("coder").settings.script_llm is False
    assert "llm" not in script_tool_of(runtime).description
    assert "script_llm: false\n" in manifest(home)
    assert read(home)["coder"].settings.script_llm is False

    reply = patch(client, script_llm=None)  # cleared: back to what an agent has unsaid

    assert reply.status_code == 200 and reply.json()["profile"]["script_llm"] is True
    assert "script_llm" not in manifest(home)
    assert "llm.classify" in script_tool_of(runtime).description


# --- when a save holds ---


async def test_a_turn_under_way_ends_as_it_began_and_the_next_begins_as_saved(served):
    """A turn takes its agent once, as it begins (`inbound.py`). A save puts another agent in
    the crew in its place and leaves the one the turn took as it was (`server/runtime.py`).
    So the switches hold from the next turn: the one under way keeps the script tool it
    began with, and its scripts keep the model they could ask."""
    client, runtime, _ = served
    conv = runtime.store.create(agent_id="coder")
    held, waits = runtime.inbound.deps_for_conversation(conv.id), Waits()
    held.tools.register(waits.tool)
    script = asyncio.create_task(played(held, conv.id, 'tools.hung_read()\nprint("xong")'))
    await waits.entered.wait()

    saved = patch(client, script_calls="none", script_llm=False)
    assert saved.status_code == 200 and saved.json()["restart_required"] == []
    waits.go.set()
    result, _ = await script

    # The script that was running ends well, and the turn may write another that asks.
    assert (result.ok, result.output) == (True, "xong")
    assert held.tools.get(SCRIPT_TOOL) is not None
    assert "llm.classify" in held.tools.get(SCRIPT_TOOL).description
    assert (held.settings.script_calls, held.settings.script_llm) == ("read_only", True)
    asked = await ran(held, conv, 'print("hỏi được:", len(llm.summarise("thư dài")) > 0)')
    assert (asked.ok, asked.output) == (True, "hỏi được: True")
    # The next turn of the same conversation takes the agent as it was saved.
    fresh = runtime.inbound.deps_for_conversation(conv.id)
    assert fresh is not held and fresh is runtime.deps_for("coder")
    assert fresh.tools.get(SCRIPT_TOOL) is None
    assert (fresh.settings.script_calls, fresh.settings.script_llm) == ("none", False)


ASKS_EACH_MORNING = """\
name: Coder
routes: [fake:echo]
schedules:
  - id: due
    name: Tóm tắt thư
    cron: '0 7 * * *'
    script: |
      print(len(llm.summarise("Kính gửi anh Phúc, đơn HP3-12 đã giao hôm qua.")) > 0)
"""


async def test_the_next_run_of_a_schedule_begins_with_the_agent_as_saved(tmp_path: Path):
    """The clock takes the agent each time a job runs (`scheduler/runner.py`), from the crew
    a save changes. The schedule itself stays as the start read it."""
    home = tmp_path / "home"
    write_agent(home, "coder", ASKS_EACH_MORNING)
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        before = await runtime.scheduler.run_job("coder/due")
        saved = patch(client, script_llm=False)
        after = await runtime.scheduler.run_job("coder/due")

    assert (before.status, before.summary) == (DONE, "True")
    assert saved.status_code == 200 and saved.json()["restart_required"] == []
    assert (after.status, after.conversation_id) == (FAILED, None)
    assert after.steps[0]["output"] == preview(unfinished(erred(1, NOT_HERE)))


def test_an_edit_about_something_else_keeps_both(served):
    client, runtime, home = served
    patch(client, script_calls="none", script_llm=False)

    reply = patch(client, description="viết mã")

    assert reply.status_code == 200
    kept = reply.json()["profile"]
    assert (kept["script_calls"], kept["script_llm"]) == ("none", False)
    assert "script_calls: none\n" in manifest(home) and "script_llm: false\n" in manifest(home)
    assert script_tool_of(runtime) is None


def test_a_new_agent_may_be_made_with_both(served):
    client, runtime, home = served

    reply = client.post(
        "/api/agents",
        json={"agent_id": "quiet", "profile": {"script_calls": "none", "script_llm": False}},
    )

    assert reply.status_code == 201
    made = reply.json()["profile"]
    assert (made["script_calls"], made["script_llm"]) == ("none", False)
    assert runtime.deps_for("quiet").tools.get(SCRIPT_TOOL) is None
    written = read(home)["quiet"].settings
    assert (written.script_calls, written.script_llm) == ("none", False)


@pytest.mark.parametrize("value", ["false", "no", 0, 1, ["false"]], ids=repr)
def test_the_editor_refuses_what_is_no_boolean_before_it_is_written(served, value):
    client, runtime, home = served
    before = manifest(home)

    reply = patch(client, script_llm=value)

    assert reply.status_code == 422
    assert reply.json()["detail"] == "agent coder: script_llm must be true or false"
    assert manifest(home) == before
    assert "llm.classify" in script_tool_of(runtime).description


@pytest.mark.parametrize("value", [False, True], ids=repr)
def test_the_editor_tells_a_boolean_for_script_calls_which_word_to_send(served, value):
    client, runtime, home = served
    before = manifest(home)

    reply = patch(client, script_calls=value)

    assert reply.status_code == 422
    assert reply.json()["detail"] == BOOLEAN.replace("coach", "coder")
    assert manifest(home) == before and script_tool_of(runtime) is not None
