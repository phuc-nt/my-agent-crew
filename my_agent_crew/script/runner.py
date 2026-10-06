"""Runs one script in a process of its own and answers the tool calls it makes.

The script is the model's, so it runs where a mistake in the interpreter would still have
nothing to reach: a child process with an empty environment and no site packages, and on
macOS inside a sandbox with the network, every file write and forking denied. (Linux has
no such sandbox; there the interpreter is the wall.) The child keeps its own CPU limit and
counts its own memory; the clock is kept here.

One JSON line each way. The child asks for a tool call, the caller's `call` carries it out
in this process, and the answer goes back. Whatever happens, the child is gone when
`run_script` returns: it is killed if it is still there.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import signal
import sys
from asyncio.subprocess import PIPE, Process
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from my_agent_crew import texts_script as t
from my_agent_crew.tools.shell_sandbox import SANDBOX_EXEC, helper_rules

logger = logging.getLogger(__name__)

# CPU seconds for the whole script, the longest it may go without a word, and the longest
# it may take in all, tool calls included.
CPU_S = 20
IDLE_S = 60.0
TOTAL_S = 300.0
# The longest line the child may write: what it printed and one error, with room to spare.
LINE_LIMIT = 8 * 1024 * 1024
STDERR_KEPT = 4000
EXIT_S = 5.0
ROOT = str(Path(__file__).resolve().parents[2])
# Appended, so nothing beside the package can stand in for a module of Python's own.
BOOT = (
    "import sys; sys.path.append(sys.argv[1]); from my_agent_crew.script.child import main; main()"
)
# A profile of the script's own and not the shell's with more denied: that one lets a
# command write to the temp directories, and a rule is not taken back by saying it again.
SEALED = (
    "(version 1)(allow default)(deny network*)(deny file-write*)(deny process-fork)"
    + helper_rules()
)


@dataclass(frozen=True)
class Answer:
    """What one tool call of a script came to. `halt` ends the script there, uncatchable:
    it is for a call the script may not make at all, not for one that failed."""

    ok: bool
    output: str
    halt: bool = False


@dataclass(frozen=True)
class Outcome:
    ok: bool
    output: str
    error: str | None = None


CallTool = Callable[[str, dict[str, Any]], Awaitable[Answer]]


def command() -> list[str]:
    """`-I -S`: no environment variables read, no user or site packages. `-B`: nothing
    written beside the source."""
    python = [sys.executable, "-I", "-S", "-B", "-c", BOOT, ROOT]
    if not SANDBOX_EXEC.is_file():
        return python
    return [str(SANDBOX_EXEC), "-p", SEALED, *python]


async def _send(proc: Process, message: dict[str, Any]) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(message, ensure_ascii=False).encode("utf-8", "replace") + b"\n")
    with contextlib.suppress(OSError):  # a child that died is found out on the next read
        await proc.stdin.drain()


async def _tail(stream: asyncio.StreamReader, kept: bytearray) -> None:
    """Reads what the child wrote to stderr for as long as it runs, keeping the end of it:
    left unread, a full pipe would stall the child."""
    while chunk := await stream.read(65536):
        kept.extend(chunk)
        del kept[:-STDERR_KEPT]


async def _converse(
    proc: Process, source: str, call: CallTool, cpu_s: int, idle_s: float
) -> Outcome | None:
    """Speaks with the child until it is done. None when it stopped making sense, which
    is what a dead child's silence reads as."""
    assert proc.stdout is not None
    await _send(proc, {"source": source, "cpu_s": cpu_s})
    while True:
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), idle_s)
        except TimeoutError:
            return Outcome(False, "", t.SCRIPT_TIMED_OUT.format(seconds=idle_s))
        except ValueError:  # a line longer than `LINE_LIMIT`
            return None
        try:
            message = json.loads(line)
            if "done" in message:
                return Outcome(**message["done"])
            name, arguments = message["call"]["name"], message["call"]["arguments"]
        except (ValueError, KeyError, TypeError):
            return None
        await _send(proc, asdict(await call(name, arguments)))


async def _died(proc: Process, tail: asyncio.Task[None], errors: bytearray) -> Outcome:
    await asyncio.wait({tail, asyncio.ensure_future(proc.wait())}, timeout=EXIT_S)
    if proc.returncode == -signal.SIGXCPU:
        return Outcome(False, "", t.SCRIPT_OUT_OF_CPU)
    said = errors.decode("utf-8", "replace")
    logger.warning("a script's process ended on its own (exit %s): %s", proc.returncode, said)
    return Outcome(False, "", t.SCRIPT_DIED)


async def run_script(
    source: str,
    call: CallTool,
    *,
    cpu_s: int = CPU_S,
    idle_s: float = IDLE_S,
    total_s: float = TOTAL_S,
) -> Outcome:
    proc = await asyncio.create_subprocess_exec(
        *command(), stdin=PIPE, stdout=PIPE, stderr=PIPE, env={}, limit=LINE_LIMIT
    )
    assert proc.stderr is not None
    errors = bytearray()
    tail = asyncio.create_task(_tail(proc.stderr, errors))
    try:
        try:
            async with asyncio.timeout(total_s):
                outcome = await _converse(proc, source, call, cpu_s, idle_s)
        except TimeoutError:
            return Outcome(False, "", t.SCRIPT_TIMED_OUT.format(seconds=total_s))
        return outcome if outcome is not None else await _died(proc, tail, errors)
    finally:
        # Also where a cancelled turn leaves: the child never outlives its script.
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
        await proc.wait()
        tail.cancel()
