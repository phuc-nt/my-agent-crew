"""What a script may not write, and how it ends when it goes wrong (`my_agent_crew/script/`):
refused whole before a line runs, stopped at the line that failed, or caught by its own `try`."""

from __future__ import annotations

import warnings

import pytest

from my_agent_crew import texts_script as t
from my_agent_crew.script import statements
from my_agent_crew.script.limits import Halt, ScriptError
from tests.script_helpers import play, printed, stopped

NO_ATTRIBUTE = (
    "`.{name}` không đọc được: script chỉ gọi phương thức (`x.{name}(...)`), không đọc thuộc tính."
)
NO_PARAMS = "*, / hay ** trong tham số của hàm"
NO_JSON = "json chỉ có `loads` và `dumps`."
ONLY_KINDS = "isinstance chỉ nhận str, int, float, bool, list, dict, set, tuple."

# A script, the line it is refused at, and what that line is told it may not use.
NOT_IN_THE_LANGUAGE = [
    ("import os", 1, "import os"),
    ("import json as j", 1, "import json as j"),
    ("import json, sys", 1, "import sys"),
    ("from os import path", 1, "from ... import"),
    ("class Page:\n    pass", 1, "class"),
    ('with open("f") as held:\n    pass', 1, "with"),
    ("x = 1\ndel x", 2, "del"),
    ("def f():\n    global x", 2, "global"),
    ("def f():\n    nonlocal x", 2, "nonlocal"),
    ("2 ** 10", 1, "**"),
    ("x = 2\nx **= 3", 2, "**"),
    ("1 << 200", 1, "<<"),
    ("8 >> 1", 1, ">>"),
    ("~5", 1, "~"),
    ("[1] @ [2]", 1, "@"),
    ("if (n := 5):\n    pass", 1, ":="),
    ("@cache\ndef f():\n    pass", 1, "@decorator"),
    ("def f(*args):\n    pass", 1, NO_PARAMS),
    ("def f(**named):\n    pass", 1, NO_PARAMS),
    ("def f(a, /):\n    pass", 1, NO_PARAMS),
    ("def f(*, a):\n    pass", 1, NO_PARAMS),
    ("f = lambda *args: args", 1, NO_PARAMS),
    ("first, *rest = [1, 2, 3]", 1, "*"),
    ("for a, *b in [[1, 2]]:\n    pass", 1, "*"),
    ("xs = [1]\ny = *xs", 2, "*"),
    ("async def f():\n    pass", 1, "async def"),
    ("def f():\n    yield 1", 2, "yield"),
    ("def f():\n    yield from [1]", 2, "yield from"),
    ("await later", 1, "await"),
    ("[x async for x in rows]", 1, "async for"),
    ("match 5:\n    case 5:\n        pass", 1, "match"),
    ("try:\n    pass\nexcept* ValueError:\n    pass", 1, "except*"),
    ('data = b"raw"', 1, "bytes"),
    ("z = 1j", 1, "complex"),
    ("x = ...", 1, "ellipsis"),
    # The first thing written on the earliest line is the one told of.
    ("x = 1\ndel x.real", 2, "del"),
    ("@tools.cached\nclass Page:\n    pass", 1, "class"),
    ("@tools.cached\ndef f(*args):\n    pass", 1, "@decorator"),
    ("y = 2 ** [].real", 1, "**"),
    ('print("fine")\nimport os\nclass Late:\n    pass', 2, "import os"),
    ("async for x in []:\n    pass", 1, "async for"),
    ("async with a as b:\n    pass", 1, "async with"),
]

# An attribute read or set, by the line and the name of it: the one way out of plain data.
ATTRIBUTES = [
    ("x = 5\nx.real", 2, "real"),
    ("print([].__class__)", 1, "__class__"),
    ('join = "".join', 1, "join"),
    ("f = len.__self__", 1, "__self__"),
    ("x = {}\nx.field = 1", 2, "field"),
    ("x = {}\nx.count += 1", 2, "count"),
    ("for row.item in [1]:\n    pass", 1, "item"),
    ('"{0.__class__}".format.__globals__', 1, "__globals__"),
    ("y = 1 if [].real else 2 ** 3", 1, "real"),
    ("raise json.JSONDecodeError", 1, "JSONDecodeError"),
    # Of two, the one on the earlier line is told, whichever a reader of the tree meets first.
    ("d = {1: a.x,\n     b.y: 2}", 1, "x"),
]

# What Python itself turns away, in Python's words.
BAD_SYNTAX = [
    ("x = (1", 1, "'(' was never closed"),
    ("print('a')\nbreak", 2, "'break' outside loop"),
    ("x = 1\n\nreturn x", 3, "'return' outside function"),
    ("continue", 1, "'continue' not properly in loop"),
    ("def f():\n    pass\n  x = 1", 3, "unindent does not match any outer indentation level"),
    ("x = = 2", 1, "invalid syntax"),
    ("f(a=1, a=2)", 1, "keyword argument repeated: a"),
    ("def f(a, a):\n    pass", 1, "duplicate argument 'a' in function definition"),
]

# A name a script might reach for and that is simply not there.
NOT_THERE = (
    "getattr setattr hasattr delattr eval exec compile open input type object super vars dir "
    "globals locals __import__ __builtins__ breakpoint memoryview bytes bytearray classmethod "
    "property staticmethod id hash iter next map filter chr ord pow divmod format callable "
    "frozenset slice help exit quit os sys Exception ValueError"
).split()

# A script that fails as it runs, the line it fails at, and the words it is told.
MISTAKES = [
    ("x = tools", 1, "`tools` chỉ dùng để gọi: `tools.TEN(...)`."),
    ("print(json)", 1, "`json` chỉ dùng để gọi: `json.TEN(...)`."),
    ('"{}".format(1)', 1, "str không có phương thức `format` trong script."),
    ('"a".encode()', 1, "str không có phương thức `encode` trong script."),
    ("[].__class__()", 1, "list không có phương thức `__class__` trong script."),
    ("(1).bit_length()", 1, "int không có phương thức `bit_length` trong script."),
    ("(1.5).is_integer()", 1, "float không có phương thức `is_integer` trong script."),
    ("len.call()", 1, "function không có phương thức `call` trong script."),
    ("def f():\n    pass\nf.env()", 3, "function không có phương thức `env` trong script."),
    ("(lambda: 1).__call__()", 1, "function không có phương thức `__call__` trong script."),
    ("None.strip()", 1, "None không có phương thức `strip` trong script."),
    ("{}.fromkeys([1])", 1, "dict không có phương thức `fromkeys` trong script."),
    ("(1, 2).append(3)", 1, "tuple không có phương thức `append` trong script."),
    ("True.real()", 1, "bool không có phương thức `real` trong script."),
    ('"%s" % 5', 1, "không định dạng chuỗi bằng `%`: dùng f-string."),
    ('f"{1:>9999}"', 1, "định dạng `>9999` trong f-string không được hỗ trợ."),
    ('f"{1:.300f}"', 1, "định dạng `.300f` trong f-string không được hỗ trợ."),
    ('f"{5:x}"', 1, "định dạng `x` trong f-string không được hỗ trợ."),
    ("5()", 1, "int không phải hàm, không gọi được."),
    ("x = None\nx()", 2, "None không phải hàm, không gọi được."),
    ('"text"(1)', 1, "str không phải hàm, không gọi được."),
    ("{**5}", 1, "`**` chỉ mở được một dict (khi gọi hàm thì khoá phải là chuỗi)."),
    ("{**[1]}", 1, "`**` chỉ mở được một dict (khi gọi hàm thì khoá phải là chuỗi)."),
    (
        "def f(a=1):\n    pass\nf(**{1: 2})",
        3,
        "`**` chỉ mở được một dict (khi gọi hàm thì khoá phải là chuỗi).",
    ),
    ("5[0]", 1, "int không lấy phần tử bằng [] được."),
    ("{1, 2}[0]", 1, "set không lấy phần tử bằng [] được."),
    ('x = {}.get("k")\nx["y"]', 2, "None không lấy phần tử bằng [] được."),
    ("len[0]", 1, "function không lấy phần tử bằng [] được."),
    ("for x in 5:\n    pass", 1, "int không duyệt được."),
    ("[x for x in None]", 1, "None không duyệt được."),
    ("a, b = 5", 1, "int không duyệt được."),
    ("print(*5)", 1, "int không duyệt được."),
    ("for x in len:\n    pass", 1, "function không duyệt được."),
    ("a, b = [1, 2, 3]", 1, "tách 3 giá trị vào 2 tên."),
    ('a, b, c = "xy"', 1, "tách 2 giá trị vào 3 tên."),
    ("for a, b in [[1]]:\n    pass", 1, "tách 1 giá trị vào 2 tên."),
    ('s = "abc"\ns[0] = "x"', 2, "chỉ gán được vào tên, vào `list[i]` hoặc `dict[k]`."),
    ("xs = [1, 2]\nxs[0:1] = [5]", 2, "chỉ gán được vào tên, vào `list[i]` hoặc `dict[k]`."),
    ("pair = (1, 2)\npair[0] = 5", 2, "chỉ gán được vào tên, vào `list[i]` hoặc `dict[k]`."),
    ("pair = (1, 2)\npair[0] += 5", 2, "chỉ gán được vào tên, vào `list[i]` hoặc `dict[k]`."),
    ("xs = [1]\nxs[0:1] += [2]", 2, "chỉ gán được vào tên, vào `list[i]` hoặc `dict[k]`."),
    ("n = 0\ndef bump():\n    n += 1\nbump()", 3, "chưa có tên `n`."),
    ("total += 1", 1, "chưa có tên `total`."),
    ("sorted([1], nope=1)", 1, "gọi hàm `sorted` sai tham số."),
    ("sorted()", 1, "gọi hàm `sorted` sai tham số."),
    ("sorted([2], [1])", 1, "gọi hàm `sorted` sai tham số."),
    ("str(1, 2)", 1, "gọi hàm `str` sai tham số."),
    ('str("x", encoding="utf-8")', 1, "gọi hàm `str` sai tham số."),
    ("repr(1, 2)", 1, "gọi hàm `repr` sai tham số."),
    ("sum()", 1, "gọi hàm `sum` sai tham số."),
    ("sum([1], 2, 3)", 1, "gọi hàm `sum` sai tham số."),
    ("sum([1], begin=2)", 1, "gọi hàm `sum` sai tham số."),
    ("isinstance(1)", 1, "gọi hàm `isinstance` sai tham số."),
    ("max()", 1, "gọi hàm `max` sai tham số."),
    ("min([1], nope=2)", 1, "gọi hàm `min` sai tham số."),
    ("range(stop=3)", 1, "hàm `range` không nhận tham số theo tên."),
    ("len(x=1)", 1, "hàm `len` không nhận tham số theo tên."),
    ('int("5", base=8)', 1, "hàm `int` không nhận tham số theo tên."),
    ("def f(a):\n    pass\nf()", 3, "gọi hàm `f` sai tham số."),
    ("def f(a):\n    pass\nf(1, 2)", 3, "gọi hàm `f` sai tham số."),
    ("def f(a):\n    pass\nf(b=1)", 3, "gọi hàm `f` sai tham số."),
    ("def f(a):\n    pass\nf(1, a=2)", 3, "gọi hàm `f` sai tham số."),
    ("(lambda a: a)()", 1, "gọi hàm `lambda` sai tham số."),
    ("max([])", 1, "max() của một dãy rỗng."),
    ("min(n for n in [])", 1, "min() của một dãy rỗng."),
    ("sum([[1]], [])", 1, "sum chỉ cộng số."),
    ("isinstance(1, 5)", 1, "isinstance chỉ nhận str, int, float, bool, list, dict, set, tuple."),
    (
        'isinstance(1, "int")',
        1,
        "isinstance chỉ nhận str, int, float, bool, list, dict, set, tuple.",
    ),
    ("print(1, sep=2)", 1, "gọi hàm `print` sai tham số."),
    ('print(1, file="out")', 1, "gọi hàm `print` sai tham số."),
    ('json.load("x")', 1, "json chỉ có `loads` và `dumps`."),
    ('json.JSONDecoder("x")', 1, "json chỉ có `loads` và `dumps`."),
    ("json.loads(5)", 1, "gọi hàm `json.loads` sai tham số."),
    ("raise", 1, "`raise` trống chỉ dùng trong except."),
    ("range(10 * 1000 * 1000)", 1, "range dài quá 2000000 phần tử."),
    ("json.loads()", 1, NO_JSON),
    ('json.loads("1", "2")', 1, NO_JSON),
    ("json.dumps()", 1, NO_JSON),
    ("json.dumps(1, 2)", 1, NO_JSON),
    ("isinstance(1, int, extra=2)", 1, "gọi hàm `isinstance` sai tham số."),
    ("isinstance(1, len)", 1, ONLY_KINDS),
    ("isinstance(1, (int, print))", 1, ONLY_KINDS),
    ('print("a", end=1)', 1, "gọi hàm `print` sai tham số."),
    ("def f(a):\n    return a\nf(1, b=2)", 3, "gọi hàm `f` sai tham số."),
]

# The same lines as Python fails on them: the error is named as Python names it.
PYTHONS_OWN = [
    ('{}["k"]', 1),
    ("[1][5]", 1),
    ('"abc"[9]', 1),
    ("1 / 0", 1),
    ("5 % 0", 1),
    ('int("x")', 1),
    ('float("abc")', 1),
    ('"a" + 1', 1),
    ("len(5)", 1),
    ("[1] < 2", 1),
    ("{[1]: 2}", 1),
    ("[1, 2].index(9)", 1),
    ("[].pop()", 1),
    ('{}.pop("k")', 1),
    ('"a,b".split("")', 1),
    ("sorted([1, 'a'])", 1),
    ('json.loads("{")', 1),
    ("round('x')", 1),
    ('assert 1 > 2, "no"', 1),
    ("abs()", 1),
    ("json.dumps({1, 2})", 1),
    ('"a" * "b"', 1),
]


def unsupported(what: str) -> str:
    return f"`{what}` không dùng được trong script."


def python_says(source: str) -> str:
    """The same line failing in Python, said the way a script is told of it."""
    import json

    try:
        exec(compile(source, "<script>", "exec"), {"json": json})
    except Exception as error:  # noqa: BLE001 - whatever Python raises is the answer
        return f"{type(error).__name__}: {error}"
    raise AssertionError(f"{source!r} does not fail in Python")


@pytest.mark.parametrize(("source", "line", "what"), NOT_IN_THE_LANGUAGE)
def test_what_is_not_in_the_language_is_refused_before_a_line_runs(source, line, what):
    ended = play('print("ran")\n' + source, {"q": lambda arguments: "answered"})

    assert ended == {
        "ok": False,
        "output": "",
        "error": f"Dòng {line + 1}: {unsupported(what)}",
        "asked": [],
    }


@pytest.mark.parametrize(("source", "line", "name"), ATTRIBUTES)
def test_an_attribute_is_never_read_or_set(source, line, name):
    assert play(source) == {
        "ok": False,
        "output": "",
        "error": f"Dòng {line}: {NO_ATTRIBUTE.format(name=name)}",
        "asked": [],
    }


def test_a_refused_script_makes_none_of_its_calls():
    """Refused whole: the calls above the line that is wrong are not made either."""
    ended = play("tools.q()\nprint('half done')\nimport os", {"q": lambda arguments: "answered"})

    assert ended["asked"] == []
    assert ended["output"] == ""
    assert ended["error"] == "Dòng 3: `import os` không dùng được trong script."


@pytest.mark.parametrize(("source", "line", "said"), BAD_SYNTAX)
def test_a_script_python_cannot_read_is_told_so_in_pythons_words(source, line, said):
    with pytest.raises(SyntaxError) as python:
        compile(source, "<script>", "exec")

    assert play(source) == {
        "ok": False,
        "output": "",
        "error": f"Lỗi cú pháp ở dòng {line}: {said}",
        "asked": [],
    }
    assert (python.value.lineno, python.value.msg) == (line, said)


def test_a_warning_of_pythons_is_nobodys_to_read_and_never_the_scripts_to_fail_on():
    """Python warns of an odd escape and of `5()`. Under a runner that turns warnings
    into errors, as a test run may, neither is a reason to refuse the script. Nor is the
    warning passed on to whoever runs it."""
    odd_escape = 'print("a\\dz".upper())'

    with warnings.catch_warnings():
        warnings.simplefilter("error")

        assert printed(odd_escape) == "A\\DZ\n"
        assert stopped("5()") == "Lỗi ở dòng 1: int không phải hàm, không gọi được."
        assert stopped("{1, 2}[0]") == "Lỗi ở dòng 1: set không lấy phần tử bằng [] được."

    with warnings.catch_warnings(record=True) as shown:
        warnings.simplefilter("always")

        assert printed(odd_escape) == "A\\DZ\n"
    assert shown == []


def test_a_null_byte_in_a_script_is_a_refusal_and_not_a_crash():
    ended = play("x = 1\x00")

    assert not ended["ok"]
    assert ended["error"].startswith("Lỗi cú pháp ở dòng 1: ")
    assert "null" in ended["error"]


def test_an_expression_too_deep_to_read_ends_the_script_and_nothing_else():
    ended = play("x = " + "+".join(["1"] * 3000) + "\nprint(x)")

    assert not ended["ok"]
    assert ended["output"] == ""
    assert ended["error"] in (
        t.SCRIPT_SYNTAX.format(line=1, error=t.SCRIPT_TOO_NESTED),
        t.SCRIPT_HALTED.format(line=1, reason=t.SCRIPT_TOO_DEEP),
    )
    assert printed("x = " + "+".join(["1"] * 30) + "\nprint(x)") == "30\n"


TOO_MUCH_TO_READ = {
    "a sum of fifty thousand terms": "x = " + "+".join(["1"] * 50000),
    "a hundred thousand signs before a number": "-" * 100000 + "1",
}


@pytest.mark.parametrize("what", TOO_MUCH_TO_READ)
def test_a_script_python_gives_up_reading_is_refused_and_nothing_is_raised(what):
    """Python gives up on the first by its depth and on the second by its memory. Either is
    for the script to be told, never for its caller to catch."""
    assert play(TOO_MUCH_TO_READ[what]) == {
        "ok": False,
        "output": "",
        "error": t.SCRIPT_SYNTAX.format(line=1, error=t.SCRIPT_TOO_NESTED),
        "asked": [],
    }


def test_a_script_python_cannot_take_in_as_text_is_refused_in_pythons_words():
    half_a_pair = "x = '\ud800'"
    with pytest.raises(UnicodeEncodeError) as python:
        compile(half_a_pair, "<script>", "exec")

    assert play(half_a_pair) == {
        "ok": False,
        "output": "",
        "error": t.SCRIPT_SYNTAX.format(line=1, error=python.value),
        "asked": [],
    }


@pytest.mark.parametrize("name", NOT_THERE)
def test_a_name_of_pythons_that_reaches_past_plain_data_is_not_there(name):
    assert stopped(name) == f"Lỗi ở dòng 1: chưa có tên `{name}`."
    assert stopped(f"{name}(1)") == f"Lỗi ở dòng 1: chưa có tên `{name}`."
    # It is a mistake like any other: the script may catch it and go another way.
    assert printed(f"try:\n    {name}\nexcept Exception as e:\n    print(e)") == (
        f"chưa có tên `{name}`.\n"
    )


@pytest.mark.parametrize(("source", "line", "said"), MISTAKES)
def test_a_mistake_ends_the_script_at_its_line_with_what_was_wrong(source, line, said):
    ended = play('print("before")\n' + source + '\nprint("after")')

    assert ended["ok"] is False
    assert ended["output"] == "before\n"
    assert ended["error"] == f"Lỗi ở dòng {line + 1}: {said}"


@pytest.mark.parametrize(("source", "line", "said"), MISTAKES)
def test_a_mistake_is_one_the_script_may_catch(source, line, said):
    body = "\n".join(f"    {row}" for row in source.splitlines())

    assert printed(f"try:\n{body}\nexcept Exception as e:\n    print(e)\nprint('went on')") == (
        f"{said}\nwent on\n"
    )


@pytest.mark.parametrize(("source", "line"), PYTHONS_OWN)
def test_an_error_of_pythons_own_is_named_as_python_names_it(source, line):
    said = python_says(source)

    assert stopped(source) == f"Lỗi ở dòng {line}: {said}"
    assert printed(f"try:\n    {source}\nexcept Exception as e:\n    print(e)") == f"{said}\n"


def test_the_words_of_an_error_are_what_a_reader_of_python_knows():
    assert stopped('{}["k"]') == "Lỗi ở dòng 1: KeyError: 'k'"
    assert stopped("[1][5]") == "Lỗi ở dòng 1: IndexError: list index out of range"
    assert stopped("1 / 0") == "Lỗi ở dòng 1: ZeroDivisionError: division by zero"
    assert stopped('assert 1 > 2, "no"') == "Lỗi ở dòng 1: AssertionError: no"
    assert stopped("assert False") == "Lỗi ở dòng 1: AssertionError"
    assert stopped("assert [], {'rows': 0}") == "Lỗi ở dòng 1: AssertionError: {'rows': 0}"


def test_a_script_that_fails_keeps_what_it_had_printed():
    ended = play(
        """
        print("one")
        rows = [1, 2]
        print("two", rows[5])
        print("three")
        """
    )

    assert ended == {
        "ok": False,
        "output": "one\n",
        "error": "Lỗi ở dòng 4: IndexError: list index out of range",
        "asked": [],
    }


LINES = {
    "inside the function that failed": (
        """
        def first(rows):
            return rows[0]

        print(first([]))
        """,
        "Lỗi ở dòng 3: IndexError: list index out of range",
    ),
    "after a function came back, at the line that used what it gave": (
        """
        def get(data):
            return data

        value = get({})["missing"]
        """,
        "Lỗi ở dòng 5: KeyError: 'missing'",
    ),
    "on the line of a long expression that failed": (
        """
        total = (
            1
            + {}["k"]
            + 3
        )
        """,
        "Lỗi ở dòng 4: KeyError: 'k'",
    ),
    "in the loop, after the function it calls came back": (
        """
        def double(n):
            return n * 2

        for n in [1, 2]:
            double(n)
            [][n]
        """,
        "Lỗi ở dòng 7: IndexError: list index out of range",
    ),
    "in a comprehension, on the line of the part that failed": (
        """
        rows = [{"n": 1}, {}]
        found = [
            row["n"]
            for row in rows
        ]
        """,
        "Lỗi ở dòng 4: KeyError: 'n'",
    ),
    "where the argument was worked out, not where the call began": (
        """
        print(
            "a",
            int("x"),
        )
        """,
        "Lỗi ở dòng 4: ValueError: invalid literal for int() with base 10: 'x'",
    ),
    "at the tool call that failed": (
        """
        x = 1
        y = tools.missing(query="a")
        """,
        "Lỗi ở dòng 3: no tool missing",
    ),
    "at the last line, when that is the one shown": (
        """
        x = {}
        x["k"]
        """,
        "Lỗi ở dòng 3: KeyError: 'k'",
    ),
    "at the handler, when the handler is what failed": (
        """
        try:
            {}["k"]
        except KeyError:
            [][0]
        """,
        "Lỗi ở dòng 5: IndexError: list index out of range",
    ),
    "at the else, which the handlers of its own try do not guard": (
        """
        try:
            pass
        except Exception:
            print("never")
        else:
            {}["k"]
        """,
        "Lỗi ở dòng 7: KeyError: 'k'",
    ),
}


@pytest.mark.parametrize("where", LINES)
def test_an_error_is_laid_at_the_line_it_came_from(where):
    source, said = LINES[where]

    assert stopped(source) == said


def failing(said: str):
    def tool(arguments):
        raise ScriptError(said)

    return tool


def refusing(said: str):
    def tool(arguments):
        raise Halt(said)

    return tool


def out_of(error: type[BaseException]):
    def tool(arguments):
        raise error()

    return tool


RAN_OUT = [(MemoryError, t.SCRIPT_OUT_OF_ROOM), (RecursionError, t.SCRIPT_TOO_DEEP)]


@pytest.mark.parametrize(("error", "reason"), RAN_OUT)
def test_python_out_of_memory_or_depth_ends_the_script_at_the_line_it_was_on(error, reason):
    """Neither is an error a script could catch nor one its caller should see raised: the
    script ends where it was, keeping what it had printed."""
    ended = play(
        'try:\n    print("before")\n    tools.boom()\nexcept Exception:\n    print("caught")',
        {"boom": out_of(error)},
    )

    assert ended == {
        "ok": False,
        "output": "before\n",
        "error": t.SCRIPT_HALTED.format(line=3, reason=reason),
        "asked": [("boom", {})],
    }


def test_running_out_is_laid_at_the_line_being_worked_out_not_where_its_statement_began():
    ended = play("x = 1\ny = [\n    tools.boom(),\n]", {"boom": out_of(MemoryError)})

    assert ended["error"] == t.SCRIPT_HALTED.format(line=3, reason=t.SCRIPT_OUT_OF_ROOM)


def test_running_out_while_a_statement_is_set_up_is_laid_at_that_statement(monkeypatch):
    """A `def` works nothing out, so the line is the statement's own and not the last one
    something was worked out on."""

    def no_room(machine, node, env):
        raise MemoryError

    monkeypatch.setattr(statements, "function", no_room)

    ended = play("x = [\n    1,\n]\ndef f():\n    pass")

    assert ended["error"] == t.SCRIPT_HALTED.format(line=4, reason=t.SCRIPT_OUT_OF_ROOM)


CATCHES = {
    "a bare except": "except:",
    "except Exception": "except Exception:",
    "except BaseException": "except BaseException:",
    "a name Python does not have": "except ToolError:",
    "a name of Python's the interpreter does not know": "except RuntimeError:",
    "a list of names with one such in it": "except (KeyError, ToolError):",
    "a dotted name": "except tools.Failed:",
}


@pytest.mark.parametrize("how", CATCHES)
def test_a_tool_that_failed_is_caught_by_any_except_not_naming_an_error_of_pythons(how):
    source = f"try:\n    tools.q()\n{CATCHES[how]}\n    print('caught')\nprint('went on')"

    assert printed(source, {"q": failing("the server said no")}) == "caught\nwent on\n"


@pytest.mark.parametrize("names", ["KeyError", "(KeyError, ValueError)", "LookupError"])
def test_a_tool_that_failed_is_not_one_of_pythons_errors(names):
    source = f"try:\n    tools.q()\nexcept {names}:\n    print('caught')"
    ended = play(source, {"q": failing("the server said no")})

    assert (ended["ok"], ended["output"]) == (False, "")
    assert ended["error"] == "Lỗi ở dòng 2: the server said no"


def test_a_tool_that_failed_is_read_as_what_it_said():
    said = printed(
        """
        try:
            tools.q(query="x")
        except Exception as e:
            print("failed:", e, len(e))
        """,
        {"q": failing("không tìm thấy trang")},
    )

    assert said == "failed: không tìm thấy trang 20\n"


def test_an_error_of_pythons_is_not_caught_under_another_name():
    assert stopped("try:\n    {}['k']\nexcept ToolError:\n    print('no')") == (
        "Lỗi ở dòng 2: KeyError: 'k'"
    )
    assert stopped("try:\n    {}['k']\nexcept (ValueError, TypeError):\n    print('no')") == (
        "Lỗi ở dòng 2: KeyError: 'k'"
    )
    assert stopped("try:\n    1 / 0\nexcept LookupError:\n    print('no')") == (
        "Lỗi ở dòng 2: ZeroDivisionError: division by zero"
    )


def test_the_first_except_that_fits_is_the_one_that_runs():
    said = printed(
        """
        for risky in [lambda: {}["k"], lambda: 1 / 0, lambda: tools.q()]:
            try:
                risky()
            except ArithmeticError:
                print("arithmetic")
            except LookupError:
                print("lookup")
            except KeyError:
                print("never: the one above took it")
            except Exception as e:
                print("other:", e)
        """
    )

    assert said == "lookup\narithmetic\nother: no tool q\n"


RAISED = {
    'raise ValueError("bad")': "ValueError: bad",
    "raise ValueError": "ValueError",
    'raise KeyError("k")': "KeyError: 'k'",
    'raise Oops("x")': "x",
    "raise Oops": "Oops",
    'raise Exception("stop here")': "stop here",
    "raise Exception": "Exception",
    'raise RuntimeError(f"only {1 + 1} rows")': "only 2 rows",
    'raise ValueError("a", 2)': "ValueError: ('a', 2)",
    "raise ValueError(5)": "ValueError: 5",
    'raise json.JSONDecodeError("not json")': "ValueError: not json",
    'raise "just words"': "just words",
    'raise AttributeError("gone")': "AttributeError: gone",
}


@pytest.mark.parametrize("line", RAISED)
def test_a_script_raises_an_error_of_its_own(line):
    assert stopped(f"print('before')\n{line}") == f"Lỗi ở dòng 2: {RAISED[line]}"
    assert printed(f"try:\n    {line}\nexcept Exception as e:\n    print(e)") == (
        f"{RAISED[line]}\n"
    )


def test_what_a_script_raises_is_caught_by_the_name_it_was_raised_with():
    said = printed(
        """
        def check(n):
            if n < 0:
                raise ValueError("negative")
            if n == 0:
                raise Empty("nothing")
            return n

        for n in [1, -1, 0]:
            try:
                print(check(n))
            except ValueError as e:
                print("value:", e)
            except Empty as e:
                print("empty:", e)
        """
    )

    assert said == "1\nvalue: ValueError: negative\nempty: nothing\n"


def test_raising_what_an_except_named_raises_its_words_again():
    source = """
        try:
            {}["k"]
        except KeyError as e:
            print("seen")
            raise e
        """

    ended = play(source)

    assert (ended["output"], ended["error"]) == ("seen\n", "Lỗi ở dòng 6: KeyError: 'k'")


def test_what_is_raised_again_by_name_is_its_words_and_no_longer_its_kind():
    said = printed(
        """
        try:
            try:
                {}["k"]
            except KeyError as e:
                raise e
        except KeyError:
            print("never: only its words were raised")
        except Exception as again:
            print("again:", again)
        """
    )

    assert said == "again: KeyError: 'k'\n"


def test_a_bare_raise_raises_the_same_error_from_where_it_first_failed():
    said = printed(
        """
        try:
            try:
                {}["k"]
            except KeyError:
                print("seen")
                raise
        except LookupError as e:
            print("outer", e)
        """
    )

    assert said == "seen\nouter KeyError: 'k'\n"
    assert (
        stopped("try:\n    {}['k']\nexcept KeyError:\n    raise") == "Lỗi ở dòng 2: KeyError: 'k'"
    )


def test_a_bare_raise_is_about_the_except_it_stands_in():
    inner_done = """
        try:
            1 / 0
        except ZeroDivisionError:
            try:
                {}["k"]
            except KeyError:
                pass
            raise
        """
    left = """
        try:
            1 / 0
        except ZeroDivisionError:
            pass
        raise
        """

    assert stopped(inner_done) == "Lỗi ở dòng 3: ZeroDivisionError: division by zero"
    assert stopped(left) == "Lỗi ở dòng 6: `raise` trống chỉ dùng trong except."


def test_finally_runs_when_the_script_fails_and_the_failure_goes_on():
    ended = play(
        """
        def risky():
            try:
                return {}["k"]
            finally:
                print("cleanup")

        try:
            risky()
        except KeyError:
            print("caught outside")
        try:
            [][0]
        finally:
            print("last words")
        print("never")
        """
    )

    assert ended["output"] == "cleanup\ncaught outside\nlast words\n"
    assert ended["error"] == "Lỗi ở dòng 13: IndexError: list index out of range"


def test_a_call_a_script_may_not_make_ends_it_whatever_it_wrote():
    """Not caught, and no `finally`: nothing of the script runs once it is stopped."""
    ended = play(
        """
        print("before")
        try:
            tools.write(text="x")
        except:
            print("caught")
        finally:
            print("cleanup")
        print("after")
        """,
        {"write": refusing("`write` phải hỏi trước.")},
    )

    assert ended == {
        "ok": False,
        "output": "before\n",
        "error": "Dừng ở dòng 4: `write` phải hỏi trước.",
        "asked": [("write", {"text": "x"})],
    }


def test_a_call_refused_inside_a_function_ends_the_script_at_that_call():
    ended = play(
        """
        def save(text):
            try:
                return tools.write(text=text)
            except Exception:
                return "fallback"

        print(save("x"))
        """,
        {"write": refusing("no")},
    )

    assert (ended["output"], ended["error"]) == ("", "Dừng ở dòng 4: no")


WRONG_TOOL_CALLS = {
    'tools.q("words")': t.SCRIPT_TOOL_ARGS,
    'tools.q({"a": 1}, {"b": 2})': t.SCRIPT_TOOL_ARGS,
    'tools.q({"a": 1}, b=2)': t.SCRIPT_TOOL_ARGS,
    "tools.q([1, 2])": t.SCRIPT_TOOL_ARGS,
    "tools.q(when={1, 2})": t.SCRIPT_TOOL_ARGS_JSON,
    "tools.q(fn=len)": t.SCRIPT_TOOL_ARGS_JSON,
    "tools.q({(1, 2): 3})": t.SCRIPT_TOOL_ARGS_JSON,
}


@pytest.mark.parametrize("call", WRONG_TOOL_CALLS)
def test_a_tool_called_the_wrong_way_is_a_mistake_and_the_tool_is_not_asked(call):
    ended = play(call, {"q": lambda arguments: "answered"})

    assert ended["asked"] == []
    assert ended["error"] == f"Lỗi ở dòng 1: {WRONG_TOOL_CALLS[call]}"
    assert printed(f"try:\n    {call}\nexcept Exception as e:\n    print(e)") == (
        f"{WRONG_TOOL_CALLS[call]}\n"
    )


def test_the_words_a_wrongly_called_tool_is_told():
    assert t.SCRIPT_TOOL_ARGS == "gọi công cụ bằng tham số theo tên, hoặc đúng một dict."
    assert t.SCRIPT_TOOL_ARGS_JSON == (
        "tham số gọi công cụ phải là dữ liệu JSON (chuỗi, số, list, dict)."
    )
