"""Kit hooks around tool calls: read from `settings.json` in the Claude Code shape, run
with the call on stdin, blocking on exit 2 or a JSON verdict, and letting the call
through on any failure of their own."""

from __future__ import annotations

import json
from pathlib import Path

from my_agent_crew import texts
from my_agent_crew.agents.kit import Kit
from my_agent_crew.agents.kit_hooks import POST, PRE, Hook, load_hooks, parse_hooks
from my_agent_crew.tools import Tool, ToolRegistry
from my_agent_crew.tools.hooks import HookRunner, read_outcome

SETTINGS = {
    "hooks": {
        "PreToolUse": [
            {"matcher": "Bash|Write", "hooks": [{"type": "command", "command": "guard"}]},
            {"matcher": "", "hooks": [{"type": "prompt", "prompt": "not a command"}]},
        ],
        "PostToolUse": [{"matcher": "*", "hooks": [{"command": "audit", "timeout": 5}]}],
        "Stop": [{"hooks": [{"type": "command", "command": "ignored"}]}],
    }
}


def test_parse_hooks_reads_command_hooks_and_matches_our_names_through_aliases(tmp_path: Path):
    guard, audit = parse_hooks(SETTINGS, tmp_path)
    assert (guard.event, guard.matcher, guard.command) == (PRE, "Bash|Write", "guard")
    assert guard.cwd == tmp_path and (audit.event, audit.timeout) == (POST, 5.0)
    assert guard.matches("shell_run") and guard.matches("workspace_write")
    assert guard.matches("Bash") and not guard.matches("workspace_read")
    assert not guard.matches("shell") and audit.matches("anything")
    literal = Hook(PRE, "(bad", "c", tmp_path)
    assert literal.matches("(bad") and not literal.matches("x")


def test_load_hooks_skips_unreadable_settings(tmp_path: Path):
    good, bad = tmp_path / "good" / ".claude", tmp_path / "bad" / ".claude"
    for root in (good, bad):
        root.mkdir(parents=True)
    good.joinpath("settings.json").write_text(json.dumps(SETTINGS))
    bad.joinpath("settings.json").write_text("{not json")
    hooks = load_hooks([Kit(bad, tmp_path), Kit(good, tmp_path)])
    assert [h.command for h in hooks] == ["guard", "audit"]
    assert hooks[0].cwd == tmp_path / "good"


def outcome(code: int, stdout: str = "", stderr: str = "") -> tuple[bool, str]:
    result = read_outcome(code, stdout, stderr)
    return result.blocked, result.reason


def test_read_outcome_understands_exit_codes_and_json_verdicts():
    assert outcome(2, stderr=" no way \n") == (True, "no way")
    assert outcome(2) == (True, texts.HOOK_BLOCKED_NO_REASON)
    assert outcome(0) == (False, "")
    assert outcome(0, "not json") == (False, "")
    assert outcome(0, json.dumps({"decision": "block", "reason": "r"})) == (True, "r")
    specific = {"permissionDecision": "deny", "permissionDecisionReason": "d"}
    assert outcome(0, json.dumps({"hookSpecificOutput": specific})) == (True, "d")
    add = {"hookSpecificOutput": {"additionalContext": "fyi"}}
    assert outcome(0, json.dumps(add)) == (False, "fyi")
    assert outcome(1, json.dumps({"decision": "block"}), "boom") == (False, "")


def py(code: str) -> str:
    return f"python3 -c {json.dumps(code)}"


BLOCK_RM = py(
    "import json,sys; d=json.load(sys.stdin);"
    " sys.exit(2 if 'rm' in d['tool_input']['command'] else 0)"
)
DENY = {"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": "nope"}}
DENY_JSON = py(f"print({json.dumps(json.dumps(DENY))})")
NOTE = py(
    "import json,sys; d=json.load(sys.stdin);"
    " print(d['tool_response']['output'].upper(), file=sys.stderr); sys.exit(2)"
)


async def test_runner_blocks_on_exit_two_and_appends_post_notes(tmp_path: Path):
    hooks = [
        Hook(PRE, "Bash", BLOCK_RM, tmp_path, timeout=10),
        Hook(POST, "shell_run", NOTE, tmp_path, timeout=10),
    ]
    runner = HookRunner(hooks, "a")
    assert await runner.before("shell_run", {"command": "ls"}) is None
    assert await runner.before("shell_run", {"command": "rm x"}) == texts.HOOK_BLOCKED_NO_REASON
    assert await runner.before("workspace_read", {"path": "rm"}) is None
    note = await runner.after("shell_run", {"command": "ls"}, True, "out")
    assert note == texts.TOOL_HOOK_NOTE.format(note="OUT")
    assert await runner.after("workspace_read", {}, True, "out") == ""


async def test_runner_reads_json_verdicts_and_hands_the_call_over(tmp_path: Path):
    seen = tmp_path / "seen.json"
    record = py(f"import sys; open({str(seen)!r},'w').write(sys.stdin.read())")
    hooks = [Hook(PRE, "*", record, tmp_path), Hook(PRE, "Write", DENY_JSON, tmp_path)]
    runner = HookRunner(hooks, "coach")
    assert await runner.before("workspace_write", {"path": "x"}) == "nope"
    payload = json.loads(seen.read_text())
    assert payload["hook_event_name"] == "PreToolUse" and payload["agent_id"] == "coach"
    assert payload["tool_name"] == "workspace_write" and payload["tool_alias"] == "Write"
    assert payload["tool_input"] == {"path": "x"} and payload["cwd"] == str(tmp_path)


async def test_runner_fails_open_on_crash_timeout_and_missing_command(tmp_path: Path):
    hooks = [
        Hook(PRE, "*", py("import sys; sys.exit(3)"), tmp_path),
        Hook(PRE, "*", py("import time; time.sleep(5)"), tmp_path, timeout=0.3),
        Hook(PRE, "*", "/no/such/binary", tmp_path),
    ]
    assert await HookRunner(hooks, "a").before("shell_run", {}) is None


async def test_registry_asks_the_hooks_around_every_call(tmp_path: Path):
    async def run(arguments):
        return f"ran {arguments['command']}"

    shell = Tool("shell_run", "shell", {"type": "object"}, run)
    hooks = [Hook(PRE, "Bash", BLOCK_RM, tmp_path), Hook(POST, "Bash", NOTE, tmp_path)]
    runner = HookRunner(hooks, "a")
    registry = ToolRegistry([shell], hooks=runner)
    blocked = await registry.execute("shell_run", {"command": "rm -r x"})
    assert not blocked.ok
    reason = texts.HOOK_BLOCKED_NO_REASON
    assert blocked.output == texts.TOOL_BLOCKED_BY_HOOK.format(name="shell_run", reason=reason)
    result = await registry.execute("shell_run", {"command": "ls"})
    assert result.ok and result.output == "ran ls" + texts.TOOL_HOOK_NOTE.format(note="RAN LS")
    assert registry.without("nothing").hooks is runner
    plain = await ToolRegistry([shell]).execute("shell_run", {"command": "rm"})
    assert plain.output == "ran rm"
