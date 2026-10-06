"""The process a script runs in.

It is started with nothing: no environment, no site packages, and on macOS a sandbox with
no network, no file writes and no forking. It reads the script as one JSON line, runs it,
and writes one JSON line back for each tool call it makes and one for how it ended. A tool
is never run here: the call is asked of the parent, which answers with what it gave.

The process sets its own CPU limit before the script starts, and counts the memory it
allocates so `limits.Budget` has something to measure.
"""

from __future__ import annotations

import json
import resource
import sys
import tracemalloc
from typing import Any

from my_agent_crew.script.limits import Halt, ScriptError
from my_agent_crew.script.machine import run

# Python's own depth, above what `limits.MAX_DEPTH` lets a script reach: a function call
# of the script is a dozen of the interpreter's.
RECURSION_LIMIT = 4000


def _read() -> dict[str, Any]:
    line = sys.stdin.buffer.readline()
    if not line:  # the parent is gone, and nobody is left to answer
        raise SystemExit(1)
    return json.loads(line)


def _write(message: dict[str, Any]) -> None:
    # A text can hold half a character pair (`json.loads` makes one from an escape), which
    # has no UTF-8: it is written as a `?` instead of taking the answer down.
    line = json.dumps(message, ensure_ascii=False).encode("utf-8", "replace")
    sys.stdout.buffer.write(line + b"\n")
    sys.stdout.buffer.flush()


def _call_tool(name: str, arguments: dict[str, Any]) -> str:
    _write({"call": {"name": name, "arguments": arguments}})
    answer = _read()
    if answer.get("halt"):
        raise Halt(answer["output"])
    if not answer["ok"]:
        raise ScriptError(answer["output"])
    return answer["output"]


def _limit_cpu(seconds: int) -> None:
    """Past this the process is killed by the system, which is what stops a single
    operation the step count cannot see into: a sort, a search through a long list."""
    _, hard = resource.getrlimit(resource.RLIMIT_CPU)
    soft = seconds if hard == resource.RLIM_INFINITY else min(seconds, hard)
    resource.setrlimit(resource.RLIMIT_CPU, (soft, hard))


def main() -> None:
    sys.setrecursionlimit(RECURSION_LIMIT)
    request = _read()
    _limit_cpu(request["cpu_s"])
    tracemalloc.start()
    _write({"done": run(request["source"], _call_tool)})
