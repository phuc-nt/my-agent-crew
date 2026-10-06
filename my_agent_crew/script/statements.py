"""How each kind of statement a script may write is carried out.

One function per node, `(machine, node, scope)`, in the table at the end, as with
`expressions.py`. A statement with no function here is not part of the language.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_script as t
from my_agent_crew.script.binding import assign, iterate
from my_agent_crew.script.expressions import function
from my_agent_crew.script.limits import ScriptError
from my_agent_crew.script.operators import INPLACE, binary, describe, text_of
from my_agent_crew.script.values import (
    KNOWN_ERRORS,
    RUNTIME_ERRORS,
    Break,
    Continue,
    Env,
    Return,
    Signal,
)

if TYPE_CHECKING:
    from my_agent_crew.script.machine import Machine

# What a script's `try` may catch. A limit reached and a refused call are neither.
CAUGHT = (ScriptError, *RUNTIME_ERRORS)
EVERYTHING = ("Exception", "BaseException")


def _assign(machine: Machine, node: ast.Assign, env: Env) -> None:
    value = machine.eval(node.value, env)
    for target in node.targets:
        assign(machine, target, value, env)


def _annotated(machine: Machine, node: ast.AnnAssign, env: Env) -> None:
    if node.value is not None:
        assign(machine, node.target, machine.eval(node.value, env), env)


def _augmented(machine: Machine, node: ast.AugAssign, env: Env) -> None:
    target = node.target
    if isinstance(target, ast.Name):
        # As in Python, `+=` inside a function never reaches a name of an outer scope.
        if target.id not in env.names and env.parent is not None:
            raise ScriptError(t.SCRIPT_NO_NAME.format(name=target.id))
        held, key = env.names, target.id
        current = machine.eval(target, env)
    elif isinstance(target, ast.Subscript) and not isinstance(target.slice, ast.Slice):
        held, key = machine.eval(target.value, env), machine.eval(target.slice, env)
        if type(held) not in (list, dict):
            raise ScriptError(t.SCRIPT_BAD_TARGET)
        current = held[key]
    else:
        raise ScriptError(t.SCRIPT_BAD_TARGET)
    held[key] = binary(machine.budget, node.op, current, machine.eval(node.value, env), INPLACE)


def _if(machine: Machine, node: ast.If, env: Env) -> None:
    machine.run_block(node.body if machine.eval(node.test, env) else node.orelse, env)


def _while(machine: Machine, node: ast.While, env: Env) -> None:
    while machine.eval(node.test, env):
        try:
            machine.run_block(node.body, env)
        except Break:
            return
        except Continue:
            continue
    machine.run_block(node.orelse, env)


def _for(machine: Machine, node: ast.For, env: Env) -> None:
    for item in iterate(machine, machine.eval(node.iter, env)):
        assign(machine, node.target, item, env)
        try:
            machine.run_block(node.body, env)
        except Break:
            return
        except Continue:
            continue
    machine.run_block(node.orelse, env)


def _def(machine: Machine, node: ast.FunctionDef, env: Env) -> None:
    env.names[node.name] = function(machine, node, env)


def _return(machine: Machine, node: ast.Return, env: Env) -> None:
    raise Return(None if node.value is None else machine.eval(node.value, env))


def _leave(signal: type[Signal]) -> Callable[..., None]:
    def leave(machine: Machine, node: ast.stmt, env: Env) -> None:
        raise signal

    return leave


def _assert(machine: Machine, node: ast.Assert, env: Env) -> None:
    if not machine.eval(node.test, env):
        said = "" if node.msg is None else machine.eval(node.msg, env)
        raise AssertionError(text_of(machine.budget, said))


def _error_names(kind: ast.expr | None) -> list[str]:
    """The errors an `except` lists, as the words they are written with."""
    parts = kind.elts if isinstance(kind, ast.Tuple) else [kind]
    return [getattr(part, "attr", getattr(part, "id", "")) for part in parts]


def _catches(handler: ast.ExceptHandler, error: Exception) -> bool:
    """An error of Python's own is caught by its name. Any other name stands for a failure
    of the script's own making or of a tool; `Exception` and a bare `except` catch both."""
    names = [] if handler.type is None else _error_names(handler.type)
    if not names or any(name in EVERYTHING for name in names):
        return True
    return isinstance(error, tuple(KNOWN_ERRORS.get(name, ScriptError) for name in names))


def _guarded(machine: Machine, node: ast.Try, env: Env) -> None:
    try:
        machine.run_block(node.body, env)
    except CAUGHT as error:
        handler = next((one for one in node.handlers if _catches(one, error)), None)
        if handler is None:
            raise
        if handler.name:
            # What `as e` names is the error's text: a script has no error objects.
            env.names[handler.name] = describe(error)
        outer, machine.handling = machine.handling, error
        try:
            machine.run_block(handler.body, env)
        finally:
            machine.handling = outer
    else:
        machine.run_block(node.orelse, env)


def _try(machine: Machine, node: ast.Try, env: Env) -> None:
    try:
        _guarded(machine, node, env)
    except (Signal, *CAUGHT):
        # Not on a `Halt`: a script stopped at a limit runs nothing more, `finally` included.
        machine.run_block(node.finalbody, env)
        raise
    machine.run_block(node.finalbody, env)


def _raise(machine: Machine, node: ast.Raise, env: Env) -> None:
    raised = node.exc
    if raised is None:
        if machine.handling is None:
            raise ScriptError(t.SCRIPT_NOTHING_TO_RAISE)
        raise machine.handling
    named = raised.func if isinstance(raised, ast.Call) else raised
    name = getattr(named, "attr", getattr(named, "id", None))
    if name is None or env.find(name) is not None:
        # `raise e`, where `e` is what an `except ... as e` named: the text is raised again.
        raise ScriptError(text_of(machine.budget, machine.eval(raised, env)))
    given = [machine.eval(arg, env) for arg in getattr(raised, "args", ())]
    kind = KNOWN_ERRORS.get(name)
    if not given:
        raise ScriptError(name) if kind is None else kind()
    said: Any = given[0] if len(given) == 1 else tuple(given)
    raise (kind or ScriptError)(text_of(machine.budget, said))


def _nothing(machine: Machine, node: ast.stmt, env: Env) -> None:
    """`pass`, and `import json`: the one import a script may write is already there."""


STATEMENTS: dict[type[ast.stmt], Callable[..., None]] = {
    ast.Expr: lambda machine, node, env: machine.eval(node.value, env),
    ast.Assign: _assign,
    ast.AnnAssign: _annotated,
    ast.AugAssign: _augmented,
    ast.If: _if,
    ast.While: _while,
    ast.For: _for,
    ast.Break: _leave(Break),
    ast.Continue: _leave(Continue),
    ast.FunctionDef: _def,
    ast.Return: _return,
    ast.Assert: _assert,
    ast.Try: _try,
    ast.Raise: _raise,
    ast.Pass: _nothing,
    ast.Import: _nothing,
}
