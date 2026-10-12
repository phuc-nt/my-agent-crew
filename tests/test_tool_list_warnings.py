"""What a start says about the names in an agent's `tools:` list.

The list is matched against the tools built with the agent, and some tools are handed
later or by something else: `delegate` once every agent exists, `tool_script` by what the
agent was left to read, `tool_search` and a server's tools by the servers it names, and
three tools by the work mode. None of those is a name nobody knows. Each test starts a
whole crew, so the order things are wired in cannot bring a false warning back unseen.
"""

import logging
from pathlib import Path

import pytest
import yaml

from my_agent_crew.agents import DEFAULT_AGENT_ID
from my_agent_crew.config import load_settings
from my_agent_crew.server import build_runtime


def said(caplog) -> list[str]:
    """What was said about a `tools:` list, and nothing else a start warns of."""
    return [r.getMessage() for r in caplog.records if "tools lists" in r.getMessage()]


def started(home: Path, caplog, **agents):
    for agent_id, raw in agents.items():
        # The master's file is the home's own; everyone else has a folder under `agents/`.
        directory = home if agent_id == DEFAULT_AGENT_ID else home / "agents" / agent_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "agent.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    with caplog.at_level(logging.WARNING):
        runtime = build_runtime(load_settings(env=env))
    return runtime, said(caplog)


@pytest.mark.parametrize(
    ("agent_id", "raw"),
    [
        ("lead", {"mode": "work", "tools": ["shell_run", "delegate"]}),
        ("planner", {"delegates": ["helper"], "tools": ["workspace_read", "delegate"]}),
        ("default", {"tools": ["workspace_read", "delegate"]}),
    ],
    ids=["a work agent", "an agent that names delegates", "the master"],
)
def test_an_agent_that_hands_work_out_may_list_delegate_without_a_word(
    tmp_path: Path, caplog, agent_id, raw
) -> None:
    runtime, warnings = started(tmp_path, caplog, helper={}, **{agent_id: raw})

    # Naming it is how delegation is kept under a chosen list (`Runtime.delegates`).
    assert runtime.deps_for(agent_id).agent.tools == tuple(raw["tools"])
    assert "delegate" in runtime.deps_for(agent_id).tools.names()
    assert warnings == []


def test_a_name_no_tool_carries_is_still_called_unknown(tmp_path: Path, caplog) -> None:
    _, warnings = started(tmp_path, caplog, coder={"tools": ["shell_run", "typo_tool"]})

    assert warnings == ["agent coder: tools lists unknown tool typo_tool"]


def test_a_tool_that_needs_a_key_stays_unmentioned_on_a_machine_without_it(
    tmp_path: Path, caplog
) -> None:
    runtime, warnings = started(tmp_path, caplog, coder={"tools": ["shell_run", "image_read"]})

    assert "image_read" not in runtime.deps_for("coder").tools.names()
    assert warnings == []


def test_delegate_listed_by_an_agent_with_nobody_to_hand_work_to_says_so(
    tmp_path: Path, caplog
) -> None:
    runtime, warnings = started(tmp_path, caplog, coder={"tools": ["shell_run", "delegate"]})

    # Not the master, no work agent, no `delegates`: the name is known and gives nothing.
    assert "delegate" not in runtime.deps_for("coder").tools.names()
    (warning,) = warnings
    assert warning.startswith("agent coder: tools lists delegate, ")
    assert "unknown" not in warning
    assert "hands work to nobody" in warning


@pytest.mark.parametrize("name", ["tool_script", "tool_search", "mcp__notion__search"])
def test_a_tool_the_list_does_not_decide_is_said_to_be_none_of_its_business(
    tmp_path: Path, caplog, name
) -> None:
    runtime, warnings = started(tmp_path, caplog, coder={"tools": ["shell_run", name]})

    # Naming it gave the agent nothing: a shell alone leaves a script no tool to call,
    # and the agent names no server.
    assert name not in runtime.deps_for("coder").tools.names()
    (warning,) = warnings
    assert warning.startswith(f"agent coder: tools lists {name}, ")
    assert "unknown" not in warning
    assert "the list does not decide" in warning


def test_the_script_tool_comes_whether_or_not_the_list_names_it(tmp_path: Path, caplog) -> None:
    runtime, warnings = started(
        tmp_path,
        caplog,
        named={"tools": ["workspace_read", "tool_script"]},
        unnamed={"tools": ["workspace_read"]},
    )

    assert "tool_script" in runtime.deps_for("named").tools.names()
    assert "tool_script" in runtime.deps_for("unnamed").tools.names()
    (warning,) = warnings
    assert warning.startswith("agent named: tools lists tool_script, ")
    assert "unknown" not in warning


@pytest.mark.parametrize("name", ["workspace_edit", "workspace_grep", "workspace_glob"])
def test_a_work_agents_tool_on_an_assistants_list_is_said_to_need_the_mode(
    tmp_path: Path, caplog, name
) -> None:
    runtime, warnings = started(
        tmp_path,
        caplog,
        assistant={"tools": ["shell_run", name]},
        worker={"mode": "work", "tools": ["shell_run", name]},
    )

    assert name in runtime.deps_for("worker").tools.names()
    assert name not in runtime.deps_for("assistant").tools.names()
    (warning,) = warnings
    assert warning.startswith(f"agent assistant: tools lists {name}, ")
    assert "unknown" not in warning
    assert "mode: work" in warning


def test_wiring_an_edited_agent_in_says_nothing_of_a_list_that_is_right(
    tmp_path: Path, caplog
) -> None:
    runtime, first = started(
        tmp_path,
        caplog,
        lead={"mode": "work", "tools": ["shell_run", "delegate"]},
        coder={"tools": ["shell_run", "delegate"]},
    )
    caplog.clear()

    with caplog.at_level(logging.WARNING):
        runtime.replace_agent(runtime.deps_for("lead").agent)

    # The lead's list is right, and the coder's was told of once, when it was built.
    assert [line.split(":")[0] for line in first] == ["agent coder"]
    assert said(caplog) == []
    assert "delegate" in runtime.deps_for("lead").tools.names()
