"""The process a script runs in. Every test here starts a real one: what comes back from
it, what it is started with, how long it is waited on, and that it is gone afterwards
whatever happened."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import signal
import socket
from asyncio.subprocess import DEVNULL, PIPE, Process
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from my_agent_crew import texts_script as t
from my_agent_crew.script import runner
from my_agent_crew.script.runner import Answer, Outcome, run_script
from tests.test_shell_network_sandbox import needs_sandbox

# One long operation after another: the step count sees little of it, the clocks all of it.
SPINS = "big = list(range(2000000))\nwhile True:\n    big.count(-1)"
# What Python and macOS put in every process themselves, whoever started it.
SET_BY_THE_SYSTEM = {"LC_CTYPE", "__CF_USER_TEXT_ENCODING"}

# Stand-ins for the child, started exactly as it is: what such a process is given, what it
# may do, and what is made of one that does not keep to the conversation.
ECHOES = """
import json, sys
print(json.dumps({"done": {"ok": True, "output": sys.stdin.readline()}}), flush=True)
"""
SEES = """
import json, os, sys
sys.stdin.readline()
try:
    import httpx
    packages = "found"
except ImportError:
    packages = "none"
seen = {
    "env": sorted(os.environ),
    "packages": packages,
    "flags": [sys.flags.isolated, sys.flags.no_site, sys.flags.dont_write_bytecode],
}
print(json.dumps({"done": {"ok": True, "output": json.dumps(seen)}}), flush=True)
"""
TRIES = """
import json, os, socket, sys
sys.stdin.readline()
did = {}
try:
    with open(PATH, "w") as file:
        file.write("x")
    did["write"] = "written"
except OSError as error:
    did["write"] = type(error).__name__
try:
    socket.create_connection(("127.0.0.1", PORT), timeout=3).close()
    did["connect"] = "connected"
except OSError as error:
    did["connect"] = type(error).__name__
try:
    pid = os.fork()
    if pid == 0:
        os._exit(0)
    os.waitpid(pid, 0)
    did["fork"] = "forked"
except OSError as error:
    did["fork"] = type(error).__name__
print(json.dumps({"done": {"ok": True, "output": json.dumps(did)}}), flush=True)
"""
STAYS = """
import json, os, sys, time
sys.stdin.readline()
print(json.dumps({"call": {"name": "here", "arguments": {"pid": os.getpid()}}}), flush=True)
sys.stdin.readline()
time.sleep(600)
"""
BABBLES = """
import time
print("not a line anyone agreed on", flush=True)
time.sleep(600)
"""
DIES = """
import sys
sys.stderr.write("first words " + "x" * 10000 + " last words")
sys.exit(3)
"""
SHOUTS = """
import json, sys
sys.stderr.write("x" * 1000000)
sys.stderr.flush()
print(json.dumps({"done": {"ok": True, "output": "heard"}}), flush=True)
"""
SAYS = """
import sys
sys.stdin.readline()
print(LINE, flush=True)
"""
# Falls silent, and a moment later is ended by the system for the CPU it used.
FADES = """
import os, signal, time
os.close(1)
time.sleep(0.3)
os.kill(os.getpid(), signal.SIGXCPU)
"""
# Its last words are three thousand of the letter `ơ`, two bytes each, and one more byte.
MOURNS = """
import sys
sys.stderr.buffer.write(b"\\xc6\\xa1" * 3000 + b"!")
sys.exit(3)
"""
# Asks for a tool and is gone a MOMENT later, the answer unread.
LEAVES = """
import json, sys, time
sys.stdin.readline()
print(json.dumps({"call": {"name": "read", "arguments": {}}}), flush=True)
time.sleep(MOMENT)
sys.exit(3)
"""
# The child itself, in a process already held to five seconds of CPU.
TIGHT = (
    "import resource, sys; resource.setrlimit(resource.RLIMIT_CPU, (5, 5));"
    " sys.path.append(sys.argv[1]); from my_agent_crew.script.child import main; main()"
)
# Tries to become another program, and says what stopped it.
BECOMES = """
import json, os, sys
sys.stdin.readline()
try:
    os.execv(PROGRAM, ARGUMENTS)
except OSError as error:
    print(json.dumps({"done": {"ok": True, "output": type(error).__name__}}), flush=True)
"""


async def nobody(name: str, arguments: dict[str, Any]) -> Answer:
    raise AssertionError(f"the script was not written to call {name}")


def gone(pid: int) -> bool:
    """Whether the process has ended and been collected: one only ended still answers."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def timed_out(seconds: str) -> Outcome:
    return Outcome(False, "", f"Script bị dừng: quá {seconds} giây mà chưa xong.")


@pytest.fixture(autouse=True)
def children(monkeypatch):
    """Every process started while a test runs. Whatever the test was about, none of them
    is left when it ends."""
    started: list[Process] = []
    start = asyncio.create_subprocess_exec

    async def starting(*args, **kwargs):
        proc = await start(*args, **kwargs)
        started.append(proc)
        return proc

    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", starting)
    yield started
    assert started, "the test was to start a process"
    assert all(proc.returncode is not None and gone(proc.pid) for proc in started)


# --- what comes back ---------------------------------------------------------------------


async def test_a_script_runs_in_another_process_and_its_calls_are_answered_in_this_one(children):
    asked = []

    async def double(name, arguments):
        asked.append((name, arguments))
        return Answer(True, json.dumps({"n": arguments["n"] * 2}))

    source = dedent(
        """\
        total = 0
        for n in [1, 2]:
            total += json.loads(tools.double(n=n))["n"]
        print("total", total)
        """
    )
    assert await run_script(source, double) == Outcome(True, "total 6\n")
    assert asked == [("double", {"n": 1}), ("double", {"n": 2})]
    (child,) = children
    assert child.pid != os.getpid()


async def test_what_goes_to_a_script_and_what_comes_back_keep_their_letters():
    asked = []

    async def shout(name, arguments):
        asked.append((name, arguments))
        return Answer(True, arguments["text"].upper())

    outcome = await run_script('print("nghe được:", tools.shout(text="chào bạn"))', shout)
    assert outcome == Outcome(True, "nghe được: CHÀO BẠN\n")
    assert asked == [("shout", {"text": "chào bạn"})]


async def test_a_tool_that_failed_is_the_scripts_to_catch():
    async def fail(name, arguments):
        return Answer(False, "Tool failed: nope")

    source = dedent(
        """\
        try:
            tools.fail()
        except Exception as e:
            print("caught:", e)
        print("after")
        """
    )
    assert await run_script(source, fail) == Outcome(True, "caught: Tool failed: nope\nafter\n")


async def test_a_failure_nobody_caught_ends_the_script_with_what_it_had_printed():
    async def fail(name, arguments):
        return Answer(False, "Tool failed: nope")

    outcome = await run_script('print("before")\ntools.fail()\nprint("after")', fail)
    assert outcome == Outcome(False, "before\n", "Lỗi ở dòng 2: Tool failed: nope")


async def test_a_call_the_script_may_not_make_ends_it_whatever_it_wrote():
    async def refuse(name, arguments):
        return Answer(False, f"no tool {name}", halt=True)

    source = dedent(
        """\
        try:
            tools.nope()
        except Exception as e:
            print("caught:", e)
        print("after")
        """
    )
    assert await run_script(source, refuse) == Outcome(False, "", "Dừng ở dòng 2: no tool nope")


async def test_an_answer_far_longer_than_a_pipe_holds_reaches_the_script_whole():
    async def read(name, arguments):
        return Answer(True, "x" * 200_000)

    source = "text = tools.read()\nprint(len(text))\nprint(text[:50000])"
    assert await run_script(source, read) == Outcome(True, "200000\n" + "x" * 50_000 + "\n")


async def test_half_a_character_pair_is_written_as_a_question_mark():
    """`json.loads` makes one from an escape, and it has no UTF-8: the answer still comes."""
    outcome = await run_script(r"""print(json.loads('"a\\ud800b"'))""", nobody)
    assert outcome == Outcome(True, "a?b\n")


async def test_half_a_character_pair_in_an_answer_reaches_the_script_as_a_question_mark():
    """A tool hands on what it read, and such a half has no UTF-8 to be sent in."""

    async def read(name, arguments):
        return Answer(True, "a\ud800b")

    outcome = await run_script('print(tools.read() == "a?b")', read)
    assert outcome == Outcome(True, "True\n")


async def test_the_process_is_told_the_script_and_its_seconds_of_cpu(monkeypatch):
    monkeypatch.setattr(runner, "BOOT", ECHOES)
    told = json.loads((await run_script('print("ơ")', nobody)).output)
    assert told == {"source": 'print("ơ")', "cpu_s": 20}
    assert run_script.__kwdefaults__ == {"cpu_s": 20, "idle_s": 60.0, "total_s": 300.0}


# --- the limits kept by the process and by the clock -------------------------------------


async def test_a_loop_without_end_is_stopped_by_its_steps_and_says_so_itself():
    outcome = await run_script("while True:\n    pass", nobody)
    stopped = t.SCRIPT_HALTED.format(line=2, reason=t.SCRIPT_OUT_OF_STEPS.format(most=2_000_000))
    assert outcome == Outcome(False, "", stopped)


async def test_what_the_steps_cannot_see_is_stopped_by_the_seconds_of_cpu(children):
    """One second, where a script has twenty: the limit asked for is the one that holds.
    Left at twenty, the silence would end it first and say something else."""
    outcome = await run_script(SPINS, nobody, cpu_s=1, idle_s=10)
    assert outcome == Outcome(False, "", t.SCRIPT_OUT_OF_CPU)
    # Ended by the system, at the limit the process set itself.
    assert children[0].returncode == -signal.SIGXCPU


async def test_a_script_is_stopped_by_the_memory_it_holds():
    source = dedent(
        """\
        kept = []
        for i in range(40):
            kept.append("x" * 8000000)
        print(len(kept))
        """
    )
    stopped = t.SCRIPT_HALTED.format(line=3, reason=t.SCRIPT_OUT_OF_ROOM)
    assert await run_script(source, nobody) == Outcome(False, "", stopped)


async def test_a_script_as_deep_in_its_calls_as_it_may_be_has_the_depth_of_pythons_it_needs():
    """Forty calls deep, the most there is, each of them twenty signs deep: nearly twice
    what Python lets a process nest unless it is told otherwise."""
    source = "def f(n):\n    return n if n == 0 else " + "-" * 20 + "f(n - 1)\nprint(f(39))"

    assert await run_script(source, nobody) == Outcome(True, "0\n")


async def test_a_process_already_held_to_less_cpu_than_a_script_is_given_keeps_to_that(
    monkeypatch,
):
    """Asking for more than the system lets it have would end the process before the
    script began."""
    monkeypatch.setattr(runner, "BOOT", TIGHT)

    assert await run_script('print("ran")', nobody) == Outcome(True, "ran\n")


async def test_a_script_that_says_nothing_for_too_long_is_killed(children):
    outcome = await run_script(SPINS, nobody, cpu_s=30, idle_s=0.2, total_s=30)
    assert outcome == timed_out("0.2")
    assert children[0].returncode == -signal.SIGKILL


async def test_the_time_a_tool_takes_is_not_the_scripts_silence():
    async def slow(name, arguments):
        await asyncio.sleep(0.7)
        return Answer(True, "there")

    outcome = await run_script("print(tools.slow())", slow, idle_s=0.5)
    assert outcome == Outcome(True, "there\n")


async def test_a_script_is_given_so_long_in_all_its_calls_included(children):
    async def never(name, arguments):
        await asyncio.Event().wait()

    outcome = await run_script("tools.wait()", never, idle_s=30, total_s=0.4)
    assert outcome == timed_out("0.4")
    assert children[0].returncode == -signal.SIGKILL


async def test_a_turn_cancelled_while_its_script_waits_leaves_no_process(children):
    reached = asyncio.Event()

    async def never(name, arguments):
        reached.set()
        await asyncio.Event().wait()

    running = asyncio.create_task(run_script("tools.wait()", never))
    await asyncio.wait_for(reached.wait(), 30)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    (child,) = children
    assert child.returncode == -signal.SIGKILL and gone(child.pid)


async def test_the_process_killed_is_the_one_the_script_ran_in(monkeypatch, children):
    """The sandbox does not stand between: it becomes the script's process, so killing
    what was started kills the script and leaves nothing running behind it."""
    monkeypatch.setattr(runner, "BOOT", STAYS)
    pids = []

    async def here(name, arguments):
        pids.append(arguments["pid"])
        return Answer(True, "")

    assert await run_script("", here, idle_s=0.5) == timed_out("0.5")
    (child,) = children
    assert pids == [child.pid] and gone(child.pid)


# --- a process that does not keep to the conversation -------------------------------------


async def test_a_process_that_ends_without_an_answer_is_told_as_that_and_logged(
    monkeypatch, caplog
):
    monkeypatch.setattr(runner, "BOOT", DIES)
    with caplog.at_level(logging.WARNING, logger="my_agent_crew.script.runner"):
        outcome = await run_script("print(1)", nobody)
    assert outcome == Outcome(False, "", t.SCRIPT_DIED)
    (record,) = [one for one in caplog.records if one.name == "my_agent_crew.script.runner"]
    said = record.getMessage()
    assert "(exit 3)" in said and said.endswith(" last words")
    # Only the end of what it wrote is kept: a process may write without end.
    assert "first words" not in said and len(said) < 4100


async def test_a_process_that_stops_making_sense_is_not_waited_on_for_long(
    monkeypatch, caplog, children
):
    monkeypatch.setattr(runner, "BOOT", BABBLES)
    monkeypatch.setattr(runner, "EXIT_S", 0.2)
    with caplog.at_level(logging.WARNING, logger="my_agent_crew.script.runner"):
        outcome = await run_script("print(1)", nobody)
    assert outcome == Outcome(False, "", t.SCRIPT_DIED)
    # Still running when it was given up on, and killed for that.
    assert "(exit None)" in caplog.text
    assert children[0].returncode == -signal.SIGKILL


async def test_a_process_ended_for_its_cpu_a_moment_after_it_fell_silent_is_told_as_that(
    monkeypatch,
):
    """Its silence is read before the system has said how it ended, so that is waited for."""
    monkeypatch.setattr(runner, "BOOT", FADES)

    assert await run_script("", nobody) == Outcome(False, "", t.SCRIPT_OUT_OF_CPU)


OUT_OF_SHAPE = [
    "{}",
    "[1]",
    "3",
    '"done"',
    '{"call": {}}',
    '{"call": []}',
    '{"call": {"name": "read"}}',
    '{"done": 3}',
    '{"done": {"ok": true}}',
    '{"done": {"ok": true, "output": "", "more": 1}}',
]


@pytest.mark.parametrize("line", OUT_OF_SHAPE)
async def test_a_line_that_is_json_and_nothing_agreed_on_is_a_process_that_died(monkeypatch, line):
    monkeypatch.setattr(runner, "BOOT", SAYS.replace("LINE", repr(line)))

    assert await run_script("", nobody) == Outcome(False, "", t.SCRIPT_DIED)


async def test_last_words_cut_in_the_middle_of_a_letter_are_logged_all_the_same(
    monkeypatch, caplog
):
    """Only the end is kept, and the cut falls where it falls: half a letter at the front
    of it is no reason to fail the turn."""
    monkeypatch.setattr(runner, "BOOT", MOURNS)
    with caplog.at_level(logging.WARNING, logger="my_agent_crew.script.runner"):
        outcome = await run_script("print(1)", nobody)
    assert outcome == Outcome(False, "", t.SCRIPT_DIED)
    (record,) = [one for one in caplog.records if one.name == "my_agent_crew.script.runner"]
    assert record.getMessage().endswith("(exit 3): �" + "ơ" * 1999 + "!")


async def test_a_process_gone_while_a_long_answer_was_on_its_way_is_told_as_one_that_died(
    monkeypatch,
):
    """Far longer than a pipe holds: the sending waits for a reader, and is still waiting
    when the process goes."""
    monkeypatch.setattr(runner, "BOOT", LEAVES.replace("MOMENT", "0.3"))

    async def read(name, arguments):
        return Answer(True, "x" * 2_000_000)

    assert await run_script("", read) == Outcome(False, "", t.SCRIPT_DIED)


async def test_a_process_gone_before_its_tool_had_answered_is_told_as_one_that_died(
    monkeypatch, children
):
    """The answer is short, and by the time it is there nobody is left to send it to."""
    monkeypatch.setattr(runner, "BOOT", LEAVES.replace("MOMENT", "0"))

    async def read(name, arguments):
        await children[0].wait()
        await asyncio.sleep(0.2)
        return Answer(True, "late")

    assert await run_script("", read) == Outcome(False, "", t.SCRIPT_DIED)


async def test_a_process_whose_parent_is_gone_ends_there_and_does_not_run_on():
    """Nobody is left to answer. A script that went on as if its call had failed would
    work for no one, up to all the limits it has."""
    proc = await asyncio.create_subprocess_exec(
        *runner.command(), stdin=PIPE, stdout=PIPE, stderr=DEVNULL, env={}
    )
    assert proc.stdin is not None and proc.stdout is not None
    source = 'try:\n    tools.wait()\nexcept Exception:\n    pass\nprint("went on")'
    proc.stdin.write(json.dumps({"source": source, "cpu_s": 20}).encode() + b"\n")
    asked = json.loads(await asyncio.wait_for(proc.stdout.readline(), 30))

    proc.stdin.close()
    rest = await asyncio.wait_for(proc.stdout.read(), 30)

    assert asked == {"call": {"name": "wait", "arguments": {}}}
    assert (rest, await proc.wait()) == (b"", 1)


async def test_a_line_longer_than_any_script_can_write_is_not_read(monkeypatch):
    monkeypatch.setattr(runner, "LINE_LIMIT", 1000)
    assert await run_script('print("x" * 500)', nobody) == Outcome(True, "x" * 500 + "\n")
    assert await run_script('print("x" * 2000)', nobody) == Outcome(False, "", t.SCRIPT_DIED)


async def test_a_process_that_writes_much_to_its_errors_is_not_stalled_by_them(monkeypatch):
    monkeypatch.setattr(runner, "BOOT", SHOUTS)
    assert await run_script("", nobody, idle_s=10) == Outcome(True, "heard")


# --- what the process is started with -----------------------------------------------------


async def test_the_process_is_handed_nothing_of_the_servers(monkeypatch):
    """No variable of the server's environment, where its keys are, and none of the
    packages it runs on: only Python and the interpreter's own modules."""
    monkeypatch.setenv("MY_AGENT_SECRET_PROBE", "s3cret")
    monkeypatch.setattr(runner, "BOOT", SEES)
    seen = json.loads((await run_script("", nobody)).output)
    # The server's own process has both, which is what makes their absence the runner's doing.
    assert "MY_AGENT_SECRET_PROBE" in os.environ and importlib.util.find_spec("httpx")
    assert set(seen["env"]) & set(os.environ) - SET_BY_THE_SYSTEM == set()
    assert seen["packages"] == "none"
    assert seen["flags"] == [1, 1, 1]


async def test_nothing_beside_the_package_stands_in_for_a_module_of_pythons(monkeypatch, tmp_path):
    (tmp_path / "my_agent_crew").symlink_to(Path(runner.ROOT) / "my_agent_crew")
    (tmp_path / "json.py").write_text('raise SystemExit("not the json a script was promised")\n')
    monkeypatch.setattr(runner, "ROOT", str(tmp_path))
    assert await run_script("print(json.dumps([1]))", nobody) == Outcome(True, "[1]\n")


@needs_sandbox
async def test_the_sandbox_denies_the_network_every_file_and_a_second_process(
    monkeypatch, tmp_path
):
    """Whatever the interpreter let through would still write nothing, reach nobody and
    start nothing. The temp directory is the place to try a write: `shell_run`'s sandbox
    leaves it open. The same attempts made outside the sandbox all succeed, which is what
    makes the refusals its doing."""
    listener = socket.create_server(("127.0.0.1", 0))
    listener.settimeout(0.3)
    port = listener.getsockname()[1]

    async def attempt(target: Path) -> dict[str, str]:
        probe = TRIES.replace("PATH", repr(str(target))).replace("PORT", str(port))
        monkeypatch.setattr(runner, "BOOT", probe)
        return json.loads((await run_script("", nobody)).output)

    with listener:
        inside = await attempt(tmp_path / "inside.txt")
        with pytest.raises(TimeoutError):
            listener.accept()
        monkeypatch.setattr(runner, "SANDBOX_EXEC", Path("/nowhere/sandbox-exec"))
        outside = await attempt(tmp_path / "outside.txt")
        listener.accept()[0].close()
    refused = "PermissionError"
    assert inside == {"write": refused, "connect": refused, "fork": refused}
    assert outside == {"write": "written", "connect": "connected", "fork": "forked"}
    assert not (tmp_path / "inside.txt").exists() and (tmp_path / "outside.txt").exists()


@needs_sandbox
@pytest.mark.parametrize(
    "helper",
    # Both end harmlessly where nothing stops them: no such file, just the help.
    [["/usr/bin/open", "/no/such/file"], ["/bin/launchctl", "help"]],
)
async def test_the_sandbox_keeps_the_process_from_becoming_a_helper_outside_it(monkeypatch, helper):
    """`open` and `launchctl` get something unsandboxed to act for whoever runs them, and
    becoming one of them takes no second process. Outside the sandbox the process does
    become the helper, and so never answers."""
    probe = BECOMES.replace("PROGRAM", repr(helper[0])).replace("ARGUMENTS", repr(helper))
    monkeypatch.setattr(runner, "BOOT", probe)

    inside = await run_script("", nobody)
    monkeypatch.setattr(runner, "SANDBOX_EXEC", Path("/nowhere/sandbox-exec"))
    outside = await run_script("", nobody)

    assert inside == Outcome(True, "PermissionError")
    assert outside == Outcome(False, "", t.SCRIPT_DIED)
