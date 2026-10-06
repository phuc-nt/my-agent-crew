"""How much a script may do: its steps, its values, what it prints, its calls, its memory.

Each limit is tried from both sides: what stays inside it runs to its end, and what goes
past it stops with the line that says which limit that was. The limits a script cannot
catch are tried under a `try` as well, and a `finally` that must not run is there to run.
"""

from __future__ import annotations

import json
import tracemalloc

import pytest

from my_agent_crew.script import limits
from my_agent_crew.script.limits import ScriptError
from tests.script_helpers import play, printed, stopped

OUT_OF_ROOM = "script tạo ra quá nhiều dữ liệu. Lọc bớt trước khi gom lại."
OUT_OF_STEPS = "script chạy quá 300 bước. Xử lý ít dữ liệu hơn hoặc bỏ vòng lặp thừa."
TOO_NESTED = "dữ liệu lồng nhau quá sâu hoặc quá nhiều phần tử để viết ra."
TOO_MUCH_OUTPUT = "script in ra quá 60000 ký tự. Chỉ in phần cần, đã gộp hoặc lọc."
TOO_MANY_CALLS = "Script đã gọi công cụ quá 25 lần. Gộp việc lại hoặc chia nhiều script."
TOO_DEEP = "hàm gọi lồng nhau quá sâu."
# Whatever a script wrote around it, a limit it cannot catch ends it there.
GUARDED = """
try:
{body}
except Exception:
    print("caught")
finally:
    print("cleanup")
print("after")
"""


def halted(line: int, reason: str) -> str:
    return f"Dừng ở dòng {line}: {reason}"


def guarded(body: str) -> str:
    """The lines under a `try` that would catch them if they could be caught: the first
    of them is on line 3."""
    return GUARDED.format(body="\n".join(f"    {line}" for line in body.splitlines()))


def answering(said: str):
    return lambda arguments: said


def failing(said: str):
    def fail(arguments):
        raise ScriptError(said)

    return fail


# --- steps ---


@pytest.fixture
def few_steps(monkeypatch):
    monkeypatch.setattr(limits, "MAX_STEPS", 300)


def test_a_loop_without_end_is_stopped_and_what_it_printed_is_kept(few_steps):
    assert play('print("started")\nwhile True: pass') == {
        "ok": False,
        "output": "started\n",
        "error": halted(2, OUT_OF_STEPS),
        "asked": [],
    }


def test_a_script_out_of_steps_runs_nothing_more_whatever_it_wrote(few_steps):
    ended = play(guarded("while True: pass"))

    assert (ended["output"], ended["error"]) == ("", halted(3, OUT_OF_STEPS))


def test_steps_are_counted_over_the_whole_script_and_not_over_each_loop(few_steps):
    loop = "for n in range(30): total = total + n\n"

    assert printed(f"total = 0\n{loop}print(total)") == "435\n"
    assert stopped(f"total = 0\n{loop}{loop}{loop}print(total)") == halted(4, OUT_OF_STEPS)


def test_writing_a_value_out_costs_a_step_for_each_thing_in_it(few_steps):
    """Else a script would have a long walk for the price of one call, as often as it liked."""
    held = "x = list(range(100))\n"

    assert printed(f"{held}y = str(x)\nprint(len(y))") == f"{len(str(list(range(100))))}\n"
    assert stopped(f"{held}y = str(x)\ny = str(x)\ny = str(x)") == halted(4, OUT_OF_STEPS)


def test_the_steps_a_script_really_has_are_enough_for_a_long_table():
    assert printed("print(sum([n % 7 for n in range(100000)]))") == "299995\n"


# --- ranges ---


def test_a_range_is_as_long_as_a_script_has_steps_and_no_longer():
    assert printed("print(len(range(2000000)), sum(range(2000000)))") == "2000000 1999999000000\n"
    assert stopped("range(2000001)") == "Lỗi ở dòng 1: range dài quá 2000000 phần tử."
    assert stopped('range(int("1" + "0" * 30))') == "Lỗi ở dòng 1: range dài quá 2000000 phần tử."
    assert printed(guarded("range(0, 4000002, 2)\nrange(2000001)")) == "caught\ncleanup\nafter\n"


# --- the size of one value ---


@pytest.fixture
def small_values(monkeypatch):
    monkeypatch.setattr(limits, "MAX_VALUE", 1000)


# `N` is how long the value comes to. Each is (the script, the line it stops on).
MAKES = {
    "a text repeated": ('print(len("a" * N))', 1),
    "a text repeated from the left": ('print(len(N * "a"))', 1),
    "a list repeated": ("print(len([0] * N))", 1),
    "a tuple repeated": ("print(len((0,) * N))", 1),
    "a list repeated in place": ("x = [0]\nx *= N\nprint(len(x))", 2),
    "texts added": ('x = "a" * 600\nprint(len(x + "a" * (N - 600)))', 2),
    "lists added in place": ("x = [0] * 600\nx += [0] * (N - 600)\nprint(len(x))", 2),
    "texts joined": ('x = ["a" * 600, "a" * (N - 601)]\nprint(len("-".join(x)))', 2),
    "texts joined by a long one": ('x = ["a", "b"]\nprint(len(("-" * (N - 2)).join(x)))', 2),
    "a text with parts replaced": (
        'x = "a" * 300 + "c" * (N - 600)\nprint(len(x.replace("a", "bb")))',
        2,
    ),
    "a text with so many parts replaced": (
        'x = "a" * 700\nprint(len(x.replace("a", "bb", N - 700)))',
        2,
    ),
    # Three places in a text of two: 998 long for 1000, 1001 long for 1001.
    "a text with a part put between its letters": (
        'x = "cc"\nprint(len(x.replace("", "a" * ((N - 2) // 3))) + 2)',
        2,
    ),
    "an f-string": ('a = "a" * 600\nb = "a" * (N - 600)\nprint(len(f"{a}{b}"))', 3),
    "a list with others opened in it": (
        "a = [0] * 600\nb = [0] * (N - 600)\nprint(len([*a, *b]))",
        3,
    ),
    "a call with lists opened in it": (
        "a = [0] * 600\nb = [0] * (N - 600)\nprint(max(*a, *b) + 1000)",
        3,
    ),
    "a dict with others opened in it": (
        "a = {n: 0 for n in range(600)}\nb = {n: 0 for n in range(600, N)}\nprint(len({**a, **b}))",
        3,
    ),
    "a list given one more": ("x = [0] * (N - 1)\nx.append(0)\nprint(len(x))", 2),
    "a list given one more in the middle": ("x = [0] * (N - 1)\nx.insert(5, 1)\nprint(len(x))", 2),
    "a list given many more": ("x = [0] * 600\nx.extend([0] * (N - 600))\nprint(len(x))", 2),
    "a set given one more": ("x = set(range(N - 1))\nx.add(-1)\nprint(len(x))", 2),
    "a set given many more": ("x = set(range(600))\nx.update(range(600, N))\nprint(len(x))", 2),
    "a dict given one more": (
        'x = {n: 0 for n in range(N - 1)}\nx.setdefault("k", 0)\nprint(len(x))',
        2,
    ),
    "a dict given many more": (
        "x = {n: 0 for n in range(600)}\nx.update({n: 0 for n in range(600, N)})\nprint(len(x))",
        2,
    ),
    "a dict given more by name": (
        "x = {n: 0 for n in range(N - 2)}\nx.update(a=1, b=2)\nprint(len(x))",
        2,
    ),
    "a list of a range": ("print(len(list(range(N))))", 1),
    "a tuple of a range": ("print(len(tuple(range(N))))", 1),
    "a set of a range": ("print(len(set(range(N))))", 1),
    "a range sorted": ("print(len(sorted(range(N))))", 1),
    "a range turned round": ("print(len(reversed(range(N))))", 1),
    "a range numbered": ("print(len(enumerate(range(N))))", 1),
    "two ranges zipped": ("print(len(zip(range(N), range(N))))", 1),
    "a dict's keys": ("x = {n: 0 for n in range(N)}\nprint(len(x.keys()))", 2),
    "a dict walked": ("x = {n: 0 for n in range(N)}\nfor k in x: pass\nprint(len(x))", 2),
    "a text written as JSON": ('print(len(json.dumps("a" * (N - 2))))', 1),
    "a dict copied": ("x = {n: 0 for n in range(N)}\nprint(len(dict(x)))", 2),
    # Each of the 499 line ends is two characters once written out, and the quotes two more.
    "a text written with its escapes": (
        'x = "\\n" * 499 + "a" * (N - 1000)\nprint(len(repr(x)))',
        2,
    ),
}


@pytest.mark.parametrize("name", MAKES)
def test_no_one_value_is_longer_than_a_script_may_hold(small_values, name):
    source, line = MAKES[name]

    assert printed(source.replace("N", "1000")) == "1000\n"
    assert stopped(source.replace("N", "1001")) == halted(line, OUT_OF_ROOM)


@pytest.mark.parametrize("name", MAKES)
def test_a_value_too_long_ends_the_script_whatever_it_wrote(small_values, name):
    source, line = MAKES[name]

    ended = play(guarded(source.replace("N", "1001")))

    assert (ended["output"], ended["error"]) == ("", halted(line + 2, OUT_OF_ROOM))


# A dict spread from another, then one key more, then a key whose value a tool answers.
SPREAD = """
held = {n: 0 for n in range(N)}
wide = {**held, **{"one more": 0}, "answer": tools.ask()}
print(len(wide))
"""


def test_a_dict_spread_too_long_ends_the_script_before_what_stands_after_it(small_values):
    """The length is looked at after each spread, not only where the braces close: what
    follows a spread too long is never worked out, so the tool is not asked."""
    tools = {"ask": answering("said")}

    fits = play(SPREAD.replace("N", "998"), tools)
    closes = play(SPREAD.replace("N", "999"), tools)
    spreads = play(SPREAD.replace("N", "1000"), tools)

    assert (fits["output"], fits["error"], fits["asked"]) == ("1000\n", None, [("ask", {})])
    assert (closes["output"], closes["error"]) == ("", halted(3, OUT_OF_ROOM))
    assert closes["asked"] == [("ask", {})]
    assert (spreads["output"], spreads["error"]) == ("", halted(3, OUT_OF_ROOM))
    assert spreads["asked"] == []


WRITTEN_OUT = {
    "a list": lambda count: "[" + "0," * count + "]",
    "a tuple": lambda count: "(" + "0," * count + ")",
    "a set": lambda count: "{" + ",".join(str(n) for n in range(count)) + "}",
    "a dict": lambda count: "{" + ",".join(f"{n}:0" for n in range(count)) + "}",
}


@pytest.mark.parametrize("kind", WRITTEN_OUT)
def test_a_value_written_out_item_by_item_is_no_longer_than_any_other(small_values, kind):
    written = WRITTEN_OUT[kind]

    assert printed(f"print(len({written(1000)}))") == "1000\n"
    assert stopped(f"print(len({written(1001)}))") == halted(1, OUT_OF_ROOM)


# A count Python itself refuses at once: left to Python, the script would catch the refusal.
REPEATS = [
    '"a" * (10000000000 * 10000000000)',
    "[0] * (10000000000 * 10000000000)",
    "(0,) * (10000000000 * 10000000000)",
]


@pytest.mark.parametrize("repeat", REPEATS)
def test_a_repeat_too_long_is_refused_before_python_is_asked_to_make_it(repeat):
    ended = play(guarded(repeat))

    assert (ended["output"], ended["error"]) == ("", halted(3, OUT_OF_ROOM))


def test_a_part_of_a_text_too_long_ends_the_script_at_its_own_line(monkeypatch):
    monkeypatch.setattr(limits, "MAX_VALUE", 100)

    assert stopped('x = f"""a\n{1:>200}"""') == halted(2, OUT_OF_ROOM)


def test_what_is_written_out_is_sized_by_all_it_names_and_not_by_what_it_holds(small_values):
    """A list of three is three long, and names the one text it holds three times over."""
    held = 'a = "a" * 400\n'

    assert printed(f"{held}x = [a, a, a]\nprint(len(x), len(str([a, a])))") == "3 808\n"
    for line in (
        "str(x)",
        "repr(x)",
        "json.dumps(x)",
        'f"{x}"',
        "print(x)",
        "tools.q(rows=x)",
        "x",
    ):
        said = play(f"{held}x = [a, a, a]\n{line}", {"q": answering("fine")})

        assert (said["error"], said["asked"]) == (halted(3, OUT_OF_ROOM), []), line


def test_a_value_as_long_as_a_script_may_hold_is_held_and_one_longer_is_not():
    """The real limit, once: the others are tried with a small one."""
    assert printed('print(len("a" * 8000000))') == "8000000\n"
    assert stopped('print(len("a" * 8000001))') == halted(1, OUT_OF_ROOM)


# --- what is written out: how deep, how many ---

NESTED = """
x = []
for n in range(N):
    x = [x]
"""
WRITES = ("print(x)", "str(x)", "repr(x)", "json.dumps(x)", 'f"{x}"', "tools.q(rows=x)", "x")


def test_data_is_written_out_fifty_deep_and_no_deeper():
    assert printed(NESTED.replace("N", "49") + "print(str(x))") == "[" * 50 + "]" * 50 + "\n"
    for line in WRITES:
        said = play(NESTED.replace("N", "50") + line, {"q": answering("fine")})

        assert (said["error"], said["asked"]) == (f"Lỗi ở dòng 5: {TOO_NESTED}", []), line


@pytest.mark.parametrize("line", WRITES)
def test_data_that_holds_itself_is_never_written_out(line):
    for made in ("x = []\nx.append(x)", 'x = {}\nx["me"] = x', "x = [{}]\nx[0][1] = (x,)"):
        said = play(f"{made}\n{line}", {"q": answering("fine")})

        assert (said["error"], said["asked"]) == (f"Lỗi ở dòng 3: {TOO_NESTED}", []), made


def test_data_too_deep_to_write_is_still_data_a_script_may_hold_and_mend():
    said = printed(
        NESTED.replace("N", "500")
        + """
try:
    print(x)
except Exception as e:
    print(e)
count = 0
while len(x) > 0:
    x = x[0]
    count += 1
print(count, x)
"""
    )

    assert said == f"{TOO_NESTED}\n500 []\n"


def test_data_is_written_out_two_hundred_thousand_things_long_and_no_longer():
    assert printed("print(len(str(list(range(199999)))))") == f"{len(str(list(range(199999))))}\n"
    assert stopped("str(list(range(200000)))") == f"Lỗi ở dòng 1: {TOO_NESTED}"
    assert stopped("x = [[n] for n in range(100000)]\njson.dumps(x)") == (
        f"Lỗi ở dòng 2: {TOO_NESTED}"
    )
    assert printed("x = list(range(200000))\nprint(len(x), sum(x))") == "200000 19999900000\n"


# --- what a script prints ---


def test_a_script_prints_sixty_thousand_characters_and_no_more():
    assert printed('print("x" * 59999)') == "x" * 59999 + "\n"
    assert play('print("x" * 60000)') == {
        "ok": False,
        "output": "x" * 60000,
        "error": halted(1, TOO_MUCH_OUTPUT),
        "asked": [],
    }


def test_a_script_that_prints_without_end_is_stopped_with_what_fitted():
    ended = play('for n in range(5000):\n    print(n, "x" * 100)')

    assert ended["error"] == halted(2, TOO_MUCH_OUTPUT)
    assert len(ended["output"]) == 60000
    assert ended["output"].startswith("0 " + "x" * 100 + "\n1 ")


def test_printing_too_much_cannot_be_caught():
    ended = play(guarded('print("x" * 70000)'))

    assert (ended["output"], ended["error"]) == ("x" * 60000, halted(3, TOO_MUCH_OUTPUT))


def test_the_value_of_the_last_line_counts_as_printed():
    assert stopped('"x" * 60000') == halted(1, TOO_MUCH_OUTPUT)
    assert printed('"x" * 59999') == "x" * 59999 + "\n"


def test_printing_too_much_is_laid_at_the_line_that_printed_it():
    """Not at the last line worked out before it: the text is made a line below the
    `print` that takes it, and a line above the call whose value is shown at the end."""
    assert stopped('print(\n    "x" * 70000\n)') == halted(1, TOO_MUCH_OUTPUT)
    assert stopped('def big():\n    return "x" * 70000\nbig()') == halted(3, TOO_MUCH_OUTPUT)


# --- numbers ---


def test_a_whole_number_has_two_hundred_and_fifty_six_bits_and_no_more():
    doubled = "x = 1\nfor n in range(N):\n    x = x + x\nprint(x)"

    assert printed(doubled.replace("N", "255")) == f"{2**255}\n"
    assert stopped(doubled.replace("N", "256")) == "Lỗi ở dòng 3: số nguyên quá lớn."


@pytest.mark.parametrize(
    "line",
    [
        "x * x * x",
        "x * -x * x",
        "-(x * x * x)",
        'int("9" * 100)',
        "int(1e300)",
        "sum([x * x * 36028797018963968] * 2)",
        "abs(x * x) * x",
        "x * x // 1 * x",
    ],
)
def test_a_number_too_large_is_a_mistake_the_script_may_catch(line):
    held = f"x = {2**100}\n"

    assert stopped(held + line) == "Lỗi ở dòng 2: số nguyên quá lớn."
    assert printed(held + guarded(line)) == "caught\ncleanup\nafter\n"


# --- functions inside functions ---

DOWN = """
def down(n):
    return 0 if n == 0 else 1 + down(n - 1)
"""


def test_a_function_calls_itself_forty_deep_and_no_deeper():
    assert printed(DOWN + "print(down(39))") == "39\n"
    assert stopped(DOWN + "print(down(40))") == halted(3, TOO_DEEP)


def test_calling_too_deep_cannot_be_caught():
    ended = play(DOWN + guarded("down(40)"))

    assert (ended["output"], ended["error"]) == ("", halted(3, TOO_DEEP))


def test_the_depth_a_call_took_is_given_back_when_it_ends_however_it_ends():
    said = printed(
        DOWN
        + """
def fail(n):
    if n == 0:
        return {}["k"]
    return fail(n - 1)

for n in range(5):
    try:
        fail(30)
    except KeyError:
        pass
print(down(30) + down(30), down(39))
"""
    )

    assert said == "60 39\n"


def test_a_function_called_for_each_item_is_one_call_deep_each_time():
    assert printed(DOWN + "print(sorted([3, 1, 2], key=lambda n: down(n + 30)))") == "[1, 2, 3]\n"
    assert stopped(DOWN + "sorted([3, 1], key=lambda n: down(39))") == halted(3, TOO_DEEP)


# --- tool calls ---


def test_a_script_makes_twenty_five_calls_and_not_one_more():
    made = play('for n in range(25):\n    tools.read(n=n)\nprint("done")', {"read": answering("x")})

    assert (made["ok"], made["output"], len(made["asked"])) == (True, "done\n", 25)

    over = play(
        'print("before")\nfor n in range(40):\n    tools.read(n=n)\nprint("done")',
        {"read": answering("x")},
    )

    assert (over["output"], over["error"]) == ("before\n", halted(3, TOO_MANY_CALLS))
    assert over["asked"] == [("read", {"n": n}) for n in range(25)]


def test_one_call_too_many_cannot_be_caught():
    ended = play(guarded("for n in range(26):\n    tools.read(n=n)"), {"read": answering("x")})

    assert (ended["output"], ended["error"]) == ("", halted(4, TOO_MANY_CALLS))
    assert len(ended["asked"]) == 25


def test_a_call_that_failed_was_still_a_call():
    ended = play(
        """
        failed = 0
        for n in range(30):
            try:
                tools.read(n=n)
            except Exception:
                failed += 1
        """,
        {"read": failing("no")},
    )

    assert (ended["error"], len(ended["asked"])) == (halted(5, TOO_MANY_CALLS), 25)


def test_arguments_too_long_to_send_are_a_mistake_the_script_may_mend():
    said = play(
        """
        long = "x" * 100000
        try:
            tools.save(text=long)
        except Exception as e:
            print(e)
        print(tools.save(text=long[:99000]))
        """,
        {"save": lambda arguments: str(len(arguments["text"]))},
    )

    assert said["output"] == "tham số gọi công cụ dài quá 100000 ký tự.\n99000\n"
    assert [len(arguments["text"]) for _, arguments in said["asked"]] == [99000]
    assert stopped('tools.save(rows=["x" * 1000] * 100)') == (
        "Lỗi ở dòng 1: tham số gọi công cụ dài quá 100000 ký tự."
    )


def test_arguments_are_sent_up_to_the_most_and_not_one_character_over():
    """One text under a one-letter name is counted as the text and eleven more."""
    said = printed(
        'print(tools.q(a="x" * 99989))', {"q": lambda arguments: str(len(arguments["a"]))}
    )

    assert said == "99989\n"
    assert play('tools.q(a="x" * 99990)', {"q": answering("sent")}) == {
        "ok": False,
        "output": "",
        "error": "Lỗi ở dòng 1: tham số gọi công cụ dài quá 100000 ký tự.",
        "asked": [],
    }


def test_json_too_deep_for_python_to_read_is_a_mistake_the_script_may_mend():
    said = printed(
        """
        try:
            json.loads("[" * 100000 + "]" * 100000)
        except Exception as e:
            print(e)
        """
    )

    assert said == f"{TOO_NESTED}\n"


def test_a_call_never_sent_is_not_one_of_the_twenty_five():
    said = play(
        """
        long = "x" * 100000
        for n in range(30):
            try:
                tools.save(text=long)
            except Exception:
                pass
            try:
                tools.save("not", "a dict")
            except Exception:
                pass
            try:
                tools.save(when={1, 2})
            except Exception:
                pass
        for n in range(25):
            tools.save(text="short")
        print("done")
        """,
        {"save": answering("saved")},
    )

    assert (said["error"], said["output"], len(said["asked"])) == (None, "done\n", 25)


# --- how much of an error is told ---


def test_an_error_is_told_in_two_thousand_characters_and_no_more():
    raised = stopped('raise ValueError("x" * 5000)')
    failed = stopped("tools.read()", {"read": failing("y" * 5000)})

    assert (len(raised), raised[:30]) == (2000, "Lỗi ở dòng 1: ValueError: xxxx")
    assert (len(failed), failed[:20]) == (2000, "Lỗi ở dòng 1: yyyyyy")
    assert printed(
        'try:\n    raise ValueError("x" * 5000)\nexcept ValueError as e:\n    print(len(e))'
    ) == ("5012\n")


# --- how long a value is counted as before it is written ---


def test_a_number_is_counted_as_the_longest_a_number_is_written():
    longest = -1.7976931348623157e308

    assert limits.Budget().measure(longest) == len(repr(longest)) == 24


WRITTEN = {
    "the longest float": -1.7976931348623157e308,
    "a whole number of the most bits": 2**256 - 1,
    "and one below nothing": -(2**256 - 1),
    "a dict under a long name": {"k" * 1000: 1},
    "a set": set(range(1000)),
    "a list of whole numbers": [0] * 1000,
    "a list of floats": [1.5] * 1000,
}
WRITERS = [str, repr, lambda value: json.dumps(value, default=str)]


@pytest.mark.parametrize("what", WRITTEN)
def test_no_value_is_written_longer_than_it_was_counted(what):
    """A text that needs escaping aside: that one is sized again once it is written."""
    value = WRITTEN[what]

    counted = limits.Budget().measure(value)

    assert all(len(write(value)) <= counted for write in WRITERS)


# --- memory ---

KEEPS = """
kept = []
for n in range(100):
    kept.append("x" * 60000 + str(n))
print(len(kept))
"""
DROPS = """
last = ""
for n in range(100):
    last = "x" * 60000 + str(n)
print(len(last))
"""
ASKS = """
kept = []
for n in range(25):
    kept.append(tools.read(n=n))
print(len(kept))
"""


@pytest.fixture
def little_room(monkeypatch):
    """A megabyte to hold, measured as the process that runs a script measures it."""
    monkeypatch.setattr(limits, "MAX_LIVE_BYTES", 1024 * 1024)
    already = tracemalloc.is_tracing()
    if not already:
        tracemalloc.start()
    yield
    if not already:
        tracemalloc.stop()


def test_a_script_is_stopped_by_what_it_holds_and_not_by_what_it_made(little_room):
    assert stopped(KEEPS) == halted(4, OUT_OF_ROOM)
    assert printed(DROPS) == "60002\n"


def test_what_a_tool_answered_is_held_like_anything_else(little_room):
    asked = play(ASKS, {"read": lambda arguments: "x" * 100000 + str(arguments["n"])})

    assert asked["error"] == halted(4, OUT_OF_ROOM)
    assert 5 < len(asked["asked"]) < 15
    assert printed(ASKS, {"read": answering("short")}) == "25\n"


def test_holding_too_much_cannot_be_caught(little_room):
    ended = play(guarded(KEEPS.strip()))

    assert (ended["output"], ended["error"]) == ("", halted(5, OUT_OF_ROOM))


def test_where_nothing_measures_memory_only_the_other_limits_hold(monkeypatch):
    monkeypatch.setattr(limits, "MAX_LIVE_BYTES", 1024 * 1024)
    monkeypatch.setattr(limits.tracemalloc, "is_tracing", lambda: False)

    assert printed(KEEPS) == "100\n"


def test_memory_is_looked_at_each_time_fifty_thousand_more_were_made(little_room):
    """However they were made, a little at a time or all at once, and no more often."""
    little_by_little, at_once, again = limits.Budget(), limits.Budget(), limits.Budget()
    again.charge(50_000)
    hoard = bytearray(2 * 1024 * 1024)

    little_by_little.charge(49_999)
    with pytest.raises(limits.Halt):
        little_by_little.charge(1)
    with pytest.raises(limits.Halt):
        at_once.charge(50_000)
    again.charge(49_999)
    with pytest.raises(limits.Halt):
        again.charge(1)
    assert len(hoard) == 2 * 1024 * 1024


def test_a_script_may_hold_256_megabytes_and_not_a_byte_more(monkeypatch):
    reading = [5_000_000]
    monkeypatch.setattr(limits.tracemalloc, "is_tracing", lambda: True)
    monkeypatch.setattr(limits.tracemalloc, "get_traced_memory", lambda: (reading[0], 0))
    budget = limits.Budget()

    reading[0] = 5_000_000 + 256 * 1024 * 1024
    budget.room()
    reading[0] += 1
    with pytest.raises(limits.Halt):
        budget.room()


def test_what_was_held_before_a_script_began_is_not_counted_against_it(little_room):
    hoard = bytearray(2 * 1024 * 1024)

    assert printed('x = "a" * 60000\nprint(len(x))') == "60000\n"
    assert len(hoard) == 2 * 1024 * 1024


ROUNDS = "{setup}\nkept = []\nfor n in range(300):\n    kept.append({maker})\nprint(len(kept))"
# What each round makes, and what is set up before the first.
MADE_EACH_ROUND = {
    "a text with a value put in": ('f"' + "x" * 10000 + '{n}"', "pass"),
    "a slice": ("big[0:10000]", 'big = "x" * 20000'),
    "a list worked out item by item": ("[n for _ in range(1000)]", "pass"),
    "parts joined": ('",".join(parts)', 'parts = ["x" * 5000, "y" * 5000]'),
    "a text with letters replaced": ('big.replace("x", "y")', 'big = "x" * 10000'),
    "JSON read": ("json.loads(text)", "text = json.dumps(list(range(1000, 2000)))"),
}


@pytest.mark.parametrize("what", MADE_EACH_ROUND)
def test_whatever_makes_a_value_counts_toward_the_next_look_at_memory(little_room, what):
    """Three hundred rounds hold more than a megabyte, a few thousand characters or items
    at a time: a maker that counted nothing would never be stopped."""
    maker, setup = MADE_EACH_ROUND[what]

    assert stopped(ROUNDS.format(setup=setup, maker=maker)) == halted(4, OUT_OF_ROOM)
