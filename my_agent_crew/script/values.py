"""What a script holds besides plain data: the functions it defined, the built-ins it was
given, and the scopes its names live in. Plain data is None, a flag, a number, a text, and
lists, tuples, dicts, sets and ranges of those; nothing else can come to be in a script."""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# The errors of Python itself that a script's `try` may catch, beside its own.
RUNTIME_ERRORS = (
    TypeError,
    ValueError,
    LookupError,
    ArithmeticError,
    AttributeError,
    AssertionError,
)
# What an `except` or a `raise` can name. A name not here catches whatever can be caught.
KNOWN_ERRORS: dict[str, type[Exception]] = {
    "KeyError": KeyError,
    "IndexError": IndexError,
    "LookupError": LookupError,
    "ValueError": ValueError,
    "JSONDecodeError": ValueError,
    "TypeError": TypeError,
    "ZeroDivisionError": ZeroDivisionError,
    "ArithmeticError": ArithmeticError,
    "AttributeError": AttributeError,
    "AssertionError": AssertionError,
}


class Signal(Exception):
    """How `break`, `continue` and `return` leave where they are. Never an error."""


class Break(Signal):
    pass


class Continue(Signal):
    pass


class Return(Signal):
    def __init__(self, value: Any):
        super().__init__()
        self.value = value


class Env:
    """One scope: its own names, and the scope it was opened in."""

    __slots__ = ("names", "parent")

    def __init__(self, parent: Env | None = None):
        self.names: dict[str, Any] = {}
        self.parent = parent

    def find(self, name: str) -> dict[str, Any] | None:
        """The names of the nearest scope that holds `name`."""
        scope: Env | None = self
        while scope is not None:
            if name in scope.names:
                return scope.names
            scope = scope.parent
        return None


class Function:
    """A `def` or a `lambda` of the script, with the scope it was written in."""

    __slots__ = ("body", "defaults", "env", "name", "params")

    def __init__(
        self, name: str, params: list[str], defaults: list[Any], body: list[ast.stmt] | ast.expr
    ):
        self.name = name
        self.params = params
        self.defaults = defaults
        self.body = body
        self.env: Env | None = None

    def __repr__(self) -> str:
        return f"<function {self.name}>"


@dataclass(frozen=True)
class Builtin:
    """A function a script is given. `call(machine, args, kwargs)` is all it is; `kind` is
    the type `isinstance` means by its name."""

    name: str
    call: Callable[..., Any]
    kind: type | None = None

    def __repr__(self) -> str:
        return f"<function {self.name}>"


def kind_name(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, Function | Builtin):
        return "function"
    return type(value).__name__
