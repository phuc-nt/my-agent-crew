"""The interpreter: one script, the names it holds, what it printed and what it has used.

`run` is all a caller needs. It never raises for anything the script did: a refusal, a
failure and a limit reached all come back as the line that says so, after whatever the
script had printed by then.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from typing import Any

from my_agent_crew import texts_script as t
from my_agent_crew.script.check import parse
from my_agent_crew.script.expressions import EXPRESSIONS
from my_agent_crew.script.limits import (
    MAX_DEPTH,
    MAX_ERROR_CHARS,
    MAX_OUTPUT_CHARS,
    Budget,
    Halt,
    ScriptError,
)
from my_agent_crew.script.operators import describe, render
from my_agent_crew.script.statements import CAUGHT, STATEMENTS
from my_agent_crew.script.values import Builtin, Env, Function, Return, kind_name

# Hands back a tool's output; raises `ScriptError` when the tool failed, and `Halt` when
# the script may not make that call at all.
CallTool = Callable[[str, dict[str, Any]], str]
# What ends a script unless it is caught: each is told the line it came from.
STOPS = (Halt, *CAUGHT)


def _at(error: Exception, line: int) -> None:
    """Notes where an error came from: the innermost line it passes through, and only that
    one, so a failure after a function returned is not laid at the function's last line."""
    if getattr(error, "script_line", None) is None:
        error.script_line = line  # type: ignore[attr-defined]


def _unknown(machine: Machine, node: ast.AST, env: Env) -> Any:
    raise Halt(t.SCRIPT_UNSUPPORTED.format(what=type(node).__name__))


def _bind(called: Function, args: list[Any], kwargs: dict[str, Any], scope: Env) -> None:
    params, names = called.params, scope.names
    if len(args) > len(params):
        raise ScriptError(t.SCRIPT_BAD_CALL.format(name=called.name))
    names.update(zip(params, args, strict=False))
    for name, value in kwargs.items():
        if name not in params or name in names:
            raise ScriptError(t.SCRIPT_BAD_CALL.format(name=called.name))
        names[name] = value
    optional = len(params) - len(called.defaults)
    for index, name in enumerate(params):
        if name not in names:
            if index < optional:
                raise ScriptError(t.SCRIPT_BAD_CALL.format(name=called.name))
            names[name] = called.defaults[index - optional]


class Machine:
    def __init__(self, call_tool: CallTool):
        self.call_tool = call_tool
        self.budget = Budget()
        self.globals = Env()
        self.out: list[str] = []
        self.printed = 0
        self.line = 1
        # The error an `except` is dealing with, for a bare `raise` to raise again.
        self.handling: Exception | None = None

    def eval(self, node: ast.expr, env: Env) -> Any:
        self.line = node.lineno
        try:
            self.budget.step()
            return EXPRESSIONS.get(type(node), _unknown)(self, node, env)
        except STOPS as error:
            _at(error, node.lineno)
            raise

    def run_block(self, body: list[ast.stmt], env: Env) -> None:
        for statement in body:
            self.line = statement.lineno
            try:
                self.budget.step()
                STATEMENTS.get(type(statement), _unknown)(self, statement, env)
            except STOPS as error:
                _at(error, statement.lineno)
                raise

    def call(self, called: Any, args: list[Any], kwargs: dict[str, Any]) -> Any:
        if type(called) is Builtin:
            return called.call(self, args, kwargs)
        if type(called) is not Function:
            raise ScriptError(t.SCRIPT_NOT_CALLABLE.format(kind=kind_name(called)))
        scope = Env(called.env)
        _bind(called, args, kwargs, scope)
        if self.budget.depth >= MAX_DEPTH:
            raise Halt(t.SCRIPT_TOO_DEEP)
        self.budget.depth += 1
        try:
            if isinstance(called.body, list):
                self.run_block(called.body, scope)
                return None
            return self.eval(called.body, scope)
        except Return as done:
            return done.value
        finally:
            self.budget.depth -= 1

    def write(self, text: str) -> None:
        """Keeps what the script printed, up to the most it may: the rest is not kept, and
        the script ends there, so a loop that prints without end is not left running."""
        room = MAX_OUTPUT_CHARS - self.printed
        self.out.append(text[:room])
        self.printed += min(len(text), room)
        if len(text) > room:
            raise Halt(t.SCRIPT_TOO_MUCH_OUTPUT.format(most=MAX_OUTPUT_CHARS))

    def run(self, tree: ast.Module) -> None:
        """The whole script. A bare expression on its last line is shown, as a prompt
        would show it: a model that forgot `print` still gets what it asked for."""
        *body, last = tree.body or [ast.Pass(lineno=1)]
        if not isinstance(last, ast.Expr):
            self.run_block([*body, last], self.globals)
            return
        self.run_block(body, self.globals)
        value = self.eval(last.value, self.globals)
        self.line = last.lineno
        if value is not None:
            self.write(render(self.budget, value) + "\n")


def _line(error: Exception, machine: Machine) -> int:
    return getattr(error, "script_line", machine.line)


def run(source: str, call_tool: CallTool) -> dict[str, Any]:
    """Runs a script to its end: `ok`, the `output` it printed, and the `error` line when
    it was refused, failed or was stopped."""
    try:
        tree = parse(source)
    except ScriptError as refused:
        return {"ok": False, "output": "", "error": str(refused)}
    machine = Machine(call_tool)
    error: str | None = None
    try:
        machine.run(tree)
    except Halt as halt:
        error = t.SCRIPT_HALTED.format(line=_line(halt, machine), reason=halt)
    except CAUGHT as failed:
        error = t.SCRIPT_ERROR.format(line=_line(failed, machine), error=describe(failed))
    except RecursionError:
        error = t.SCRIPT_HALTED.format(line=machine.line, reason=t.SCRIPT_TOO_DEEP)
    except MemoryError:
        error = t.SCRIPT_HALTED.format(line=machine.line, reason=t.SCRIPT_OUT_OF_ROOM)
    said = None if error is None else error[:MAX_ERROR_CHARS]
    return {"ok": error is None, "output": "".join(machine.out), "error": said}
