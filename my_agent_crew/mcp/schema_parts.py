"""A schema taken apart: where one schema stands inside another, and which parts say the
same.

A schema stands only at the places the keywords below make. A map of properties is names,
so a parameter called `items` is a parameter; what `enum`, `const`, `default` or
`examples` hold is a value and is never read as a schema; a keyword not known here is left
as it is.

Some schemas are not read at all (`Unread`): one that names itself (`$id`, an anchor) or
points anywhere but at one of its own definitions, since where a pointer leads from there
is more than is followed here. That is judged by the letters alone, so a parameter that
happens to be called `$id` is taken for the keyword.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

DEFS, REF = "$defs", "$ref"
# Where a schema stands: as the keyword's value, as a member of its list, as a value of
# its map. `items` is written either way.
_ONE = frozenset(
    ("items", "additionalProperties", "not", "if", "then", "else", "contains", "propertyNames")
)
_LISTED = frozenset(("anyOf", "oneOf", "allOf", "prefixItems", "items"))
_NAMED = frozenset(("properties", "patternProperties", "dependentSchemas", DEFS, "definitions"))
_NAMES_ITSELF = frozenset(
    ("$id", "$anchor", "$dynamicRef", "$dynamicAnchor", "$recursiveRef", "$recursiveAnchor")
)
_OWN_DEFINITION = re.compile(r"#/(?:\$defs|definitions)/([^/#%~]+)")


class Unread(Exception):
    """The schema is one that is not read here."""


def with_places(schema: dict[str, Any], place: Callable[[Any], Any]) -> dict[str, Any]:
    """The schema with `place` asked what goes at each place right under it where a schema
    stands. Everything else is handed on as the same object."""
    made: dict[str, Any] = {}
    for key, value in schema.items():
        if key in _ONE and isinstance(value, dict):
            made[key] = place(value)
        elif key in _LISTED and isinstance(value, list):
            made[key] = [place(member) for member in value]
        elif key in _NAMED and isinstance(value, dict):
            made[key] = {name: place(member) for name, member in value.items()}
        else:
            made[key] = value
    return made


def under(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """The schemas right under this one, in the order written."""
    found: list[Any] = []
    with_places(schema, found.append)
    return [member for member in found if isinstance(member, dict)]


class Reading:
    """Every part of one schema numbered by what it says: two parts that say the same have
    one number, however far apart they stand."""

    def __init__(self) -> None:
        self.numbers: dict[Any, int] = {}
        # By number: the letters a part takes written as JSON.
        self.chars: list[int] = []
        # By `id`: the number of a map or a list of the source.
        self.of: dict[int, int] = {}
        # The names a `$ref` of the source points to.
        self.pointed: set[str] = set()

    def _numbered(self, said: Any, chars: int) -> int:
        number = self.numbers.get(said)
        if number is None:
            number = self.numbers[said] = len(self.chars)
            self.chars.append(chars)
        return number

    def read(self, node: Any) -> int:
        """The number of a part, after numbering everything in it."""
        if not isinstance(node, dict | list):
            text = json.dumps(node, ensure_ascii=False)
            return self._numbered(text, len(text))
        if isinstance(node, list):
            said: tuple[Any, ...] = (None, *map(self.read, node))
            inside = sum(self.chars[member] for member in said[1:])
        else:
            for key, value in node.items():
                self._checked(key, value)
            said = tuple((key, self.read(value)) for key, value in node.items())
            # A key is written as a text is, with `: ` after it.
            inside = sum(self.chars[self.read(key)] + 2 + self.chars[m] for key, m in said)
        # The brackets, and `, ` between one member and the next.
        number = self.of[id(node)] = self._numbered(said, inside + 2 * max(len(node), 1))
        return number

    def _checked(self, key: str, value: Any) -> None:
        if key in _NAMES_ITSELF:
            raise Unread
        if key == REF:
            own = _OWN_DEFINITION.fullmatch(value) if isinstance(value, str) else None
            if own is None:
                raise Unread
            self.pointed.add(own[1])
