"""A schema with its repeats said once: which parts are moved, from where, under what
names, and which schemas are left alone (`mcp/schema_fold.py`, `mcp/schema_parts.py`)."""

from __future__ import annotations

import copy
import json

import pytest

from my_agent_crew.mcp import schema_fold
from my_agent_crew.mcp.schema_fold import MAX_FOLD_CHARS, fold
from my_agent_crew.mcp.schema_parts import Reading
from tests.mcp_schema_fakes import chars, moment, padded, parameters, text, unfolded

ONE = ("items", "additionalProperties", "not", "if", "then", "else", "contains", "propertyNames")
LISTED = ("anyOf", "oneOf", "allOf", "prefixItems", "items")
NAMED = ("properties", "patternProperties", "dependentSchemas", "$defs", "definitions")
PLACES = [
    *((k, "one") for k in ONE),
    *((k, "listed") for k in LISTED),
    *((k, "named") for k in NAMED),
]


def address(of: str = "a parcel") -> dict:
    return {
        "type": "object",
        "description": f"Where {of} goes.",
        "properties": {"street": {"type": "string"}, "city": {"type": "string"}},
        "required": ["city"],
        "additionalProperties": False,
    }


def ref(number: int) -> dict:
    return {"$ref": f"#/$defs/shared{number}"}


def held(shape: str, part: dict):
    """The part as a keyword holds it: alone, in a list, or under a name."""
    return {"one": part, "listed": [{"type": "null"}, part], "named": {"a": part}}[shape]


def pair(**more) -> dict:
    """A schema that folds: one address at two places."""
    return {"type": "object", "properties": {"from": address(), "to": address(), **more}}


def test_a_part_that_stands_twice_is_said_once_and_pointed_to():
    schema = {**pair(), "required": ["to"]}

    folded = fold(schema)

    assert folded == {
        "type": "object",
        "properties": {"from": ref(1), "to": ref(1)},
        "required": ["to"],
        "$defs": {"shared1": address()},
    }
    # What is added stands last, so everything else reads in the order it was written.
    assert list(folded) == ["type", "properties", "required", "$defs"]
    assert chars(folded) < chars(schema)
    assert text(unfolded(folded)) == text(schema)


def test_folding_leaves_the_source_as_it_was():
    schema = parameters()
    before = text(schema)

    folded = fold(schema)

    assert folded is not schema and text(schema) == before


@pytest.mark.parametrize(("keyword", "shape"), PLACES, ids=[f"{k} {s}" for k, s in PLACES])
def test_a_part_is_moved_from_every_place_a_schema_stands(keyword, shape):
    def holder(title: str, part: dict) -> dict:
        return {"title": title, keyword: held(shape, part)}

    schema = {
        "type": "object",
        "properties": {"x": holder("x", address()), "y": holder("y", address())},
    }

    assert fold(schema) == {
        "type": "object",
        "properties": {"x": holder("x", ref(1)), "y": holder("y", ref(1))},
        "$defs": {"shared1": address()},
    }


@pytest.mark.parametrize("shape", ["one", "listed", "named"])
@pytest.mark.parametrize("keyword", ["enum", "const", "default", "examples", "required", "x-shape"])
def test_what_a_keyword_holds_as_a_value_is_never_moved(keyword, shape):
    """`default: {...}` is a value someone may send, whatever it looks like."""

    def holder(title: str) -> dict:
        return {"title": title, keyword: held(shape, address())}

    values = {"x": holder("x"), "y": holder("y")}

    assert fold({"type": "object", "properties": values}) is None
    # Beside places where the same part is a schema, it is moved from those alone.
    assert fold(pair(**values)) == {
        "type": "object",
        "properties": {"from": ref(1), "to": ref(1), "x": holder("x"), "y": holder("y")},
        "$defs": {"shared1": address()},
    }


@pytest.mark.parametrize(
    "name",
    ["items", "properties", "default", "enum", "const", "examples", "required", "anyOf", "$defs"],
)
def test_a_parameter_named_like_a_keyword_is_a_parameter(name):
    schema = {"type": "object", "properties": {name: address(), "other": address()}}

    assert fold(schema) == {
        "type": "object",
        "properties": {name: ref(1), "other": ref(1)},
        "$defs": {"shared1": address()},
    }


@pytest.mark.parametrize("keyword", NAMED)
def test_a_map_of_names_is_never_moved_as_if_it_were_a_schema(keyword):
    """Two schemas with the same parameters hold the same map. Pointed to, the map would
    read as one parameter called `$ref`."""

    def names() -> dict:
        return {f"field{n}": {"type": "string"} for n in range(12)}

    schema = {
        "type": "object",
        "properties": {
            "x": {"type": "object", "title": "x", keyword: names()},
            "y": {"type": "object", "title": "y", keyword: names()},
        },
    }

    assert chars(names()) > 300 and fold(schema) is None


def test_what_a_parameter_named_properties_holds_is_a_schema_not_a_map_of_names():
    """Were the map it stands in read as a schema, its `default` and `const` would be
    read as the schemas of two parameters."""
    named = {"type": "object", "default": address(), "const": address()}

    assert fold({"type": "object", "properties": {"properties": named}}) is None


def test_a_keyword_that_holds_something_else_than_a_schema_is_left_as_it_is():
    odd = {
        "anyOf": "none",
        "items": True,
        "properties": ["street"],
        "not": [address()],
        "additionalProperties": False,
        "prefixItems": {"a": address()},
    }

    folded = fold(pair(odd=odd))

    assert folded == {
        "type": "object",
        "properties": {"from": ref(1), "to": ref(1), "odd": odd},
        "$defs": {"shared1": address()},
    }


def test_parts_are_named_in_the_order_they_first_stand():
    nested = {
        "type": "object",
        "title": "first",
        "properties": {"late": address("B"), "early": address("A")},
    }
    schema = {
        "type": "object",
        "properties": {
            "a": nested,
            "b": address("A"),
            "c": address("B"),
            "d": address("C"),
            "e": address("C"),
        },
    }

    folded = fold(schema)

    assert folded == {
        "type": "object",
        "properties": {
            "a": {**nested, "properties": {"late": ref(1), "early": ref(2)}},
            "b": ref(2),
            "c": ref(1),
            "d": ref(3),
            "e": ref(3),
        },
        "$defs": {"shared1": address("B"), "shared2": address("A"), "shared3": address("C")},
    }
    assert list(folded["$defs"]) == ["shared1", "shared2", "shared3"]


def test_a_part_moved_points_to_the_parts_moved_out_of_it():
    def route() -> dict:
        return {
            "type": "object",
            "description": "From one address to another.",
            "properties": {"start": address(), "end": address()},
        }

    schema = {"type": "object", "properties": {"out": route(), "back": route(), "home": address()}}

    folded = fold(schema)

    assert folded == {
        "type": "object",
        "properties": {"out": ref(1), "back": ref(1), "home": ref(2)},
        "$defs": {
            "shared1": {**route(), "properties": {"start": ref(2), "end": ref(2)}},
            "shared2": address(),
        },
    }
    assert text(unfolded(folded)) == text(schema)


def test_the_same_schema_always_folds_to_the_same_letters():
    schema = parameters()

    first = text(fold(schema))

    assert text(fold(schema)) == first
    assert text(fold(copy.deepcopy(schema))) == first
    assert text(fold(parameters())) == first


def test_parts_that_are_one_object_fold_as_parts_written_out_do():
    """A schema read off the wire holds each part anew; one made here may hold one object
    at every place."""
    part = address()
    schema = {"type": "object", "properties": {"from": part, "to": part}}

    assert fold(schema) == fold(json.loads(json.dumps(schema))) == fold(pair())


@pytest.mark.parametrize("uses", range(2, 7))
@pytest.mark.parametrize("letters", range(0, 70, 3))
def test_a_part_is_moved_only_where_that_makes_the_whole_shorter(uses, letters):
    """Held against the count of both ways of writing it, for parts from too short to be
    worth a pointer to long enough to be."""

    def part() -> dict:
        return {"type": "string", "description": "x" * letters}

    names = [f"p{n}" for n in range(uses)]
    schema = {"type": "object", "properties": {name: part() for name in names}}
    moved = {
        "type": "object",
        "properties": {name: ref(1) for name in names},
        "$defs": {"shared1": part()},
    }

    assert fold(schema) == (moved if chars(moved) < chars(schema) else None)


def test_the_short_parts_stay_written_out_beside_a_long_one_that_is_moved():
    def word() -> dict:
        return {"type": "string"}

    words = {f"w{n}": word() for n in range(30)}

    assert fold({"type": "object", "properties": words}) is None
    assert fold(pair(**words)) == {
        "type": "object",
        "properties": {"from": ref(1), "to": ref(1), **words},
        "$defs": {"shared1": address()},
    }


@pytest.mark.parametrize("letter", ["x", "ờ"])
@pytest.mark.parametrize("uses", range(2, 7))
@pytest.mark.parametrize("letters", range(40))
def test_beside_a_part_that_is_moved_another_is_moved_only_where_it_shortens(uses, letters, letter):
    """With `$defs` there already, one more part costs its name and its pointers and no
    more, so this is the count to the letter: a part that would leave the whole as long
    as it was stays where it is. Letters are counted as they are written, not as escapes."""

    def part() -> dict:
        return {"type": "string", "description": letter * letters}

    names = [f"p{n}" for n in range(uses)]
    left = {
        "type": "object",
        "properties": {"from": ref(1), "to": ref(1), **{name: part() for name in names}},
        "$defs": {"shared1": address()},
    }
    moved = {
        "type": "object",
        "properties": {"from": ref(1), "to": ref(1), **{name: ref(2) for name in names}},
        "$defs": {"shared1": address(), "shared2": part()},
    }

    folded = fold(pair(**{name: part() for name in names}))

    assert folded == (moved if chars(moved) < chars(left) else left)


@pytest.mark.parametrize("letters", range(12))
def test_a_part_is_weighed_by_what_is_left_of_it_once_its_own_parts_are_moved(letters):
    """An address inside a wrapper, and the wrapper twice. With the address pointed to,
    little is left of the wrapper to save by moving that too."""

    def wrapper(inside: dict) -> dict:
        return {"title": "x" * letters, "properties": {"at": inside}}

    schema = {
        "type": "object",
        "properties": {"out": wrapper(address()), "back": wrapper(address()), "home": address()},
    }
    left = {
        "type": "object",
        "properties": {"out": wrapper(ref(1)), "back": wrapper(ref(1)), "home": ref(1)},
        "$defs": {"shared1": address()},
    }
    moved = {
        "type": "object",
        "properties": {"out": ref(1), "back": ref(1), "home": ref(2)},
        "$defs": {"shared1": wrapper(ref(2)), "shared2": address()},
    }

    assert fold(schema) == (moved if chars(moved) < chars(left) else left)


@pytest.mark.parametrize("letters", range(26, 40))
def test_the_tenth_part_moved_is_weighed_with_the_longer_name_it_takes(letters):
    """`shared10` is a letter more than the nine before it, where it is said and at each
    place that points to it."""
    ends = [(f"{end}{n}", n) for n in range(1, 10) for end in ("from", "to")]
    tenth = {"type": "string", "description": "x" * letters}
    nine = {f"shared{n}": address(f"parcel {n}") for n in range(1, 10)}
    pointed = {name: ref(n) for name, n in ends}
    left = {"type": "object", "properties": {**pointed, "p": tenth, "q": tenth}, "$defs": nine}
    moved = {
        "type": "object",
        "properties": {**pointed, "p": ref(10), "q": ref(10)},
        "$defs": {**nine, "shared10": tenth},
    }

    folded = fold(
        {
            "type": "object",
            "properties": {
                **{name: address(f"parcel {n}") for name, n in ends},
                "p": dict(tenth),
                "q": dict(tenth),
            },
        }
    )

    assert folded == (moved if chars(moved) < chars(left) else left)


@pytest.mark.parametrize("letters", range(26, 40))
def test_a_part_is_weighed_with_the_longer_name_the_sources_own_names_leave_it(letters):
    """The source has `shared1` to `shared9` of its own, so the address moved beside the
    part is `shared10` and the part, where it is worth moving, `shared11`."""
    own = {f"shared{n}": {"type": "integer"} for n in range(1, 10)}
    part = {"type": "string", "description": "x" * letters}
    ends = {"from": ref(10), "to": ref(10)}
    left = {
        "type": "object",
        "$defs": {**own, "shared10": address()},
        "properties": {**ends, "p": part, "q": part},
    }
    moved = {
        "type": "object",
        "$defs": {**own, "shared10": address(), "shared11": part},
        "properties": {**ends, "p": ref(11), "q": ref(11)},
    }

    folded = fold({"type": "object", "$defs": own, **pair(p=dict(part), q=dict(part))})

    assert folded == (moved if chars(moved) < chars(left) else left)


def test_a_part_that_stands_once_in_a_part_moved_is_written_out_in_it():
    """It stands at three places in the source, and at one once what holds it is said once."""

    def stop() -> dict:
        return {"type": "object", "title": "A stop on the way.", "properties": {"at": address()}}

    schema = {"type": "object", "properties": {"a": stop(), "b": stop(), "c": stop()}}

    assert fold(schema) == {
        "type": "object",
        "properties": {"a": ref(1), "b": ref(1), "c": ref(1)},
        "$defs": {"shared1": stop()},
    }


def test_a_schema_with_nothing_said_twice_is_not_folded():
    schema = {"type": "object", "properties": {"a": address("A"), "b": address("B")}}

    assert fold(schema) is None
    assert fold({"type": "object", "properties": {}}) is None


def test_a_part_moved_takes_no_name_the_source_has_or_points_to():
    own = {"type": "string", "description": "The source's own."}
    schema = {
        "type": "object",
        "$defs": {"shared1": own, "shared3": address()},
        "properties": {
            "own": {"$ref": "#/$defs/shared1"},
            "old": {"$ref": "#/definitions/shared2"},
            "from": address(),
            "to": address(),
            "a": address("A"),
            "b": address("A"),
        },
        "definitions": {"shared2": {"type": "integer"}},
    }

    folded = fold(schema)

    assert folded == {
        "type": "object",
        # What the source defined is where it was, and one that says what a moved part
        # says points to it like any other place.
        "$defs": {
            "shared1": own,
            "shared3": ref(4),
            "shared4": address(),
            "shared5": address("A"),
        },
        "properties": {
            "own": {"$ref": "#/$defs/shared1"},
            "old": {"$ref": "#/definitions/shared2"},
            "from": ref(4),
            "to": ref(4),
            "a": ref(5),
            "b": ref(5),
        },
        "definitions": {"shared2": {"type": "integer"}},
    }
    assert list(folded) == ["type", "$defs", "properties", "definitions"]
    assert list(folded["$defs"]) == ["shared1", "shared3", "shared4", "shared5"]
    assert text(unfolded(folded, ["shared4", "shared5"])) == text(schema)


def test_a_pointer_to_nothing_is_not_given_something_to_point_to():
    """The source points at a definition it does not have. A part moved under that name
    would make the pointer mean something."""
    schema = pair(ghost={"$ref": "#/$defs/shared1"})

    assert fold(schema) == {
        "type": "object",
        "properties": {"from": ref(2), "to": ref(2), "ghost": {"$ref": "#/$defs/shared1"}},
        "$defs": {"shared2": address()},
    }


@pytest.mark.parametrize(
    "pointer", ["#/$defs/a", "#/definitions/a", "#/$defs/tên có dấu", "#/$defs/a.b-c_d"]
)
def test_a_pointer_to_one_of_its_own_definitions_is_left_as_it_is(pointer):
    schema = pair(old={"$ref": pointer})

    assert fold(schema) == {
        "type": "object",
        "properties": {"from": ref(1), "to": ref(1), "old": {"$ref": pointer}},
        "$defs": {"shared1": address()},
    }


@pytest.mark.parametrize(
    "pointer",
    [
        "#",
        "",
        "#/properties/from",
        "#/$defs/a/properties/b",
        "#/$defs/",
        "#/$DEFS/a",
        "#/$defs/a%20b",
        "#/$defs/a~1b",
        "#/$defs/a#b",
        "other.json#/$defs/a",
        "https://example.test/schema",
        7,
        None,
        ["#/$defs/a"],
    ],
)
def test_a_schema_that_points_anywhere_else_is_not_folded(pointer):
    assert fold(pair()) is not None
    assert fold(pair(old={"$ref": pointer})) is None


@pytest.mark.parametrize(
    "keyword",
    ["$id", "$anchor", "$dynamicRef", "$dynamicAnchor", "$recursiveRef", "$recursiveAnchor"],
)
def test_a_schema_that_names_itself_is_not_folded(keyword):
    named = "https://example.test/schema"
    inside = pair()
    inside["properties"]["from"]["properties"]["street"][keyword] = named
    inside["properties"]["to"]["properties"]["street"][keyword] = named

    assert fold({**pair(), keyword: named}) is None
    assert fold(pair(other={"type": "string", keyword: named})) is None
    assert fold(inside) is None
    # Judged by the letters alone: a value that holds the word, and a parameter called it.
    assert fold(pair(other={"type": "object", "default": {keyword: named}})) is None
    assert fold(pair(**{keyword: {"type": "string"}})) is None


@pytest.mark.parametrize("defs", [["x"], "x", 7, None])
def test_a_schema_whose_definitions_are_not_a_map_is_not_folded(defs):
    assert fold({**pair(), "$defs": defs}) is None


def test_a_schema_longer_than_is_read_is_not_folded():
    """The limit is on the source: these repeat enough to fold to a few thousand letters."""
    many = parameters(places=tuple(f"place{n}" for n in range(26)))

    at = fold(padded(many, MAX_FOLD_CHARS))

    assert at is not None and chars(at) < 50_000
    assert fold(padded(many, MAX_FOLD_CHARS + 1)) is None


def test_a_schema_nested_deeper_than_can_be_walked_is_not_folded():
    def deep() -> dict:
        schema = inner = {"type": "object"}
        for _ in range(1500):
            inner["properties"] = {"a": {"type": "object"}}
            inner = inner["properties"]["a"]
        return schema

    schema = {"type": "object", "properties": {"x": deep(), "y": deep()}}

    assert chars(schema) > 50_000
    assert fold(schema) is None


def test_a_fold_that_does_not_give_the_source_back_is_not_used(monkeypatch):
    """Each fold is opened out again and held to its source before it is handed on. Here
    the reading slips, and takes two parts that differ by one word for the same part."""
    other = address("a letter")
    schema = pair(other=other)

    class Slipping(Reading):
        def read(self, node):
            alike = node == other["description"]
            return super().read(address()["description"] if alike else node)

    assert fold(schema) == {
        "type": "object",
        "properties": {"from": ref(1), "to": ref(1), "other": other},
        "$defs": {"shared1": address()},
    }
    monkeypatch.setattr(schema_fold, "Reading", Slipping)
    assert fold(schema) is None


def test_parameters_written_out_at_every_place_fold_to_a_fraction_and_back():
    schema = parameters()

    folded = fold(schema)

    assert chars(schema) > 50_000 and chars(folded) < 10_000
    assert text(unfolded(folded)) == text(schema)
    # Each part is said once, and a part moved out of another is pointed to from it.
    assert text(folded).count(moment()["description"]) == 1
    assert any('"$ref"' in text(said) for said in folded["$defs"].values())
