"""Running kit hooks around a tool call. The hook gets the call as JSON on stdin, the way
Claude Code hands it over, and answers with its exit code: 2 blocks the call (before) or
adds its stderr to the result (after); 0 with a JSON `decision: block` on stdout does the
same. Anything else — another code, a crash, a timeout — is logged and lets the call
through: a guard that fails must not take the agent's hands away."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from my_agent_crew import texts
from my_agent_crew.agents.kit_hooks import POST, PRE, TOOL_ALIASES, Hook

logger = logging.getLogger(__name__)
BLOCK_EXIT = 2
MAX_REASON_CHARS = 2000


@dataclass(frozen=True)
class HookOutcome:
    blocked: bool = False
    reason: str = ""


def read_outcome(code: int | None, stdout: str, stderr: str) -> HookOutcome:
    """Exit 2 with stderr, or a JSON verdict on stdout (`decision`, or Claude Code's
    `hookSpecificOutput.permissionDecision`)."""
    if code == BLOCK_EXIT:
        return HookOutcome(True, stderr.strip()[:MAX_REASON_CHARS] or texts.HOOK_BLOCKED_NO_REASON)
    if code != 0 or not stdout.strip():
        return HookOutcome()
    try:
        data = json.loads(stdout)
    except ValueError:
        return HookOutcome()
    if not isinstance(data, dict):
        return HookOutcome()
    specific = data.get("hookSpecificOutput") or {}
    if data.get("decision") == "block":
        return HookOutcome(True, str(data.get("reason") or texts.HOOK_BLOCKED_NO_REASON))
    if specific.get("permissionDecision") == "deny":
        reason = specific.get("permissionDecisionReason") or texts.HOOK_BLOCKED_NO_REASON
        return HookOutcome(True, str(reason))
    if specific.get("additionalContext"):
        return HookOutcome(False, str(specific["additionalContext"]))
    return HookOutcome()


async def run_hook(hook: Hook, payload: dict[str, Any]) -> HookOutcome:
    env = {
        **os.environ,
        "CLAUDE_PROJECT_DIR": str(hook.cwd),
        "MY_AGENT_PROJECT_DIR": str(hook.cwd),
    }
    try:
        proc = await asyncio.create_subprocess_shell(
            hook.command,
            cwd=hook.cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        logger.warning("hook %r could not start: %s", hook.command, exc)
        return HookOutcome()
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(json.dumps(payload).encode("utf-8")), hook.timeout
        )
    except TimeoutError:
        proc.kill()
        logger.warning("hook %r timed out after %.0fs", hook.command, hook.timeout)
        return HookOutcome()
    stdout, stderr = out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
    outcome = read_outcome(proc.returncode, stdout, stderr)
    if proc.returncode not in (0, BLOCK_EXIT):
        logger.warning("hook %r exited %s: %s", hook.command, proc.returncode, err.strip()[:300])
    return outcome


class HookRunner:
    """The hooks of one agent, asked before and after each tool call."""

    def __init__(self, hooks: Sequence[Hook], agent_id: str):
        self.hooks = tuple(hooks)
        self.agent_id = agent_id

    def _payload(self, event: str, name: str, arguments: dict[str, Any], cwd: str) -> dict:
        return {
            "hook_event_name": event,
            "tool_name": name,
            "tool_alias": TOOL_ALIASES.get(name, name),
            "tool_input": arguments,
            "agent_id": self.agent_id,
            "cwd": cwd,
        }

    async def before(self, name: str, arguments: dict[str, Any]) -> str | None:
        """The reason the call is refused, or None to let it run. The first hook that
        blocks decides; the rest are not asked."""
        for hook in self.hooks:
            if hook.event != PRE or not hook.matches(name):
                continue
            outcome = await run_hook(hook, self._payload(PRE, name, arguments, str(hook.cwd)))
            if outcome.blocked:
                return outcome.reason
        return None

    async def after(self, name: str, arguments: dict[str, Any], ok: bool, output: str) -> str:
        """Notes the after-hooks want the model to read, joined; empty when none spoke."""
        notes: list[str] = []
        for hook in self.hooks:
            if hook.event != POST or not hook.matches(name):
                continue
            payload = self._payload(POST, name, arguments, str(hook.cwd))
            payload["tool_response"] = {"ok": ok, "output": output}
            outcome = await run_hook(hook, payload)
            if outcome.reason:
                notes.append(outcome.reason)
        return "".join(texts.TOOL_HOOK_NOTE.format(note=note) for note in notes)
