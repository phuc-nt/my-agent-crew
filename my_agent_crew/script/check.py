"""What a script may be written with, settled before any of it runs.

The interpreter has a function for each node it knows, and this is the same list read the
other way: a node with no function is turned away here, by the name the model wrote it
with and the line it is on, so the script is refused whole instead of failing half done.
"""

from __future__ import annotations

import ast
import warnings
from collections.abc import Callable, Iterator
from typing import Any

from my_agent_crew import texts_script as t
from my_agent_crew.script.expressions import EXPRESSIONS
from my_agent_crew.script.limits import ScriptError
from my_agent_crew.script.operators import BINARY, COMPARE, UNARY
from my_agent_crew.script.statements import STATEMENTS

# Nodes that are parts of the ones the interpreter works out, never worked out themselves.
PARTS = (
    ast.Module,
    ast.arguments,
    ast.arg,
    ast.keyword,
    ast.comprehension,
    ast.ExceptHandler,
    ast.alias,
    ast.Slice,
    ast.Starred,
    ast.Attribute,
    ast.expr_context,
    ast.And,
    ast.Or,
)
ALLOWED = (*EXPRESSIONS, *STATEMENTS, *BINARY, *COMPARE, *UNARY, *PARTS)
CONSTANTS = (str, int, float, bool, type(None))
# Read as words and never worked out: a type hint, and the error names of an `except`.
SKIPPED: dict[type, tuple[str, ...]] = {
    ast.ExceptHandler: ("type",),
    ast.arg: ("annotation",),
    ast.FunctionDef: ("returns",),
    ast.AnnAssign: ("annotation",),
}
# What the model wrote, for a node Python names differently.
WRITTEN: dict[type, str] = {
    ast.ClassDef: "class",
    ast.With: "with",
    ast.ImportFrom: "from ... import",
    ast.Global: "global",
    ast.Nonlocal: "nonlocal",
    ast.Delete: "del",
    ast.Yield: "yield",
    ast.YieldFrom: "yield from",
    ast.Await: "await",
    ast.AsyncFunctionDef: "async def",
    ast.AsyncFor: "async for",
    ast.AsyncWith: "async with",
    ast.Pow: "**",
    ast.LShift: "<<",
    ast.RShift: ">>",
    ast.MatMult: "@",
    ast.Invert: "~",
    ast.NamedExpr: ":=",
    ast.Match: "match",
    ast.TryStar: "except*",
}
# A node the interpreter knows, written in a way it does not: what to call that, or None.
RULES: dict[type, Callable[[Any], str | None]] = {
    ast.Constant: lambda node: None if type(node.value) in CONSTANTS else type(node.value).__name__,
    ast.Import: lambda node: next(
        (
            f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else "")
            for alias in node.names
            if alias.name != "json" or alias.asname
        ),
        None,
    ),
    ast.arguments: lambda node: (
        "*, / hay ** trong tham số của hàm"
        if node.vararg or node.kwarg or node.posonlyargs or node.kwonlyargs
        else None
    ),
    ast.FunctionDef: lambda node: "@decorator" if node.decorator_list else None,
    ast.comprehension: lambda node: "async for" if node.is_async else None,
    ast.Starred: lambda node: None if isinstance(node.ctx, ast.Load) else "*",
}


def _nodes(tree: ast.AST) -> Iterator[tuple[ast.AST, int]]:
    """Every node of the script with the line it is on, in the order it is read: a node
    before what it holds, and those from first to last."""
    pending: list[tuple[ast.AST, int]] = [(tree, 1)]
    while pending:
        node, line = pending.pop()
        # A decorated `def` begins at its first `@`.
        above = getattr(node, "decorator_list", None)
        line = above[0].lineno if above else getattr(node, "lineno", line)
        yield node, line
        skipped = [getattr(node, part) for part in SKIPPED.get(type(node), ())]
        held = [
            child
            for child in ast.iter_child_nodes(node)
            if not any(child is one for one in skipped)
        ]
        pending.extend((child, line) for child in reversed(held))


def _spread_into(node: ast.AST) -> list[ast.expr]:
    """Where a `*spread` may stand: the arguments of a call, the items of a display."""
    if isinstance(node, ast.Call):
        return node.args
    return node.elts if isinstance(node, ast.List | ast.Tuple | ast.Set) else []


def _refused(node: ast.AST, callees: set[int], spreads: set[int]) -> str | None:
    if not isinstance(node, ALLOWED):
        return t.SCRIPT_UNSUPPORTED.format(what=WRITTEN.get(type(node), type(node).__name__))
    if isinstance(node, ast.Attribute) and id(node) not in callees:
        # The one way out of plain data in Python is an attribute, so there is no reading
        # one: `value.method(...)` is a call of a listed method, and nothing else is.
        return t.SCRIPT_NO_ATTRIBUTE.format(name=node.attr)
    if isinstance(node, ast.Starred) and id(node) not in spreads:
        return t.SCRIPT_UNSUPPORTED.format(what="*")
    what = RULES.get(type(node), lambda node: None)(node)
    return None if what is None else t.SCRIPT_UNSUPPORTED.format(what=what)


def check(tree: ast.Module) -> None:
    nodes = list(_nodes(tree))
    callees = {id(node.func) for node, _ in nodes if isinstance(node, ast.Call)}
    spreads = {id(item) for node, _ in nodes for item in _spread_into(node)}
    refusals = [(line, _refused(node, callees, spreads)) for node, line in nodes]
    found = [(line, why) for line, why in refusals if why is not None]
    if found:
        # The first on the earliest line: what the model wrote first is what it is told of.
        line, why = min(found, key=lambda one: one[0])
        raise ScriptError(t.SCRIPT_REFUSED.format(line=line, why=why))


def parse(source: str) -> ast.Module:
    """The script as a tree the interpreter may walk, or a `ScriptError` saying why not."""
    try:
        with warnings.catch_warnings():
            # An odd escape (`"\d"`) is a warning of Python's, and nobody reads those here.
            warnings.simplefilter("ignore")
            tree = ast.parse(source, "<script>")
            check(tree)
            # Python's own last look, for what is wrong only in its place: a `break` outside
            # a loop, a `return` outside a function. Nothing is run by compiling.
            compile(tree, "<script>", "exec")
    except SyntaxError as exc:
        raise ScriptError(t.SCRIPT_SYNTAX.format(line=exc.lineno or 1, error=exc.msg)) from exc
    except (RecursionError, MemoryError) as exc:
        raise ScriptError(t.SCRIPT_SYNTAX.format(line=1, error=t.SCRIPT_TOO_NESTED)) from exc
    except ValueError as exc:
        raise ScriptError(t.SCRIPT_SYNTAX.format(line=1, error=exc)) from exc
    return tree
