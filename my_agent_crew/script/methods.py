"""The methods a script may call on its values: a list per type, and nothing off it.

A method is looked up only by the exact type of the value and only when its name is listed
here, so no attribute of Python's own can be reached through one. The ones that can make
far more than they were given are sized before they run, and the ones that grow a value in
place are charged for what they add.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_script as t
from my_agent_crew.script.builtins import BUILTINS
from my_agent_crew.script.limits import ScriptError
from my_agent_crew.script.values import kind_name

if TYPE_CHECKING:
    from my_agent_crew.script.machine import Machine

METHODS: dict[type, frozenset[str]] = {
    str: frozenset(
        "lower upper title capitalize strip lstrip rstrip split rsplit splitlines join replace "
        "startswith endswith find rfind index count removeprefix removesuffix partition "
        "rpartition isdigit isalpha isalnum isspace isupper islower".split()
    ),
    list: frozenset("append extend insert pop remove index count sort reverse copy clear".split()),
    dict: frozenset("get keys values items pop setdefault update copy clear".split()),
    set: frozenset("add discard remove update union intersection difference copy clear".split()),
    tuple: frozenset(("index", "count")),
}
# These hand back something the script already holds, so there is nothing new to charge.
HELD = frozenset(("get", "pop", "setdefault"))
# These add to the value they are called on: one item, or as many as they are given.
ADDS_ONE = frozenset(("append", "insert", "add", "setdefault"))
ADDS_MANY = frozenset(("extend", "update"))
LISTED = frozenset(("keys", "values", "items"))

Special = Callable[["Machine", Any, list[Any], dict[str, Any]], Any]


def _join(machine: Machine, held: str, args: list[Any], kwargs: dict[str, Any]) -> str:
    (given,) = args
    parts = list(given)
    between = len(held) * max(len(parts) - 1, 0)
    machine.budget.fits(sum(len(part) for part in parts if type(part) is str) + between)
    return machine.budget.made(held.join(parts))


def _replace(machine: Machine, held: str, args: list[Any], kwargs: dict[str, Any]) -> str:
    if len(args) >= 2 and type(args[0]) is str and type(args[1]) is str:
        old, new = args[0], args[1]
        places = held.count(old)
        if len(args) > 2 and type(args[2]) is int and args[2] >= 0:
            places = min(places, args[2])
        # Each place `old` stands in makes the text longer by what `new` is longer.
        machine.budget.fits(len(held) + places * max(len(new) - len(old), 0))
    return machine.budget.made(held.replace(*args, **kwargs))


def _sort(machine: Machine, held: list[Any], args: list[Any], kwargs: dict[str, Any]) -> None:
    held[:] = BUILTINS["sorted"].call(machine, [held, *args], kwargs)


SPECIAL: dict[tuple[type, str], Special] = {
    (str, "join"): _join,
    (str, "replace"): _replace,
    (list, "sort"): _sort,
}


def call_method(
    machine: Machine, held: Any, name: str, args: list[Any], kwargs: dict[str, Any]
) -> Any:
    kind = type(held)
    if name not in METHODS.get(kind, ()):
        raise ScriptError(t.SCRIPT_NO_METHOD.format(kind=kind_name(held), name=name))
    special = SPECIAL.get((kind, name))
    if special is not None:
        return special(machine, held, args, kwargs)
    if name in ADDS_ONE or name in ADDS_MANY:
        # A generator would be walked twice; a script has none, only things with a length.
        added = 1 if name in ADDS_ONE else sum(len(given) for given in args) + len(kwargs)
        # Sized before it grows: nothing looks at a value again once it has grown in place.
        machine.budget.fits(len(held) + added)
        machine.budget.charge(added)
    made = getattr(held, name)(*args, **kwargs)
    if name in LISTED:
        made = list(made)
    return made if name in HELD else machine.budget.made(made)
