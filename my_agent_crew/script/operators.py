"""The operators a script has, and how its values become text.

Only what is listed here exists. There is no `**` and no shift, because one of either makes
a number of any size; `%` does arithmetic and never formats a text, because a width in a
format is an allocation the script names freely. An f-string's format is held to a short
pattern for the same reason.
"""

from __future__ import annotations

import ast
import json
import operator
import re
from collections.abc import Callable
from typing import Any

from my_agent_crew import texts_script as t
from my_agent_crew.script.limits import Budget, ScriptError
from my_agent_crew.script.values import RUNTIME_ERRORS

BINARY: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.BitOr: operator.or_,
    ast.BitAnd: operator.and_,
    ast.BitXor: operator.xor,
}
COMPARE: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
    ast.In: lambda left, right: left in right,
    ast.NotIn: lambda left, right: left not in right,
}
UNARY: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.Not: operator.not_,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
# `x += y`: Python's own in-place operators, so a list a function was handed grows where
# it is, as it does in Python, and a text or a number is simply made anew.
INPLACE: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.iadd,
    ast.Sub: operator.isub,
    ast.Mult: operator.imul,
    ast.Div: operator.itruediv,
    ast.FloorDiv: operator.ifloordiv,
    ast.Mod: operator.imod,
    ast.BitOr: operator.ior,
    ast.BitAnd: operator.iand,
    ast.BitXor: operator.ixor,
}
REPEATED = (str, list, tuple)
# Alignment, sign, zero padding, a width of three digits at most, thousands, precision, type.
FORMAT_SPEC = re.compile(r"[<>^=]?[+-]?0?\d{0,3},?(\.\d{1,2})?[dfsge%]?")
FORMATTED = (str, int, float, bool)


def binary(
    budget: Budget,
    op: ast.operator,
    left: Any,
    right: Any,
    table: dict[type[ast.operator], Callable[[Any, Any], Any]] = BINARY,
) -> Any:
    kind = type(op)
    if kind is ast.Mult:
        for held, times in ((left, right), (right, left)):
            if type(held) in REPEATED and isinstance(times, int):
                budget.fits(len(held) * times)
    elif kind is ast.Mod and type(left) is str:
        raise ScriptError(t.SCRIPT_NO_PERCENT)
    return budget.made(table[kind](left, right))


def text_of(budget: Budget, value: Any, write: Callable[[Any], str] = str) -> str:
    """`str(value)` or `repr(value)`, measured before it is written."""
    if type(value) is str and write is str:
        return value
    budget.measure(value)
    return budget.made(write(value))


def render(budget: Budget, value: Any) -> str:
    """A value as a script's answer shows it: a text as it is, data as JSON."""
    if type(value) is str:
        return value
    budget.measure(value)
    try:
        return budget.made(json.dumps(value, ensure_ascii=False))
    except RUNTIME_ERRORS:
        return budget.made(str(value))


def formatted(budget: Budget, value: Any, conversion: int, spec: str) -> str:
    """One `{value!r:spec}` of an f-string."""
    if not FORMAT_SPEC.fullmatch(spec):
        raise ScriptError(t.SCRIPT_BAD_FORMAT.format(spec=spec))
    if conversion != -1:
        value = text_of(budget, value, str if conversion == ord("s") else repr)
    elif type(value) not in FORMATTED:
        value = text_of(budget, value)
    return budget.made(format(value, spec))


def describe(error: Exception) -> str:
    """An error as the script's `except ... as e` and the model read it."""
    said = str(error)
    if isinstance(error, ScriptError) or not said:
        return said or type(error).__name__
    return f"{type(error).__name__}: {said}"
