"""A tool's parameters with their repeats said once.

A schema written out by a program often holds one part many times over: a list of filters
of which each may hold the whole list again, written in full at every place it is allowed.
Here a schema that stands more than once is moved under `$defs` at the top and pointed to
with `$ref`, wherever that makes the whole shorter. What the schema asks for stays as it
was: putting each part back where it is pointed to gives the source again, letter for
letter, and a fold that does not is not used.

Only a whole schema is moved, and only from a place where a schema stands; `schema_parts`
says which places those are and which schemas are not read at all. A `$ref` the source
came with is left as it is, and so is what it points to.
"""

from __future__ import annotations

import json
from collections import Counter
from itertools import count
from typing import Any

from my_agent_crew.mcp.schema_parts import DEFS, REF, Reading, Unread, under, with_places

# The most that is read. Folding runs where a server's list is taken in, on the loop that
# serves everyone, and takes a few hundredths of a second at this size. A schema longer
# than this would have to be nine parts in ten repeats to come under what is taken anyway.
MAX_FOLD_CHARS = 500_000

NAME, POINTER = "shared{}", "#/$defs/{}"


def _moved(reading: Reading, source: dict[str, Any], taken: set[str]) -> dict[int, dict[str, Any]]:
    """The schemas worth moving, by number, each as it first stands in the source and in
    the order they first stand there."""
    first: dict[int, dict[str, Any]] = {}
    uses: Counter[int] = Counter()

    def meet(schema: dict[str, Any]) -> None:
        number = reading.of[id(schema)]
        if number in first:
            return
        first[number] = schema
        for member in under(schema):
            uses[reading.of[id(member)]] += 1
            meet(member)

    meet(source)
    # No name given here is longer than this one, so nothing is counted as gained that is not.
    longest = NAME.format(len(first) + len(taken))
    pointer = len(json.dumps({REF: POINTER.format(longest)}))
    entry = len(json.dumps(longest)) + len(": , ")
    # What each takes where it stands once folded: its own letters, or a pointer's.
    stands: dict[int, int] = {}
    moved: set[int] = set()
    # Shortest first, so everything under a schema is settled before it is.
    for number in sorted(first, key=reading.chars.__getitem__):
        below = (reading.of[id(member)] for member in under(first[number]))
        own = reading.chars[number] - sum(reading.chars[m] - stands[m] for m in below)
        # Said once and pointed to from each place, against written out at each. The
        # source itself stands nowhere, so it never gains.
        gained = (uses[number] - 1) * own - uses[number] * pointer - entry
        if gained > 0:
            moved.add(number)
        stands[number] = pointer if gained > 0 else own
    return {number: schema for number, schema in first.items() if number in moved}


def _unfolded(folded: dict[str, Any], names: set[str], had_defs: bool) -> dict[str, Any]:
    """The folded schema with every part put back where a pointer to it stands. It knows
    nothing of where a schema may stand: it goes by the pointers alone."""
    moved = {POINTER.format(name): folded[DEFS][name] for name in names}

    def back(node: Any) -> Any:
        if isinstance(node, list):
            return [back(member) for member in node]
        if not isinstance(node, dict):
            return node
        if len(node) == 1 and isinstance(node.get(REF), str) and node[REF] in moved:
            return back(moved[node[REF]])
        return {key: back(value) for key, value in node.items()}

    kept = {name: said for name, said in folded[DEFS].items() if name not in names}
    whole = back({**folded, DEFS: kept})
    if not had_defs:
        del whole[DEFS]
    return whole


def _fold(schema: dict[str, Any]) -> dict[str, Any] | None:
    source = json.dumps(schema, ensure_ascii=False)
    if len(source) > MAX_FOLD_CHARS or not isinstance(schema.get(DEFS, {}), dict):
        return None
    reading = Reading()
    reading.read(schema)
    # A part moved here takes no name the source has a definition under or points to.
    taken = reading.pointed | set(schema.get(DEFS, ()))
    moved = _moved(reading, schema, taken)
    free = (name for n in count(1) if (name := NAME.format(n)) not in taken)
    names = {number: next(free) for number in moved}

    def place(member: Any) -> Any:
        if not isinstance(member, dict):
            return member
        name = names.get(reading.of[id(member)])
        return {REF: POINTER.format(name)} if name else with_places(member, place)

    folded = with_places(schema, place)
    told = {names[number]: with_places(said, place) for number, said in moved.items()}
    folded[DEFS] = {**folded.get(DEFS, {}), **told}
    shorter = len(json.dumps(folded, ensure_ascii=False)) < len(source)
    whole = _unfolded(folded, set(told), DEFS in schema)
    return folded if shorter and json.dumps(whole, ensure_ascii=False) == source else None


def fold(schema: dict[str, Any]) -> dict[str, Any] | None:
    """The schema with each part that repeats said once under `$defs`, or None when it is
    not folded: nothing is gained, it is more than is read, or it is one not read here."""
    try:
        return _fold(schema)
    except (Unread, RecursionError):
        return None
