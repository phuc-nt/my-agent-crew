"""What a script can say, and that it means what the same lines mean in Python
(`my_agent_crew/script/`): the interpreter alone, no process and no tools but a test's own."""

from __future__ import annotations

import contextlib
import io
import json
from textwrap import dedent

import pytest

from tests.script_helpers import play, printed

# Each is a script and what it prints. Python itself is asked for the same answer below, so
# a line of this table is never only what the interpreter happens to do.
AS_IN_PYTHON = {
    "arithmetic": (
        """
        print(1 + 2 * 3, 7 // 2, 7 % 3, 7 / 2, -7 // 2, 2 - 5, 10 / 4, 1e3)
        print(5 | 2, 6 & 3, 6 ^ 3, not 0, -(-3), +4, 0.1 + 0.2)
        print(round(3.14159, 2), round(2.5), abs(-4), abs(-2.5), 1 / 3)
        """,
        "7 3 1 3.5 -4 -3 2.5 1000.0\n"
        "7 2 5 True 3 4 0.30000000000000004\n"
        "3.14 2 4 2.5 0.3333333333333333\n",
    ),
    "texts": (
        """
        s = "Hello, World"
        print(s.lower(), s.upper(), len(s), s[0], s[-1], s[1:4], s[::-1])
        print("a,b,c".split(","), "-".join(["x", "y"]), " pad ".strip(), "aXbXc".replace("X", "-"))
        print("abc".startswith("ab"), "abc".endswith("bc"), "abc".find("c"), "abc".count("b"))
        print("x" in "xyz", "q" not in "xyz", "ab" + "cd", "ab" * 3, 2 * "-")
        print("one\\ntwo".splitlines(), "k=v".partition("="), "pre_name".removeprefix("pre_"))
        print("12".isdigit(), "Tên".title(), " A,b ".strip().lower().split(","))
        """,
        "hello, world HELLO, WORLD 12 H d ell dlroW ,olleH\n"
        "['a', 'b', 'c'] x-y pad a-b-c\n"
        "True True 2 1\n"
        "True True abcd ababab --\n"
        "['one', 'two'] ('k', '=', 'v') name\n"
        "True Tên ['a', 'b']\n",
    ),
    "f-strings": (
        """
        name, n, price = "An", 3, 1234.5
        print(f"{name} has {n} items: {price:.2f} {price:,.1f} {n:03d} {name!r}")
        print(f"{name:>5}|{name:<5}|{name:^6}|{n:5}|{0.256:.1%}|{n + 1}|{price:+.1f}")
        print(f"{[1, 2]} {{'k': 'v'}} {None} {True} {name!s:>4} {n:{n}}")
        """,
        "An has 3 items: 1234.50 1,234.5 003 'An'\n"
        "   An|An   |  An  |    3|25.6%|4|+1234.5\n"
        "[1, 2] {'k': 'v'} None True   An   3\n",
    ),
    "lists": (
        """
        xs = [3, 1, 2]
        xs.append(5)
        xs.extend([7, 8])
        xs.insert(0, 9)
        last = xs.pop()
        print(xs, last, len(xs), xs.index(1), 2 in xs, 4 not in xs)
        xs.sort()
        print(xs, xs[1:3], xs[-1], xs[::2], xs[:2], xs[4:], sum(xs), min(xs), max(xs))
        xs.reverse()
        xs.remove(5)
        print(xs, xs.count(9), [0] * 3, [1] + [2], xs.copy() == xs, [*xs, 0][-1])
        xs[0] = "nine"
        xs.clear()
        print(xs, list(range(3)), list(range(2, 8, 3)), list(range(3, 0, -1)), range(10)[2:5])
        """,
        "[9, 3, 1, 2, 5, 7] 8 6 2 True True\n"
        "[1, 2, 3, 5, 7, 9] [2, 3] 9 [1, 3, 7] [1, 2] [7, 9] 27 1 9\n"
        "[9, 7, 3, 2, 1] 1 [0, 0, 0] [1, 2] True 0\n"
        "[] [0, 1, 2] [2, 5] [3, 2, 1] range(2, 5)\n",
    ),
    "dicts": (
        """
        d = {"a": 1, "b": 2}
        d["c"] = 3
        d.update({"d": 4})
        print(d, d["a"], d.get("z"), d.get("z", 0), "a" in d, "z" not in d, len(d))
        print(list(d.keys()), list(d.values()), list(d.items()))
        merged = {**d, "a": 10, **{"e": 5}}
        print(merged, d.pop("b"), d.setdefault("x", []), d.setdefault("a", 0), d)
        for key, value in d.items():
            print(key, value, end=";")
        print()
        print({k: v * 2 for k, v in d.items() if v}, dict(b=2), dict([("k", 1)]), d.copy() == d)
        """,
        "{'a': 1, 'b': 2, 'c': 3, 'd': 4} 1 None 0 True True 4\n"
        "['a', 'b', 'c', 'd'] [1, 2, 3, 4] [('a', 1), ('b', 2), ('c', 3), ('d', 4)]\n"
        "{'a': 10, 'b': 2, 'c': 3, 'd': 4, 'e': 5} 2 [] 1 {'a': 1, 'c': 3, 'd': 4, 'x': []}\n"
        "a 1;c 3;d 4;x [];\n"
        "{'a': 2, 'c': 6, 'd': 8} {'b': 2} {'k': 1} True\n",
    ),
    "sets and tuples": (
        """
        s = {1, 2, 2, 3}
        s.add(4)
        s.discard(1)
        print(sorted(s), len(s), 2 in s, sorted(s | {9}), sorted(s & {2, 3}), sorted(s ^ {2, 8}))
        print(sorted(s.union([7])), sorted(s.difference({2})), sorted(s.intersection({4, 5})))
        t = (1, "a", 2.5)
        a, b, c = t
        print(t, t[1], len(t), a, b, c, t + (4,), t.index("a"), (1, 2) < (1, 3), ())
        """,
        "[2, 3, 4] 3 True [2, 3, 4, 9] [2, 3] [3, 4, 8]\n"
        "[2, 3, 4, 7] [3, 4] [4]\n"
        "(1, 'a', 2.5) a 3 1 a 2.5 (1, 'a', 2.5, 4) 1 True ()\n",
    ),
    "comprehensions": (
        """
        x = "outer"
        print([x * x for x in range(5) if x % 2 == 0], x)
        print([(x, y) for x in range(2) for y in "ab"])
        print({w: len(w) for w in ["a", "bb"]}, sorted({n % 3 for n in range(10)}))
        print(sum(n for n in range(4)), any(n > 2 for n in range(4)), all(n > 2 for n in range(4)))
        print(", ".join(str(n) for n in [1, 2, 3]), max(len(w) for w in ["a", "bcd"]))
        print([n for row in [[1, 2], [3]] for n in row if n != 2], [[0] * 2 for _ in range(2)])
        """,
        "[0, 4, 16] outer\n"
        "[(0, 'a'), (0, 'b'), (1, 'a'), (1, 'b')]\n"
        "{'a': 1, 'bb': 2} [0, 1, 2]\n"
        "6 True False\n"
        "1, 2, 3 3\n"
        "[1, 3] [[0, 0], [0, 0]]\n",
    ),
    "functions": (
        """
        def area(w: int, h: int = 2) -> int:
            return w * h

        def fact(n):
            return 1 if n <= 1 else n * fact(n - 1)

        def counter():
            seen = []

            def add(item):
                seen.append(item)
                return len(seen)

            return add

        def nothing():
            pass

        def early(xs):
            for x in xs:
                if x > 1:
                    return x

        def grow(xs):
            xs += [9]

        add = counter()
        add("a")
        held = [1]
        grow(held)
        print(area(3), area(3, 4), area(h=5, w=2), area(*[2, 3]), area(**{"w": 4}), fact(10))
        print(add("b"), nothing(), early([0, 1, 5, 9]), early([]), held)
        double = lambda value: value * 2
        print(double(4), (lambda a, b=1: a + b)(1), [double(n) for n in (1, 2)])
        """,
        "6 12 10 6 8 3628800\n2 None 5 None [1, 9]\n8 2 [2, 4]\n",
    ),
    "sorting and picking": (
        """
        rows = [{"n": "b", "v": 2}, {"n": "a", "v": 2}, {"n": "c", "v": 1}]
        print([r["n"] for r in sorted(rows, key=lambda r: r["v"])])
        print([r["n"] for r in sorted(rows, key=lambda r: r["v"], reverse=True)])
        print(max(rows, key=lambda r: r["v"])["n"], min(rows, key=lambda r: r["v"])["n"])
        print(min([], default=0), max(3, 9, 4), min("b", "a"), sorted("cab"))
        print(sorted([3, 1, 2], reverse=True), sorted({"b": 1, "a": 2}), sorted((2, 1)))
        rows.sort(key=lambda r: r["n"])
        print([r["n"] for r in rows])
        """,
        "['c', 'b', 'a']\n['b', 'a', 'c']\nb c\n0 9 a ['a', 'b', 'c']\n"
        "[3, 2, 1] ['a', 'b'] [1, 2]\n['a', 'b', 'c']\n",
    ),
    "loops": (
        """
        total = 0
        for i in range(10):
            if i == 7:
                break
            if i % 2:
                continue
            total += i
        else:
            total = -1
        print(total)
        for i in range(3):
            pass
        else:
            print("done", i)
        n = 0
        while n < 5:
            n += 1
            if n == 3:
                continue
        else:
            print("ended", n)
        while True:
            n -= 1
            if n < 2:
                break
        print(n)
        for i, (a, b) in enumerate(zip("ab", [1, 2]), 1):
            print(i, a, b)
        for x in reversed([1, 2, 3]):
            print(x, end=" ")
        print(*[1, 2, 3], sep="-")
        """,
        "12\ndone 2\nended 5\n1\n1 a 1\n2 b 2\n3 2 1 1-2-3\n",
    ),
    "logic": (
        """
        def boom():
            return 1 / 0

        a, b = 0, "x"
        print(a or b, a and b, b or a, not a, 1 < 2 < 3, 1 < 2 > 5, None is None, a is not None)
        print("big" if a > 1 else "small", True or boom(), False and boom(), a == 0 != b)
        """,
        "x 0 x True True False True True\nsmall True False True\n",
    ),
    "names": (
        """
        a, b = 1, 2
        a, b = b, a
        [c, d] = "xy"
        x = y = 5
        n: int = 1
        n += 2
        n *= 3
        n -= 1
        n //= 2
        n %= 3
        table = {"k": 1}
        table["k"] += 4
        xs = [1]
        xs += [2]
        xs[0] += 10
        s = "a"
        s += "b"
        print(a, b, c, d, x, y, n, table, xs, s)
        """,
        "2 1 x y 5 5 1 {'k': 5} [11, 2] ab\n",
    ),
    "json": (
        """
        import json

        text = '{"items": [{"id": 1, "tags": ["a"]}, {"id": 2, "tags": []}], "next": null}'
        data = json.loads(text)
        print(len(data["items"]), data["next"], [i["id"] for i in data["items"] if i["tags"]])
        print(json.dumps({"b": [1, 2.5, None, True], "a": "x"}, sort_keys=True))
        print(json.dumps({"a": [1, {"b": 2}]}, indent=2))
        """,
        '2 None [1]\n{"a": "x", "b": [1, 2.5, null, true]}\n'
        '{\n  "a": [\n    1,\n    {\n      "b": 2\n    }\n  ]\n}\n',
    ),
    "kinds": (
        """
        print(isinstance(1, int), isinstance("a", str), isinstance(1.5, (int, float)))
        print(isinstance([], list), isinstance({}, dict), isinstance(None, str))
        print(isinstance((1,), tuple), isinstance(True, int), isinstance(1, bool))
        print(isinstance(True, bool), isinstance({1}, set), isinstance("a", (int, list)))
        print(int("42") + 1, int(3.9), float("2.5") * 2, str(12) + "!", bool(""), bool("x"))
        print(list("ab"), tuple([1, 2]), sorted(set([2, 1, 2])), repr("q"), str(None), str())
        """,
        "True True True\nTrue True False\nTrue True False\nTrue True False\n"
        "43 3 5.0 12! False True\n"
        "['a', 'b'] (1, 2) [1, 2] 'q' None \n",
    ),
    "errors caught by name": (
        """
        import json

        def attempt(fail):
            out = []
            try:
                out.append("try")
                if fail:
                    raise ValueError("bad")
            except ValueError:
                out.append("except")
            else:
                out.append("else")
            finally:
                out.append("finally")
            return out

        def leaves():
            try:
                return "from try"
            finally:
                print("cleanup")

        risks = [lambda: {}["k"], lambda: [1][5], lambda: int("x"), lambda: 1 / 0]
        for risky in [*risks, lambda: "a" + 1]:
            try:
                risky()
            except (KeyError, IndexError):
                print("lookup")
            except ValueError:
                print("value")
            except ZeroDivisionError:
                print("zero")
            except TypeError:
                print("type")
        try:
            json.loads("{")
        except json.JSONDecodeError:
            print("not json")
        try:
            assert 1 > 2, "math holds"
        except AssertionError:
            print("assertion")
        try:
            {}["k"]
        except LookupError:
            print("a KeyError is a LookupError")
        print(attempt(False), attempt(True), leaves())
        for i in range(3):
            try:
                if i == 1:
                    continue
                print(i)
            finally:
                print("after", i)
        """,
        "lookup\nlookup\nvalue\nzero\ntype\nnot json\nassertion\na KeyError is a LookupError\n"
        "cleanup\n['try', 'else', 'finally'] ['try', 'except', 'finally'] from try\n"
        "0\nafter 0\nafter 1\n2\nafter 2\n",
    ),
    "a table worked through": (
        """
        rows = [("tea", 3, 1.5), ("rice", 1, 20.0), ("tea", 2, 1.5), ("salt", 4, 0.5)]
        totals = {}
        for name, count, price in rows:
            totals[name] = totals.get(name, 0) + count * price
        ranked = sorted(totals.items(), key=lambda pair: -pair[1])
        for name, total in ranked[:2]:
            print(f"{name:<5}{total:>8.2f}")
        print(len(ranked), sum(total for _, total in ranked))
        """,
        "rice    20.00\ntea      7.50\n3 29.5\n",
    ),
    "comparisons at their edges": (
        "print(1 <= 1, 1 >= 1, 2 <= 1, 1 >= 2, 1 < 3 < 2, 3 > 2 > 1, 1 < 2 <= 2)",
        "True True False False False True True\n",
    ),
    "a name changed in place": (
        """
        x = 7
        x /= 2
        y = 7
        y %= 4
        a = {1}
        a |= {2}
        b = {1, 2}
        b &= {2}
        c = {1, 2}
        c ^= {2, 3}
        print(x, y, sorted(a), b, sorted(c))
        """,
        "3.5 3 [1, 2] {2} [1, 3]\n",
    ),
    "a name of Python's given a value of the script's": (
        """
        len = 3
        print(len)
        def sum(items):
            return "mine"
        print(sum([1, 2]))
        """,
        "3\nmine\n",
    ),
    "defaults taken by place": (
        """
        def f(a, b=1, c=2):
            return [a, b, c]
        print(f(0), f(0, 5), f(0, c=9), f(0, 5, 6))
        """,
        "[0, 1, 2] [0, 5, 2] [0, 1, 9] [0, 5, 6]\n",
    ),
    "a spread in every display": (
        'print((*[1, 2], 3), {*[1, 2]}, [*(1, 2), *"ab"])',
        "(1, 2, 3) {1, 2} [1, 2, 'a', 'b']\n",
    ),
    "what a helper takes by name": (
        """
        print(sum([1, 2], 10), sum([1, 2], start=10), list(enumerate(["a", "b"], start=1)))
        print(list(zip([1, 2, 3], "ab")), (1, 2, 1).count(1), "a.b.c".rpartition("."))
        """,
        "13 13 [(1, 'a'), (2, 'b')]\n[(1, 'a'), (2, 'b')] 2 ('a.b', '.', 'c')\n",
    ),
    "a hint is read and nothing more": (
        """
        x: int
        y: int = 2
        def double(n: int) -> int:
            return n * 2
        print(double(y))
        """,
        "4\n",
    ),
    "errors caught by their kin": (
        """
        try:
            [1][5]
        except LookupError:
            print("lookup")
        try:
            int(float("inf"))
        except ArithmeticError:
            print("arithmetic")
        try:
            raise AttributeError("gone")
        except TypeError:
            print("type")
        except AttributeError:
            print("attribute")
        try:
            raise ValueError
        except ValueError:
            print("value")
        try:
            {}["k"]
        except BaseException:
            print("anything")
        """,
        "lookup\narithmetic\nattribute\nvalue\nanything\n",
    ),
    "a while left by break skips its else": (
        """
        n = 0
        while n < 5:
            n += 1
            if n == 3:
                break
        else:
            print("never")
        print("left at", n)
        """,
        "left at 3\n",
    ),
}

# Where a script is deliberately not Python: nothing lazy, nothing that is not plain data.
OWN_WAYS = {
    "the last line's value is shown, as a prompt would": ("x = 20\nx + 1", "21\n"),
    "a text is shown as it is": ('"Phở " + "bò"', "Phở bò\n"),
    "data is shown as JSON": (
        '{"a": [1, None, True, 2.5], "b": ("x", "é")}',
        '{"a": [1, null, true, 2.5], "b": ["x", "é"]}\n',
    ),
    "what JSON cannot write is shown as Python writes it": ("{1, 2}", "{1, 2}\n"),
    "None on the last line shows nothing": ("x = None\nx", ""),
    "a print on the last line prints once": ('print("a")', "a\n"),
    "a print told to flush prints as any other": ('print("a", "b", flush=True)', "a b\n"),
    "a function is shown by its name": (
        "def f():\n    pass\nprint(f, len, lambda: 1)",
        "<function f> <function len> <function lambda>\n",
    ),
    "keys, values and items are lists": (
        'd = {"a": 1}\nprint(d.keys(), d.values(), d.items(), d.keys()[0])',
        "['a'] [1] [('a', 1)] a\n",
    ),
    "what Python hands out lazily is a list": (
        'print(zip("ab", [1, 2]), enumerate(["x"]), reversed([1, 2]), (n for n in [1]))',
        "[('a', 1), ('b', 2)] [(0, 'x')] [2, 1] [1]\n",
    ),
    "a dict changed while it is walked is walked as it was": (
        'd = {"a": 1, "b": 2}\nfor key in d:\n    d[key + key] = 0\nprint(sorted(d))',
        "['a', 'aa', 'b', 'bb']\n",
    ),
    "a set changed while it is walked is walked as it was": (
        "s = {1, 2}\nfor item in s:\n    s.add(item + 10)\nprint(sorted(s))",
        "[1, 2, 11, 12]\n",
    ),
    "an error an except names is its text": (
        'try:\n    {}["k"]\nexcept KeyError as e:\n    print(e, isinstance(e, str), e.upper())',
        "KeyError: 'k' True KEYERROR: 'K'\n",
    ),
    "json keeps letters that are not ASCII": (
        'print(json.dumps({"tên": "Phở"}), json.dumps("é", ensure_ascii=True))',
        '{"tên": "Phở"} "\\u00e9"\n',
    ),
    "json writes what it cannot as text when a default is named": (
        'print(json.dumps({"s": (1, 2), "t": {3}}, default=len))',
        '{"s": [1, 2], "t": "{3}"}\n',
    ),
    "an indent wider than eight is not used": ("print(json.dumps([1, 2], indent=50))", "[1, 2]\n"),
    "json is there without an import": ('print(json.loads("[1, 2]")[1])', "2\n"),
    "a name the script binds itself is its own": (
        'tools = {"a": 1}\njson = "text"\nprint(tools.get("a"), json.upper(), tools)',
        "1 TEXT {'a': 1}\n",
    ),
    "a comprehension keeps its names to itself": (
        "ys = [n for n in range(3)]\ntry:\n    n\nexcept Exception as e:\n    print(e)",
        "chưa có tên `n`.\n",
    ),
    "a hint is never worked out, whatever it names": (
        "def f(x: a.b) -> a.b:\n    return x\ny: a.b = f(1)\nprint(y)",
        "1\n",
    ),
    "zero on the last line is a value like any other": ("x = 0\nx", "0\n"),
    "an indent is a whole number up to eight": (
        "print(json.dumps([1], indent=8))\n"
        "for odd in (9, True, -1):\n"
        "    print(json.dumps([1], indent=odd))",
        "[\n        1\n]\n[1]\n[1]\n[1]\n",
    ),
}


def python_prints(source: str) -> str:
    """What Python itself prints for the same lines."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(dedent(source), "<script>", "exec"), {"json": json})
    return out.getvalue()


@pytest.mark.parametrize("name", AS_IN_PYTHON)
def test_a_script_prints_what_the_same_lines_print_in_python(name):
    source, expected = AS_IN_PYTHON[name]

    assert printed(source) == expected
    assert python_prints(source) == expected


@pytest.mark.parametrize("name", OWN_WAYS)
def test_where_a_script_is_not_python_it_is_so_in_one_known_way(name):
    source, expected = OWN_WAYS[name]

    assert printed(source) == expected


def test_a_tool_is_called_by_name_and_its_text_is_what_the_call_is_worth():
    ended = play(
        """
        first = tools.read(path="a.txt")
        second = tools.read({"path": "b.txt"})
        print(first.upper(), len(second), tools.now())
        """,
        {"read": lambda arguments: f"read {arguments['path']}", "now": lambda arguments: "noon"},
    )

    assert (ended["ok"], ended["output"], ended["error"]) == (True, "READ A.TXT 10 noon\n", None)
    assert ended["asked"] == [("read", {"path": "a.txt"}), ("read", {"path": "b.txt"}), ("now", {})]


def test_a_tool_is_handed_what_json_can_carry():
    """The same in a test as over the pipe to the process a script runs in."""
    ended = play(
        'tools.find(ids=(1, 2), names={1: "a"}, deep=[{"k": (None, True)}], text="é")',
        {"find": lambda arguments: "found"},
    )

    assert ended["asked"] == [
        ("find", {"ids": [1, 2], "names": {"1": "a"}, "deep": [{"k": [None, True]}], "text": "é"})
    ]
    assert ended["output"] == "found\n"  # the call was the last line, so its text is shown


def test_an_answer_that_is_json_is_worked_on_as_data():
    pages = json.dumps({"results": [{"title": "Kế hoạch", "words": 120}, {"title": "Nháp"}]})

    said = printed(
        """
        pages = json.loads(tools.search(query="kế hoạch"))["results"]
        print([page["title"] for page in pages if page.get("words", 0) > 100])
        """,
        {"search": lambda arguments: pages},
    )

    assert said == "['Kế hoạch']\n"


def test_an_empty_script_does_nothing_and_says_nothing():
    for source in ("", "\n\n", "# only a note\n", "pass"):
        assert play(source) == {"ok": True, "output": "", "error": None, "asked": []}
