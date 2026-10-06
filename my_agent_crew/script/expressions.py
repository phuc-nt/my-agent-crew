"""How each kind of expression a script may write is worked out.

One function per node, `(machine, node, scope)`, in the table at the end. A node with no
function here is not part of the language; `check.py` turns it away before anything runs.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_script as t
from my_agent_crew.script.binding import iterate, loops
from my_agent_crew.script.builtins import BUILTINS
from my_agent_crew.script.limits import ScriptError
from my_agent_crew.script.methods import call_method
from my_agent_crew.script.namespaces import NAMESPACES
from my_agent_crew.script.operators import COMPARE, UNARY, binary, formatted
from my_agent_crew.script.values import Env, Function, kind_name

if TYPE_CHECKING:
    from my_agent_crew.script.machine import Machine

INDEXED = (str, list, tuple, dict, range)


def _name(machine: Machine, node: ast.Name, env: Env) -> Any:
    held = env.find(node.id)
    if held is not None:
        return held[node.id]
    if node.id in BUILTINS:
        return BUILTINS[node.id]
    missing = t.SCRIPT_NAMESPACE if node.id in NAMESPACES else t.SCRIPT_NO_NAME
    raise ScriptError(missing.format(name=node.id))


def _items(machine: Machine, nodes: Iterable[ast.expr], env: Env) -> list[Any]:
    """The values of a display's items or a call's arguments, a `*spread` opened in place."""
    items: list[Any] = []
    for node in nodes:
        if isinstance(node, ast.Starred):
            items.extend(iterate(machine, machine.eval(node.value, env)))
            machine.budget.fits(len(items))
        else:
            items.append(machine.eval(node, env))
    return items


def _display(make: Callable[[list[Any]], Any]) -> Callable[..., Any]:
    return lambda machine, node, env: machine.budget.made(make(_items(machine, node.elts, env)))


def _dict(machine: Machine, node: ast.Dict, env: Env) -> dict[Any, Any]:
    made: dict[Any, Any] = {}
    for key, value in zip(node.keys, node.values, strict=True):
        if key is not None:
            made[machine.eval(key, env)] = machine.eval(value, env)
            continue
        opened = machine.eval(value, env)  # `{**other, ...}`
        if type(opened) is not dict:
            raise ScriptError(t.SCRIPT_SPREAD)
        made.update(opened)
        machine.budget.fits(len(made))
    return machine.budget.made(made)


def _joined(machine: Machine, node: ast.JoinedStr, env: Env) -> str:
    parts = [machine.eval(part, env) for part in node.values]
    machine.budget.fits(sum(len(part) for part in parts))
    return machine.budget.made("".join(parts))


def _formatted(machine: Machine, node: ast.FormattedValue, env: Env) -> str:
    value = machine.eval(node.value, env)
    spec = machine.eval(node.format_spec, env) if node.format_spec is not None else ""
    return formatted(machine.budget, value, node.conversion, spec)


def _bool(machine: Machine, node: ast.BoolOp, env: Env) -> Any:
    settles = isinstance(node.op, ast.Or)
    value = None
    for part in node.values:
        value = machine.eval(part, env)
        if bool(value) is settles:
            break
    return value


def _compare(machine: Machine, node: ast.Compare, env: Env) -> bool:
    left = machine.eval(node.left, env)
    for op, part in zip(node.ops, node.comparators, strict=True):
        right = machine.eval(part, env)
        if not COMPARE[type(op)](left, right):
            return False
        left = right
    return True


def _subscript(machine: Machine, node: ast.Subscript, env: Env) -> Any:
    held = machine.eval(node.value, env)
    if type(held) not in INDEXED:
        raise ScriptError(t.SCRIPT_NOT_INDEXED.format(kind=kind_name(held)))
    if not isinstance(node.slice, ast.Slice):
        return held[machine.eval(node.slice, env)]
    bounds = (node.slice.lower, node.slice.upper, node.slice.step)
    cut = slice(*(None if part is None else machine.eval(part, env) for part in bounds))
    return machine.budget.made(held[cut])


def _comprehension(machine: Machine, node: Any, env: Env) -> Any:
    # A generator is worked out whole, as a list: a script has no lazy values.
    scope = Env(env)
    made: list[Any] = []
    pairs = isinstance(node, ast.DictComp)

    def emit() -> None:
        machine.budget.charge(1)
        if pairs:
            made.append((machine.eval(node.key, scope), machine.eval(node.value, scope)))
        else:
            made.append(machine.eval(node.elt, scope))

    loops(machine, node.generators, scope, emit)
    if pairs:
        return dict(made)
    return set(made) if isinstance(node, ast.SetComp) else made


def function(machine: Machine, node: ast.Lambda | ast.FunctionDef, env: Env) -> Function:
    defaults = [machine.eval(default, env) for default in node.args.defaults]
    params = [arg.arg for arg in node.args.args]
    made = Function(getattr(node, "name", "lambda"), params, defaults, node.body)
    made.env = env
    return made


def _keywords(machine: Machine, keywords: list[ast.keyword], env: Env) -> dict[str, Any]:
    named: dict[str, Any] = {}
    for keyword in keywords:
        value = machine.eval(keyword.value, env)
        if keyword.arg is not None:
            named[keyword.arg] = value
        elif type(value) is dict and all(type(key) is str for key in value):
            named.update(value)
        else:
            raise ScriptError(t.SCRIPT_SPREAD)
    return named


def _call(machine: Machine, node: ast.Call, env: Env) -> Any:
    callee = node.func
    if not isinstance(callee, ast.Attribute):
        called = machine.eval(callee, env)
        args, named = _items(machine, node.args, env), _keywords(machine, node.keywords, env)
        return machine.call(called, args, named)
    owner = callee.value
    if isinstance(owner, ast.Name) and owner.id in NAMESPACES and env.find(owner.id) is None:
        args, named = _items(machine, node.args, env), _keywords(machine, node.keywords, env)
        return NAMESPACES[owner.id](machine, callee.attr, args, named)
    held = machine.eval(owner, env)
    args, named = _items(machine, node.args, env), _keywords(machine, node.keywords, env)
    return call_method(machine, held, callee.attr, args, named)


EXPRESSIONS: dict[type[ast.expr], Callable[..., Any]] = {
    ast.Constant: lambda machine, node, env: node.value,
    ast.Name: _name,
    ast.List: _display(list),
    ast.Tuple: _display(tuple),
    ast.Set: _display(set),
    ast.Dict: _dict,
    ast.JoinedStr: _joined,
    ast.FormattedValue: _formatted,
    ast.BinOp: lambda machine, node, env: binary(
        machine.budget, node.op, machine.eval(node.left, env), machine.eval(node.right, env)
    ),
    ast.UnaryOp: lambda machine, node, env: machine.budget.made(
        UNARY[type(node.op)](machine.eval(node.operand, env))
    ),
    ast.BoolOp: _bool,
    ast.Compare: _compare,
    ast.IfExp: lambda machine, node, env: machine.eval(
        node.body if machine.eval(node.test, env) else node.orelse, env
    ),
    ast.Subscript: _subscript,
    ast.ListComp: _comprehension,
    ast.SetComp: _comprehension,
    ast.DictComp: _comprehension,
    ast.GeneratorExp: _comprehension,
    ast.Lambda: function,
    ast.Call: _call,
}
