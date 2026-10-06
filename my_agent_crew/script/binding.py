"""Giving a value a place, and walking one: what `=`, `for` and a comprehension share."""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_script as t
from my_agent_crew.script.limits import ScriptError
from my_agent_crew.script.values import Env, kind_name

if TYPE_CHECKING:
    from my_agent_crew.script.machine import Machine

WALKED = (str, list, tuple, range)
SNAPSHOT = (dict, set)


def iterate(machine: Machine, held: Any) -> Iterable[Any]:
    """What a `for` walks. A dict or a set is walked as it stood when the loop began, so
    a script that changes one while walking it carries on instead of failing mid-loop."""
    if type(held) in WALKED:
        return held
    if type(held) in SNAPSHOT:
        return machine.budget.made(list(held))
    raise ScriptError(t.SCRIPT_NOT_ITERABLE.format(kind=kind_name(held)))


def loops(
    machine: Machine, generators: list[ast.comprehension], env: Env, emit: Callable[[], None]
) -> None:
    """A comprehension's `for`s and `if`s: runs `emit` once for every combination they
    let through."""
    if not generators:
        emit()
        return
    for item in iterate(machine, machine.eval(generators[0].iter, env)):
        assign(machine, generators[0].target, item, env)
        if all(machine.eval(test, env) for test in generators[0].ifs):
            loops(machine, generators[1:], env, emit)


def assign(machine: Machine, target: ast.expr, value: Any, env: Env) -> None:
    """A name is always bound in the scope the statement is in: a script has no `global`."""
    if isinstance(target, ast.Name):
        env.names[target.id] = value
    elif isinstance(target, ast.Tuple | ast.List):
        items = list(iterate(machine, value))
        if len(items) != len(target.elts):
            raise ScriptError(t.SCRIPT_UNPACK.format(got=len(items), want=len(target.elts)))
        for part, item in zip(target.elts, items, strict=True):
            assign(machine, part, item, env)
    elif isinstance(target, ast.Subscript) and not isinstance(target.slice, ast.Slice):
        held = machine.eval(target.value, env)
        if type(held) not in (list, dict):
            raise ScriptError(t.SCRIPT_BAD_TARGET)
        machine.budget.charge(1)
        held[machine.eval(target.slice, env)] = value
    else:
        raise ScriptError(t.SCRIPT_BAD_TARGET)
