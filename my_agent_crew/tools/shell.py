"""`shell_run`: execute a command in the agent's workspace. Every call goes through
approval unless the conversation is autonomous — the model sees stdout and stderr,
capped like any other tool output. The approval is the guard; the one sandbox is the
network switch below.

An autonomous conversation drops that guard for every command, which is too much for the
destructive shapes, so `ask_reason` names the ones that ask anyway. It is a coarse
substring match, deliberately: a soft second guard, not a security boundary.

An agent whose profile sets `shell_network: false` runs every command under macOS
`sandbox-exec` with all outbound connections denied — IP, localhost, and the Unix socket
DNS goes through, since a lookup of a made-up host name carries data out as surely as a
request does. That is a real boundary, unlike the patterns: it holds for `$(…)` and for a
script the model wrote a moment ago. Where `sandbox-exec` is missing the command is
refused rather than run unconfined. Scheduled `command` jobs call `run_shell` directly
and keep the network; a person wrote those, and some need it."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from my_agent_crew import texts
from my_agent_crew.tools.registry import Tool, ToolError

SHELL_TOOL_NAME = "shell_run"
DEFAULT_TIMEOUT_S = 120
MAX_TIMEOUT_S = 900
PASSTHROUGH_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TERM", "TMPDIR", "USER", "SHELL")
SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")
# Everything is allowed except opening a connection. Files, subprocesses and inbound
# stay open, so the scripts an offline agent exists to run keep working.
NO_NETWORK_PROFILE = "(version 1)(allow default)(deny network-outbound)"


def shell_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in PASSTHROUGH_ENV}
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env.setdefault("LANG", "en_US.UTF-8")
    return env


async def run_shell(
    command: str, cwd: Path, timeout_s: float, *, network: bool = True
) -> tuple[int | None, str]:
    """(exit code, combined output). A timeout kills the process and returns None.

    `network=False` runs the command inside the no-network sandbox; the caller checks
    that `SANDBOX_EXEC` exists first, because a missing one must refuse, not fall open."""
    argv = ["/bin/sh", "-c", command]
    if not network:
        argv = [str(SANDBOX_EXEC), "-p", NO_NETWORK_PROFILE, *argv]
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        env=shell_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL,
    )
    try:
        raw, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return None, ""
    return proc.returncode, raw.decode("utf-8", errors="replace")


def ask_reason(command: str, patterns: Sequence[str]) -> str | None:
    """The first pattern the command matches, or None when it matches none."""
    lowered = command.lower()
    for pattern in patterns:
        if pattern.lower() in lowered:
            return pattern
    return None


def build_shell_tool(cwd: Path, *, network: bool = True) -> Tool:
    async def run(args: dict[str, Any]) -> str:
        command = str(args.get("command", "")).strip()
        if not command:
            raise ToolError("lệnh trống")
        timeout_s = min(float(args.get("timeout_s") or DEFAULT_TIMEOUT_S), MAX_TIMEOUT_S)
        if not cwd.is_dir():
            raise ToolError(texts.SHELL_NO_CWD.format(path=cwd))
        if not network and not SANDBOX_EXEC.is_file():
            raise ToolError(texts.SHELL_NO_SANDBOX)
        code, output = await run_shell(command, cwd, timeout_s, network=network)
        if code is None:
            raise ToolError(texts.SHELL_TIMEOUT.format(seconds=int(timeout_s)))
        if code != 0:
            raise ToolError(texts.SHELL_FAILED.format(code=code, output=output.strip()[-4000:]))
        return output if output.strip() else texts.SHELL_NO_OUTPUT

    return Tool(
        name=SHELL_TOOL_NAME,
        description=(
            "Chạy một lệnh shell trong thư mục làm việc của agent và trả về stdout+stderr."
            " Dùng đường dẫn tuyệt đối cho tệp ngoài thư mục làm việc. Mỗi lệnh cần người"
            " dùng duyệt trừ khi cuộc trò chuyện ở chế độ tự động."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Lệnh shell (zsh/sh)."},
                "timeout_s": {
                    "type": "integer",
                    "description": f"Giây tối đa (mặc định {DEFAULT_TIMEOUT_S}).",
                },
            },
            "required": ["command"],
        },
        run=run,
        requires_approval=True,
    )
