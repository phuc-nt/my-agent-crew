"""The functions a script is given. Each is `call(machine, args, kwargs)`.

What makes something new charges for it. What walks its argument takes a list, never a
generator: `enumerate`, `zip` and `reversed` hand back lists, so every value a script holds
has a length that was charged. A function the script passes as `key=` is called by the
interpreter, one item at a time; nothing of Python's own is ever handed the script's code.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_script as t
from my_agent_crew.script.limits import MAX_STEPS, ScriptError
from my_agent_crew.script.operators import text_of
from my_agent_crew.script.values import Builtin

if TYPE_CHECKING:
    from my_agent_crew.script.machine import Machine

Call = Callable[["Machine", list[Any], dict[str, Any]], Any]
PRINT_NAMED = {"sep", "end", "flush"}


def _wrong(name: str) -> ScriptError:
    """Called with the wrong arguments, said in the script's words and not the interpreter's."""
    return ScriptError(t.SCRIPT_BAD_CALL.format(name=name))


def _plain(name: str, make: Callable[..., Any]) -> Call:
    """A function of Python's own over plain values, taking none of them by name."""

    def call(machine: Machine, args: list[Any], kwargs: dict[str, Any]) -> Any:
        if kwargs:
            raise ScriptError(t.SCRIPT_NO_KEYWORDS.format(name=name))
        return machine.budget.made(make(*args))

    return call


def _named(make: Callable[..., Any]) -> Call:
    return lambda machine, args, kwargs: machine.budget.made(make(*args, **kwargs))


def _text(name: str, write: Callable[[Any], str]) -> Call:
    def call(machine: Machine, args: list[Any], kwargs: dict[str, Any]) -> str:
        if len(args) > 1 or kwargs:
            raise _wrong(name)
        return text_of(machine.budget, args[0] if args else "", write)

    return call


def _range(machine: Machine, args: list[Any], kwargs: dict[str, Any]) -> range:
    if kwargs:
        raise ScriptError(t.SCRIPT_NO_KEYWORDS.format(name="range"))
    made = range(*args)
    try:
        length = len(made)
    except OverflowError:
        length = MAX_STEPS + 1
    if length > MAX_STEPS:
        raise ScriptError(t.SCRIPT_RANGE.format(most=MAX_STEPS))
    return made


def _keys(machine: Machine, items: list[Any], key: Any) -> list[Any]:
    return items if key is None else [machine.call(key, [item], {}) for item in items]


def _sorted(machine: Machine, args: list[Any], kwargs: dict[str, Any]) -> list[Any]:
    if len(args) != 1 or kwargs.keys() - {"key", "reverse"}:
        raise _wrong("sorted")
    items = machine.budget.made(list(args[0]))
    keys = _keys(machine, items, kwargs.get("key"))
    order = sorted(range(len(items)), key=keys.__getitem__, reverse=bool(kwargs.get("reverse")))
    return [items[index] for index in order]


def _extreme(name: str, pick: Callable[..., Any]) -> Call:
    def call(machine: Machine, args: list[Any], kwargs: dict[str, Any]) -> Any:
        if not args or kwargs.keys() - {"key", "default"}:
            raise _wrong(name)
        items = list(args[0]) if len(args) == 1 else list(args)
        keys = _keys(machine, items, kwargs.get("key"))
        if not items:
            if "default" not in kwargs:
                raise ScriptError(t.SCRIPT_EMPTY.format(name=name))
            return kwargs["default"]
        return items[pick(range(len(items)), key=keys.__getitem__)]

    return call


def _sum(machine: Machine, args: list[Any], kwargs: dict[str, Any]) -> Any:
    if not 1 <= len(args) <= 2 or kwargs.keys() - {"start"}:
        raise _wrong("sum")
    start = args[1] if len(args) == 2 else kwargs.get("start", 0)
    if not isinstance(start, int | float):
        raise ScriptError(t.SCRIPT_SUM)
    return machine.budget.made(sum(args[0], start))


def _isinstance(machine: Machine, args: list[Any], kwargs: dict[str, Any]) -> bool:
    if len(args) != 2 or kwargs:
        raise _wrong("isinstance")
    value, named = args
    kinds = []
    for one in named if type(named) is tuple else (named,):
        if type(one) is not Builtin or one.kind is None:
            raise ScriptError(t.SCRIPT_ISINSTANCE)
        kinds.append(one.kind)
    return isinstance(value, tuple(kinds))


def _print(machine: Machine, args: list[Any], kwargs: dict[str, Any]) -> None:
    sep, end = kwargs.get("sep", " "), kwargs.get("end", "\n")
    if type(sep) is not str or type(end) is not str or kwargs.keys() - PRINT_NAMED:
        raise _wrong("print")
    # Written piece by piece: joined first, a thousand long texts would be one text of
    # all of them before any of it was turned away.
    texts = [text_of(machine.budget, value) for value in args]
    for index, text in enumerate(texts):
        machine.write(sep + text if index else text)
    machine.write(end)


def _table() -> dict[str, Builtin]:
    kinds: dict[str, tuple[Call, type]] = {
        "str": (_text("str", str), str),
        "int": (_plain("int", int), int),
        "float": (_plain("float", float), float),
        "bool": (_plain("bool", bool), bool),
        "list": (_plain("list", list), list),
        "tuple": (_plain("tuple", tuple), tuple),
        "set": (_plain("set", set), set),
        "dict": (_named(dict), dict),
    }
    calls: dict[str, Call] = {
        "repr": _text("repr", repr),
        "len": _plain("len", len),
        "range": _range,
        "enumerate": _named(lambda *args, **kwargs: list(enumerate(*args, **kwargs))),
        "zip": _plain("zip", lambda *args: list(zip(*args, strict=False))),
        "reversed": _plain("reversed", lambda *args: list(reversed(*args))),
        "sorted": _sorted,
        "min": _extreme("min", min),
        "max": _extreme("max", max),
        "sum": _sum,
        "any": _plain("any", any),
        "all": _plain("all", all),
        "abs": _plain("abs", abs),
        "round": _plain("round", round),
        "isinstance": _isinstance,
        "print": _print,
    }
    table = {name: Builtin(name, call, kind) for name, (call, kind) in kinds.items()}
    table.update({name: Builtin(name, call) for name, call in calls.items()})
    return table


BUILTINS = _table()
