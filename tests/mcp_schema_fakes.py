"""Parameters as a program writes them out: one part in full at every place it is allowed.

Everything is built anew on each call, so no two parts are one object in memory, which is
how a schema read off the wire is. The words in it are made up; no server's own schema is
copied here.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

DEFS_POINTER = "#/$defs/"
# The rows a query may be told about, each by the same list of filters written out in full.
PLACES = ("filter", "exclude", "highlight", "group")
KINDS = 13
# Words of `moment`, by how deep they stand in `parameters`, counted the way a search reads
# a schema: FOUND is in the deepest part it reads, UNREAD one step below that.
FOUND, FOUND_NAME, UNREAD = "fortnight", "lunar", "equinox"


def chars(schema: Any) -> int:
    return len(json.dumps(schema, ensure_ascii=False))


def text(schema: Any) -> str:
    """The schema letter for letter, in the order it is written."""
    return json.dumps(schema, ensure_ascii=False)


def unfolded(folded: dict[str, Any], moved: Iterable[str] | None = None) -> dict[str, Any]:
    """The schema with every pointer to a moved part put back, and those parts gone from
    `$defs`: the ones named, or every one called `shared…` where none is. Written apart
    from the fold's own check, so one can be held to the other."""
    defs = folded.get("$defs", {})
    names = {name for name in defs if name.startswith("shared")} if moved is None else set(moved)

    def back(node: Any) -> Any:
        if isinstance(node, list):
            return [back(member) for member in node]
        if not isinstance(node, dict):
            return node
        ref = node.get("$ref")
        if len(node) == 1 and isinstance(ref, str) and ref.removeprefix(DEFS_POINTER) in names:
            return back(defs[ref.removeprefix(DEFS_POINTER)])
        return {key: back(value) for key, value in node.items()}

    kept = {name: said for name, said in defs.items() if name not in names}
    whole = back({**folded, "$defs": kept})
    if not kept:
        del whole["$defs"]
    return whole


def moment() -> dict[str, Any]:
    """A point in time, as several kinds of filter take one."""
    return {
        "type": "object",
        "description": "A moment: one date, or a span counted back from today.",
        "properties": {
            "date": {"type": "string", "format": "date"},
            "span": {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "minimum": 1},
                    "every": {
                        "type": "object",
                        "properties": {
                            "weekday": {
                                "type": "object",
                                "description": f"Counted by the {FOUND}.",
                                "properties": {
                                    FOUND_NAME: {
                                        "type": "boolean",
                                        "description": f"Counted from the {UNREAD}.",
                                    }
                                },
                            }
                        },
                    },
                },
            },
        },
        "additionalProperties": False,
    }


def stamp() -> dict[str, Any]:
    """A day and an hour of it: what a query runs from and to."""
    return {
        "type": "object",
        "description": "A day and an hour of it, in the owner's own time.",
        "properties": {
            "day": {"type": "string", "format": "date"},
            "hour": {"type": "integer", "minimum": 0, "maximum": 23},
        },
    }


def kind(number: int) -> dict[str, Any]:
    """One kind of filter: what a row's field is held against."""
    return {
        "type": "object",
        "description": f"Kind {number}: keeps a row by what its field number {number} holds, "
        "against a word, or a moment on either side of it. " + "Rows are read in order. " * 6,
        "properties": {
            "field": {"type": "string", "description": f"The field of kind {number}."},
            "equals": {"type": "string"},
            "before": moment(),
            "after": moment(),
        },
        "required": ["field"],
    }


def where(kinds: int = KINDS) -> dict[str, Any]:
    return {"anyOf": [kind(number) for number in range(kinds)]}


def parameters(places: tuple[str, ...] = PLACES, kinds: int = KINDS) -> dict[str, Any]:
    """A query's parameters: the whole list of filters at every place, and the stamps the
    query runs from and to. With the places and kinds it has by default it is more than a
    tool's parameters may be, and well under that once folded."""
    listed = {
        place: {
            "type": "object",
            "description": f"The rows to {place}.",
            "properties": {"where": where(kinds)},
        }
        for place in places
    }
    return {
        "type": "object",
        "properties": {**listed, "since": stamp(), "until": stamp()},
        "required": [places[0]],
    }


def padded(schema: dict[str, Any], size: int) -> dict[str, Any]:
    """The schema with a description at its top that makes it exactly this many letters."""
    made = {**schema, "description": ""}
    made["description"] = "x" * (size - chars(made))
    assert chars(made) == size
    return made
