"""shell_run: runs in the agent workspace, merges stderr, times out, needs approval."""

from pathlib import Path

from my_agent_crew import texts
from my_agent_crew.agent.events import ApprovalRequiredEvent, DoneEvent, ToolResultEvent
from my_agent_crew.agent.loop import resolve_approval, run_turn
from my_agent_crew.tools.registry import ToolRegistry
from my_agent_crew.tools.shell import ask_reason, build_shell_tool, run_shell
from tests.conftest import collect


async def test_runs_in_cwd_and_merges_stderr(tmp_path: Path):
    (tmp_path / "hello.txt").write_text("xin chào")
    code, output = await run_shell("cat hello.txt; echo oops >&2", tmp_path, timeout_s=10)
    assert code == 0 and "xin chào" in output and "oops" in output


async def test_timeout_kills_the_process(tmp_path: Path):
    code, output = await run_shell("sleep 5", tmp_path, timeout_s=0.2)
    assert code is None and output == ""
    reg = ToolRegistry([build_shell_tool(tmp_path)])
    result = await reg.execute("shell_run", {"command": "sleep 5", "timeout_s": 0.2})
    assert result.ok is False and texts.SHELL_TIMEOUT.format(seconds=0) in result.output


async def test_tool_reports_exit_code_and_requires_approval(tmp_path: Path):
    tool = build_shell_tool(tmp_path)
    assert tool.requires_approval is True
    reg = ToolRegistry([tool])
    ok = await reg.execute("shell_run", {"command": "printf done"})
    assert ok.ok and ok.output == "done"
    silent = await reg.execute("shell_run", {"command": "true"})
    assert silent.output == texts.SHELL_NO_OUTPUT
    failed = await reg.execute("shell_run", {"command": "echo bad; exit 3"})
    assert failed.ok is False and "Lệnh thoát với mã 3.\nbad" in failed.output
    missing = await reg.execute("shell_run", {"command": "true", "timeout_s": 1})
    assert missing.ok
    gone = ToolRegistry([build_shell_tool(tmp_path / "nope")])
    result = await gone.execute("shell_run", {"command": "true"})
    assert result.ok is False and "không tồn tại" in result.output


async def test_echo_provider_shell_call_pauses_then_runs_after_approval(deps_factory):
    from my_agent_crew.config import Route

    deps = deps_factory(routes=(Route("fake", "echo"),))
    conv = deps.store.create()
    paused = await collect(run_turn(deps, conv.id, '/tool shell_run {"command": "echo hi"}'))
    assert isinstance(paused[-1], ApprovalRequiredEvent) and paused[-1].name == "shell_run"
    events = await collect(resolve_approval(deps, conv.id, paused[-1].approval_id, True))
    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result.ok and result.output == "hi\n"
    assert isinstance(events[-1], DoneEvent)


async def test_autonomous_conversation_runs_shell_without_asking(deps_factory):
    from my_agent_crew.config import Route

    deps = deps_factory(routes=(Route("fake", "echo"),))
    conv = deps.store.create(autonomous=True)
    events = await collect(run_turn(deps, conv.id, '/tool shell_run {"command": "pwd"}'))
    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result.ok and result.output.strip() == str(deps.agent.workspace.resolve())
    assert not any(isinstance(e, ApprovalRequiredEvent) for e in events)


def test_the_ask_list_matches_a_substring_whatever_the_case():
    patterns = ("rm -rf", "sudo ")
    assert ask_reason("cd /tmp && RM -rf build", patterns) == "rm -rf"
    assert ask_reason("sudo  launchctl list", patterns) == "sudo "
    assert ask_reason("ls -la ~/Downloads", patterns) is None
    assert ask_reason("rm -rf /", ()) is None


async def test_an_autonomous_shell_command_on_the_ask_list_still_waits(deps_factory):
    """Autonomous is the user's choice and stays; this guard is added on top of it, for
    the shapes where running first and asking later cannot be undone."""
    from my_agent_crew.config import Route

    deps = deps_factory(routes=(Route("fake", "echo"),))
    conv = deps.store.create(autonomous=True)
    events = await collect(
        run_turn(deps, conv.id, '/tool shell_run {"command": "rm -rf ./scratch"}')
    )
    approval = events[-1]
    assert isinstance(approval, ApprovalRequiredEvent) and approval.name == "shell_run"
    assert approval.reason == texts.SHELL_ASK_REASON.format(pattern="rm -rf")
    assert not any(isinstance(e, ToolResultEvent) for e in events)


async def test_an_empty_ask_list_turns_the_extra_guard_off(deps_factory):
    from my_agent_crew.config import Route

    deps = deps_factory(routes=(Route("fake", "echo"),), shell_ask_patterns=())
    conv = deps.store.create(autonomous=True)
    events = await collect(
        run_turn(deps, conv.id, '/tool shell_run {"command": "rm -rf ./scratch"}')
    )
    assert not any(isinstance(e, ApprovalRequiredEvent) for e in events)
    assert next(e for e in events if isinstance(e, ToolResultEvent)).ok


async def test_an_autonomous_agent_clears_its_own_temp_sandbox_without_asking(deps_factory):
    """The cleanup an agent does after itself is the one destructive shape that runs, so
    an unattended turn is not stopped by work that deletes nothing of the person's."""
    import tempfile

    from my_agent_crew.config import Route

    deps = deps_factory(routes=(Route("fake", "echo"),))
    conv = deps.store.create(autonomous=True)
    sandbox = Path(tempfile.gettempdir()) / "tmp.crew-cleanup-probe"
    sandbox.mkdir(exist_ok=True)
    events = await collect(
        run_turn(deps, conv.id, f'/tool shell_run {{"command": "rm -rf {sandbox}"}}')
    )
    assert not any(isinstance(e, ApprovalRequiredEvent) for e in events)
    assert next(e for e in events if isinstance(e, ToolResultEvent)).ok
    assert not sandbox.exists()


async def test_a_delete_reaching_outside_the_sandbox_still_waits(deps_factory):
    """Same `rm -rf`, but the path leaves the temp root: the guard is back."""
    import tempfile

    from my_agent_crew.config import Route

    deps = deps_factory(routes=(Route("fake", "echo"),))
    conv = deps.store.create(autonomous=True)
    escape = f"{tempfile.gettempdir()}/../../Users"
    events = await collect(
        run_turn(deps, conv.id, f'/tool shell_run {{"command": "rm -rf {escape}"}}')
    )
    approval = events[-1]
    assert isinstance(approval, ApprovalRequiredEvent)
    assert approval.reason == texts.SHELL_ASK_REASON.format(pattern="rm -rf")
    assert not any(isinstance(e, ToolResultEvent) for e in events)


async def test_a_matching_command_asks_the_same_way_when_not_autonomous(deps_factory):
    from my_agent_crew.config import Route

    deps = deps_factory(routes=(Route("fake", "echo"),))
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, '/tool shell_run {"command": "sudo ls"}'))
    approval = events[-1]
    assert isinstance(approval, ApprovalRequiredEvent)
    assert approval.reason == texts.SHELL_ASK_REASON.format(pattern="sudo ")
