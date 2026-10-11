"""How much a script may do: its steps, its values, what it prints, its calls, its memory,
and what it may keep for a later run.

Each limit is tried from both sides: what stays inside it runs to its end, and what goes
past it stops with the line that says which limit that was. The limits a script cannot
catch are tried under a `try` as well, and a `finally` that must not run is there to run.
"""

from __future__ import annotations

import json
import tracemalloc
from functools import partial
from typing import Any

import pytest

from my_agent_crew import texts_script_store as kept_texts
from my_agent_crew.script import limits
from my_agent_crew.script.kept import KINDS
from my_agent_crew.script.limits import MAX_OUTPUT_CHARS, ScriptError
from my_agent_crew.script.printed import Printed
from my_agent_crew.script.store_session import Kept
from my_agent_crew.store.script_store import ScriptStore
from tests.script_helpers import play, printed, stopped

OUT_OF_ROOM = "script tạo ra quá nhiều dữ liệu. Lọc bớt trước khi gom lại."
OUT_OF_STEPS = "script chạy quá 300 bước. Xử lý ít dữ liệu hơn hoặc bỏ vòng lặp thừa."
TOO_NESTED = "dữ liệu lồng nhau quá sâu hoặc quá nhiều phần tử để viết ra."
LEFT_OUT = (
    "\n…[script in ra {total} ký tự, bỏ {dropped} ký tự ở giữa. "
    "Chỉ in phần cần, đã gộp hoặc lọc.]…\n"
)
TOO_MANY_CALLS = "Script đã dùng quá 25 lời gọi. Gộp việc lại hoặc chia nhiều script."
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


def test_a_script_prints_sixty_thousand_characters_whole():
    assert printed('print("x" * 59999)') == "x" * 59999 + "\n"
    # Whole too where it was printed in pieces that fall on both sides of what is kept
    # of the start.
    pieces = 'print("a" * 44990)\nprint("b" * 20)\nprint("c" * 14987)'
    assert printed(pieces) == "a" * 44990 + "\n" + "b" * 20 + "\n" + "c" * 14987 + "\n"


def test_a_script_that_prints_more_keeps_the_start_and_the_end_and_says_what_it_left_out():
    ended = play('print("a" * 50000)\nprint("b" * 30000)\nprint("tổng: 42")')

    note = LEFT_OUT.format(total=80011, dropped=20099)
    assert ended == {
        "ok": True,
        "output": "a" * 45000 + note + "b" * 14902 + "\ntổng: 42\n",
        "error": None,
        "asked": [],
    }
    # Three parts in four of the most are the start, and the line that says what was left
    # out is paid for out of the end: 45,000 kept, 20,099 left out, 14,912 kept.
    assert 45000 + 20099 + 14902 + len("\ntổng: 42\n") == 80011
    assert len(ended["output"]) == 60000


def test_one_character_past_the_most_is_already_more():
    whole = "x" * 60000 + "\n"

    said = printed('print("x" * 60000)')

    note = LEFT_OUT.format(total=60001, dropped=89)
    assert said == "x" * 45000 + note + "x" * 14911 + "\n"
    assert whole.startswith(said.split(note)[0]) and whole.endswith(said.split(note)[1])
    # The line is sized for the widest it could be, so the whole falls a little short.
    assert len(said) == 59997


def test_a_script_that_prints_line_after_line_keeps_its_first_lines_and_its_last():
    lines = "".join(f"{n} {'x' * 100}\n" for n in range(5000))

    said = printed('for n in range(5000):\n    print(n, "x" * 100)')

    start, end = said.split("\n…[script in ra ")[0], said.split("ở giữa. Chỉ in phần cần")[1]
    end = end.split("]…\n", 1)[1]
    assert len(start) == 45000 and lines.startswith(start)
    assert lines.endswith(end) and end.endswith("4999 " + "x" * 100 + "\n")
    dropped = len(lines) - len(start) - len(end)
    assert said == start + LEFT_OUT.format(total=len(lines), dropped=dropped) + end
    assert 59990 <= len(said) <= 60000


def test_printing_more_than_is_kept_does_not_end_the_script():
    ended = play(guarded('print("x" * 70000)'))

    assert ended["ok"] and ended["error"] is None
    assert ended["output"].startswith("x" * 45000 + "\n…[script in ra 70015 ký tự, bỏ 10103 ")
    assert ended["output"].endswith("x\ncleanup\nafter\n") and "caught" not in ended["output"]


def test_a_script_that_prints_without_end_is_stopped_by_its_steps_with_both_ends_kept(
    monkeypatch,
):
    monkeypatch.setattr(limits, "MAX_STEPS", 300)

    ended = play('n = 0\nwhile True:\n    n = n + 1\n    print(n, "y" * 5000)')

    assert (ended["ok"], ended["error"]) == (False, halted(4, OUT_OF_STEPS))
    said = ended["output"]
    assert said.startswith("1 " + "y" * 5000 + "\n2 ") and said.endswith("y" * 5000 + "\n")
    assert "\n…[script in ra " in said and 59990 <= len(said) <= 60000


def test_however_much_is_printed_little_more_than_the_most_is_held():
    said, most = Printed(), 0
    pieces = ["x" * 7000] * 1000 + ["y" * 500_000] + ["z"] * 40_000 + ["w" * 14_999, "v"]

    for piece in pieces:
        said.write(piece)
        most = max(most, said.held)

    assert said.total == 7_555_000
    # The start, and of the end no more than twice what is kept of it.
    assert MAX_OUTPUT_CHARS < most < MAX_OUTPUT_CHARS * 5 // 4
    assert said.text().endswith("w" * 14_900 + "v") and "z" not in said.text()
    assert MAX_OUTPUT_CHARS - 10 < len(said.text()) <= MAX_OUTPUT_CHARS


def test_the_value_of_the_last_line_counts_as_printed():
    note = LEFT_OUT.format(total=60001, dropped=89)
    assert printed('"x" * 60000') == "x" * 45000 + note + "x" * 14911 + "\n"
    assert printed('"x" * 59999') == "x" * 59999 + "\n"


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


def test_a_script_that_prints_far_more_than_is_kept_is_not_ended_for_what_it_holds(little_room):
    ended = play('for n in range(1600):\n    print(str(n) + "x" * 5000)')  # eight megabytes

    assert ended["ok"] and ended["error"] is None
    assert ended["output"].startswith("0xxx")
    assert ended["output"].endswith("x\n1599" + "x" * 5000 + "\n")


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


# --- what a script keeps from one run to the next ---

AGENT, PLACE = "a", "conv:c"
CAUGHT = """
try:
    {line}
except Exception as e:
    print(e)
"""


@pytest.fixture
def table(store) -> ScriptStore:
    return store.script_store


def keeping(table: ScriptStore) -> tuple[Kept, dict[str, Any]]:
    """One run's view of one place, and the two questions a script puts to it."""
    kept = Kept(table, AGENT, PLACE)
    return kept, {kind: partial(kept.answer, kind) for kind in KINDS}


def mistaken(line: int, said: str) -> str:
    return f"Lỗi ở dòng {line}: {said}"


def test_a_key_is_a_text_as_long_as_a_key_may_be_and_no_longer(table):
    most = limits.MAX_STORE_KEY_CHARS
    kept, asks = keeping(table)
    bad = mistaken(1, kept_texts.STORE_BAD_KEY.format(most=most))

    assert printed(f'store("k" * {most}, 1)\nprint(load("k" * {most}))', lookups=asks) == "1\n"
    for line in (
        f'store("k" * {most + 1}, 1)',
        f'load("k" * {most + 1})',
        'store("", 1)',
        'load("")',
        "store(7, 1)",
        "load(None)",
        'store(["k"], 1)',
        # Dropping a key is still naming one.
        f'store("k" * {most + 1}, None)',
    ):
        assert stopped(line, lookups=asks) == bad, line
    assert printed(guarded('store("", 1)'), lookups=asks) == "caught\ncleanup\nafter\n"
    assert kept.commit() is None and table.read(AGENT, PLACE) == {"k" * most: "1"}


def test_a_value_is_as_long_as_one_may_be_and_no_longer_and_the_one_too_long_is_not_kept(table):
    """Two of its characters are the quotes a text is written in."""
    most = limits.MAX_STORE_VALUE_CHARS
    kept, asks = keeping(table)
    too_long = kept_texts.STORE_VALUE_TOO_LONG.format(size=most + 1, most=most)

    said = printed(
        f'store("k", "x" * {most - 2})\n'
        + CAUGHT.format(line=f'store("k", "y" * {most - 1})')
        + 'print(len(load("k")), load("k")[:3])',
        lookups=asks,
    )

    # The script was told, went on, and reads the value it had before the one refused.
    assert said == f"{too_long}\n{most - 2} xxx\n"
    assert kept.commit() is None and table.read(AGENT, PLACE) == {"k": f'"{"x" * (most - 2)}"'}
    assert stopped(f'store("k", "y" * {most - 1})', lookups=asks) == mistaken(1, too_long)


def test_a_value_is_measured_as_the_json_it_is_kept_as(table):
    """By the character, so a letter of the owner's language is one like any other; and as
    it is written, so a line end, which JSON writes as two, is two."""
    most = limits.MAX_STORE_VALUE_CHARS
    kept, asks = keeping(table)
    escaped = kept_texts.STORE_VALUE_TOO_LONG.format(size=2 * (most - 2) + 2, most=most)

    assert printed(f'store("k", "đ" * {most - 2})\nprint(len(load("k")))', lookups=asks) == (
        f"{most - 2}\n"
    )
    assert stopped(f'store("n", "\\n" * {most - 2})', lookups=asks) == mistaken(1, escaped)
    assert kept.commit() is None and table.read(AGENT, PLACE) == {"k": f'"{"đ" * (most - 2)}"'}


NOT_JSON = [
    "{1, 2}",
    'float("nan")',
    'float("inf")',
    '[1, {"a": {1, 2}}]',
    # JSON would write each of these keys as a text, and the script would read back a key
    # it never wrote.
    "{1: 2}",
    "{True: 1}",
    "{None: 1}",
    "{(1, 2): 3}",
    '[{"a": [{"b": {2: 1}}]}]',
]


@pytest.mark.parametrize("value", NOT_JSON)
def test_a_value_that_is_not_json_is_a_mistake_the_script_may_catch(table, value):
    kept, asks = keeping(table)

    assert stopped(f'store("k", {value})', lookups=asks) == mistaken(1, kept_texts.STORE_NOT_JSON)
    said = printed(guarded(f'store("k", {value})') + 'print(load("k"))', lookups=asks)
    assert said == "caught\ncleanup\nafter\nNone\n"
    assert kept.commit() is None and table.read(AGENT, PLACE) == {}


def test_what_json_can_write_is_read_back_as_it_was_written(table):
    kept, asks = keeping(table)
    value = '{"1": 2, "đã nhắc": ["HP3", 1.5, True, None, {"sâu": []}], "": (1, 2)}'

    said = printed(f'store("k", {value})\nprint(load("k"))', lookups=asks)

    # All but the tuple, which JSON has no word for and writes as a list.
    assert said == "{'1': 2, 'đã nhắc': ['HP3', 1.5, True, None, {'sâu': []}], '': [1, 2]}\n"
    assert kept.commit() is None
    assert table.read(AGENT, PLACE) == {
        "k": '{"1":2,"đã nhắc":["HP3",1.5,true,null,{"sâu":[]}],"":[1,2]}'
    }


@pytest.fixture
def small_place(monkeypatch) -> int:
    monkeypatch.setattr(limits, "MAX_STORE_TOTAL_CHARS", 100)
    return 100


def test_a_place_holds_its_keys_and_values_up_to_the_most_and_not_a_character_more(
    table, small_place
):
    """Counted as what the place would hold once the write was made: a value written in
    place of another gives the other's room back, and so does a key dropped."""
    assert table.apply(AGENT, PLACE, {"old": json.dumps("o" * 40)}, small_place)  # 3 + 42
    kept, asks = keeping(table)
    full = kept_texts.STORE_FULL

    said = printed(
        'store("new", "n" * 50)\n'  # 3 + 52 more: the hundred
        + CAUGHT.format(line='store("x", 1)')
        + 'print(load("x"))\n'
        + 'store("old", "p" * 40)\n'  # in place of one as long: the hundred still
        + CAUGHT.format(line='store("old", "q" * 41)')
        + 'print(load("old")[:3], len(load("old")))\n'
        + 'store("new", None)\n'
        + 'store("x", 1)\n'
        + 'print(load("x"), load("new"))',
        lookups=asks,
    )

    assert said.splitlines() == [
        full.format(size=102, most=100),
        "None",
        full.format(size=101, most=100),
        "ppp 40",
        "1 None",
    ]
    assert kept.commit() is None
    assert table.read(AGENT, PLACE) == {"old": json.dumps("p" * 40), "x": "1"}


def test_a_place_that_is_full_still_lets_a_key_go(table, small_place):
    assert table.apply(AGENT, PLACE, {"k" * 49: json.dumps("v" * 49)}, small_place)
    kept, asks = keeping(table)

    said = printed(
        CAUGHT.format(line='store("x", 1)') + f'store("{"k" * 49}", None)\nstore("x", 1)',
        lookups=asks,
    )

    assert said == kept_texts.STORE_FULL.format(size=102, most=100) + "\n"
    assert kept.commit() is None and table.read(AGENT, PLACE) == {"x": "1"}


def test_another_place_and_another_agent_take_none_of_the_room(table, small_place):
    assert table.apply(AGENT, "job:due", {"k": json.dumps("v" * 90)}, small_place)
    assert table.apply("coach", PLACE, {"k": json.dumps("v" * 90)}, small_place)
    kept, asks = keeping(table)

    assert printed('store("k", "v" * 97)\nprint(load("k")[:2])', lookups=asks) == "vv\n"
    assert kept.commit() is None and len(table.read(AGENT, PLACE)["k"]) == 99


def test_what_cannot_be_kept_is_turned_away_before_it_is_asked_for():
    """By the process that runs the script, which is asked for nothing it would refuse: a
    value the line to the server cannot carry would end the process, where this is a
    mistake the script may catch."""
    asked: list[dict[str, Any]] = []
    asks = {kind: asked.append for kind in KINDS}

    for line in (
        f'store("k" * {limits.MAX_STORE_KEY_CHARS + 1}, 1)',
        f'load("k" * {limits.MAX_STORE_KEY_CHARS + 1})',
        f'store("k", "x" * {limits.MAX_STORE_VALUE_CHARS - 1})',
        'store("k", {1, 2})',
        'store("k", {1: 2})',
    ):
        assert printed(guarded(line), lookups=asks) == "caught\ncleanup\nafter\n", line
    assert asked == []


BAD_ASKS = [
    ("store", {"key": "", "value": 1}),
    ("store", {"value": 1}),
    ("store", {"key": 3, "value": 1}),
    ("store", {"key": "k" * (limits.MAX_STORE_KEY_CHARS + 1), "value": 1}),
    ("store", {"key": "k" * (limits.MAX_STORE_KEY_CHARS + 1), "value": None}),
    ("store", {"key": "k", "value": "x" * (limits.MAX_STORE_VALUE_CHARS - 1)}),
    ("store", {"key": "k", "value": float("nan")}),
    ("store", {"key": "k", "value": {1: 2}}),
    ("load", {"key": ""}),
    ("load", {}),
    ("load", {"key": "k" * (limits.MAX_STORE_KEY_CHARS + 1)}),
]


@pytest.mark.parametrize(("kind", "arguments"), BAD_ASKS)
def test_the_server_measures_again_whatever_the_process_asked(table, kind, arguments):
    """Nothing the process sends is taken on trust for having been checked there."""
    kept = Kept(table, AGENT, PLACE)

    with pytest.raises(ScriptError):
        kept.answer(kind, arguments)

    assert kept.commit() is None and table.read(AGENT, PLACE) == {}


def test_the_server_refuses_what_would_fill_the_place_whoever_measured_before(table, small_place):
    kept = Kept(table, AGENT, PLACE)
    kept.answer("store", {"key": "a", "value": "x" * 97})  # 1 + 99

    with pytest.raises(ScriptError) as refused:
        kept.answer("store", {"key": "b", "value": 1})

    assert str(refused.value) == kept_texts.STORE_FULL.format(size=102, most=100)
    assert kept.commit() is None and list(table.read(AGENT, PLACE)) == ["a"]


@pytest.mark.parametrize(
    "line",
    ['store("k")', 'store("k", 1, 2)', 'store(key="k", value=1)', "store()"],
)
def test_store_takes_a_key_and_a_value_and_nothing_else(table, line):
    kept, asks = keeping(table)

    assert stopped(line, lookups=asks) == mistaken(1, "gọi hàm `store` sai tham số.")
    assert kept.commit() is None and table.read(AGENT, PLACE) == {}


@pytest.mark.parametrize("line", ["load()", 'load("k", 1)', 'load(key="k")'])
def test_load_takes_a_key_and_nothing_else(table, line):
    _, asks = keeping(table)

    assert stopped(line, lookups=asks) == mistaken(1, "gọi hàm `load` sai tham số.")


def test_store_answers_nothing_and_load_of_a_key_never_kept_is_none(table):
    _, asks = keeping(table)

    assert printed('print(store("k", 0), load("k"), load("never"))', lookups=asks) == (
        "None 0 None\n"
    )


def test_what_a_script_keeps_or_reads_back_is_none_of_its_calls_or_its_lookups(table):
    """A script that remembers many things still has every call and lookup it came with."""
    kept, asks = keeping(table)
    many = limits.MAX_CALLS + limits.MAX_LOOKUPS + 1
    source = f"""
        for n in range({many}):
            store("k" + str(n), n)
            load("k" + str(n))
        for n in range({limits.MAX_LOOKUPS}):
            tools.names()
        for n in range({limits.MAX_CALLS}):
            tools.read()
        print("all spent")
    """

    said = printed(source, {"read": answering("ok")}, {**asks, "names": lambda arguments: []})

    assert said == "all spent\n"
    assert kept.commit() is None and len(table.read(AGENT, PLACE)) == many


# --- what a script asks a model ---

TOO_MANY_QUESTIONS = "Script đã hỏi model quá 10 lần. Gộp việc lại hoặc chia nhiều script."
CLASSIFY = "`llm.classify(text, labels)`: "
SUMMARISE = "`llm.summarise(text, max_chars=500)`: "
WRONG_ARGUMENTS = "tham số sai."
BAD_TEXT = "`text` phải là một chuỗi không rỗng."
TEXT_TOO_LONG = (
    "`text` dài 20001 ký tự, quá 20000: tự cắt bớt hoặc chia nhỏ trong script trước khi gọi."
)
BAD_LABELS = (
    "`labels` phải là list gồm 2 đến 20 chuỗi khác nhau, không rỗng, mỗi chuỗi dài "
    "tối đa 100 ký tự."
)
BAD_MAX_CHARS = "`max_chars` phải là số nguyên từ 1 đến 4000."
SORT = 'llm.classify("mua ngay", ["rác", "thường"])'


def a_model(said: str = "rác") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """A model that answers every question alike, and what it was asked."""
    asked: list[dict[str, Any]] = []

    def answer(arguments: dict[str, Any]) -> str:
        asked.append(arguments)
        return said

    return asked, {"llm": answer}


def test_a_script_asks_a_model_ten_times_and_not_once_more():
    asked, model = a_model()

    assert printed(f'for n in range(10):\n    {SORT}\nprint("done")', lookups=model) == "done\n"
    assert len(asked) == 10

    asked.clear()
    over = play(f'print("before")\nfor n in range(40):\n    {SORT}\nprint("done")', lookups=model)

    assert (over["output"], over["error"]) == ("before\n", halted(3, TOO_MANY_QUESTIONS))
    assert len(asked) == 10


def test_one_question_too_many_for_a_model_cannot_be_caught():
    asked, model = a_model()

    ended = play(guarded(f"for n in range(11):\n    {SORT}"), lookups=model)

    assert (ended["output"], ended["error"]) == ("", halted(4, TOO_MANY_QUESTIONS))
    assert len(asked) == 10


def test_summaries_and_sortings_are_counted_together():
    asked, model = a_model()
    source = f'for n in range(6):\n    {SORT}\n    llm.summarise("dài lắm")'

    assert stopped(source, lookups=model) == halted(2, TOO_MANY_QUESTIONS)
    assert [question["name"] for question in asked] == ["classify", "summarise"] * 5


def test_a_question_a_model_failed_was_still_one_asked():
    source = f"""
        failed = 0
        for n in range(30):
            try:
                {SORT}
            except Exception:
                failed += 1
    """

    assert stopped(source, lookups={"llm": failing("no")}) == halted(5, TOO_MANY_QUESTIONS)


def test_a_question_for_a_model_is_one_of_the_scripts_twenty_five_calls():
    """Whichever the call past the count is, a tool's or a model's, the script ends on it."""
    asked, model = a_model()
    reads = "for n in range({reads}):\n    tools.read(n=n)\n"
    asks = f"for n in range({{asks}}):\n    {SORT}\n"
    read = {"read": answering("x")}

    fits = reads.format(reads=16) + asks.format(asks=9) + 'print("done")'
    assert printed(fits, read, model) == "done\n"

    asked.clear()
    a_question_over = play(reads.format(reads=17) + asks.format(asks=9), read, model)
    assert a_question_over["error"] == halted(4, TOO_MANY_CALLS)
    assert (len(a_question_over["asked"]), len(asked)) == (17, 8)

    asked.clear()
    a_read_over = play(asks.format(asks=9) + reads.format(reads=17), read, model)
    assert a_read_over["error"] == halted(4, TOO_MANY_CALLS)
    assert (len(a_read_over["asked"]), len(asked)) == (16, 9)


def test_a_question_for_a_model_takes_room_from_a_batch():
    asked, model = a_model()
    batch = 'tools.batch([{{"tool": "read"}}] * {count})'
    source = (
        f"for n in range(9):\n    {SORT}\n"
        + "for n in range(12):\n    tools.read(n=n)\n"
        + CAUGHT.format(line=batch.format(count=5))
        + batch.format(count=4)
        + '\nprint("done")'
    )

    said = play(source, {"read": answering("x")}, model)

    room = "lô có 5 lời gọi mà script chỉ còn gọi được 4 trong 25 lần: bỏ bớt hoặc chia nhỏ lô."
    assert (said["error"], said["output"]) == (None, f"{room}\ndone\n")
    assert (len(asked), len(said["asked"])) == (9, 16)


def test_a_text_for_a_model_is_twenty_thousand_characters_and_not_one_more():
    """One too long is the script's to cut: which part of it matters no limit can say, so
    it is never cut on the way."""
    most = limits.MAX_LLM_TEXT_CHARS
    asked, model = a_model()

    assert most == 20_000
    assert printed(f'print(llm.classify("x" * {most}, ["a", "b"]))', lookups=model) == "rác\n"
    assert printed(f'print(llm.summarise("x" * {most}))', lookups=model) == "rác\n"
    assert [len(question["text"]) for question in asked] == [most, most]

    asked.clear()
    for line, shape in (
        (f'llm.classify("x" * {most + 1}, ["a", "b"])', CLASSIFY),
        (f'llm.summarise("x" * {most + 1})', SUMMARISE),
        (f'llm.summarise("x" * {most + 1}, max_chars=10)', SUMMARISE),
    ):
        assert stopped(line, lookups=model) == mistaken(1, shape + TEXT_TOO_LONG), line
        assert printed(guarded(line), lookups=model) == "caught\ncleanup\nafter\n", line
    assert asked == []


@pytest.mark.parametrize("text", ['""', '"  \\n "', "7", "None", '["mua ngay"]', '{"text": "x"}'])
def test_what_is_put_to_a_model_is_a_text_with_something_in_it(text):
    asked, model = a_model()

    for line, shape in (
        (f'llm.classify({text}, ["a", "b"])', CLASSIFY),
        (f"llm.summarise({text})", SUMMARISE),
    ):
        assert stopped(line, lookups=model) == mistaken(1, shape + BAD_TEXT), line
    assert asked == []


GOOD_LABELS = {
    "two": '["a", "b"]',
    "twenty": "[str(n) for n in range(20)]",
    "one a hundred characters long": '["a" * 100, "b"]',
    "a tuple": '("a", "b")',
    "told apart by their accents": '["ma", "má", "mà"]',
}
BAD_LABEL_LISTS = {
    "none": "[]",
    "one": '["a"]',
    "twenty-one": "[str(n) for n in range(21)]",
    "one a hundred and one characters long": '["a" * 101, "b"]',
    "the same twice": '["a", "b", "a"]',
    "the same but for its case": '["Rác", "rác"]',
    "the same but for its spacing": '["hoá  đơn", " hoá đơn "]',
    # One letter with its accent, and the same letter followed by the accent alone.
    "the same but for how its accent was typed": '["\\u00e1", "a\\u0301"]',
    "an empty one": '["a", ""]',
    "a blank one": '["a", "   "]',
    "a number among them": '["a", 7]',
    "a text and not a list": '"a,b"',
    "a dict": '{"a": 1, "b": 2}',
    "nothing": "None",
}


@pytest.mark.parametrize("labels", GOOD_LABELS.values(), ids=GOOD_LABELS.keys())
def test_labels_within_what_a_script_may_give_are_put_to_the_model(labels):
    asked, model = a_model("a")

    assert printed(f'print(llm.classify("x", {labels}))', lookups=model) == "a\n"
    assert type(asked[0]["labels"]) is list and len(asked) == 1


@pytest.mark.parametrize("labels", BAD_LABEL_LISTS.values(), ids=BAD_LABEL_LISTS.keys())
def test_labels_are_two_to_twenty_short_texts_no_two_alike(labels):
    asked, model = a_model()
    line = f'llm.classify("x", {labels})'

    assert stopped(line, lookups=model) == mistaken(1, CLASSIFY + BAD_LABELS)
    assert printed(guarded(line), lookups=model) == "caught\ncleanup\nafter\n"
    assert asked == []


def test_a_summary_is_asked_for_in_one_to_four_thousand_characters_and_five_hundred_unsaid():
    asked, model = a_model()
    most = limits.MAX_LLM_SUMMARY_CHARS

    for line in (
        'llm.summarise("x")',
        'llm.summarise("x", 1)',
        f'llm.summarise("x", max_chars={most})',
    ):
        assert printed(line, lookups=model) == "rác\n", line
    assert [question["max_chars"] for question in asked] == [500, 1, 4000]

    asked.clear()
    for wrong in ("0", "-5", str(most + 1), '"40"', "40.0", "True", "None", "[40]"):
        line = f'llm.summarise("x", max_chars={wrong})'
        assert stopped(line, lookups=model) == mistaken(1, SUMMARISE + BAD_MAX_CHARS), line
    assert asked == []


WRONGLY_WRITTEN = [
    ("llm.classify()", CLASSIFY),
    ('llm.classify("x")', CLASSIFY),
    ('llm.classify(labels=["a", "b"])', CLASSIFY),
    ('llm.classify("x", ["a", "b"], 3)', CLASSIFY),
    ('llm.classify("x", ["a", "b"], max_chars=3)', CLASSIFY),
    ('llm.classify("x", text="y", labels=["a", "b"])', CLASSIFY),
    # Which of the two is asked is the name it was called by, never an argument.
    ('llm.classify("x", ["a", "b"], name="summarise")', CLASSIFY),
    ("llm.summarise()", SUMMARISE),
    ("llm.summarise(max_chars=40)", SUMMARISE),
    ('llm.summarise("x", 40, 50)', SUMMARISE),
    ('llm.summarise("x", labels=["a", "b"])', SUMMARISE),
    ('llm.summarise("x", 40, max_chars=50)', SUMMARISE),
]


@pytest.mark.parametrize(("line", "shape"), WRONGLY_WRITTEN)
def test_a_question_written_wrongly_says_how_it_is_written(line, shape):
    asked, model = a_model()

    assert stopped(line, lookups=model) == mistaken(1, shape + WRONG_ARGUMENTS)
    assert asked == []


def test_a_model_is_asked_in_two_ways_and_no_other():
    asked, model = a_model()

    for line in ('llm.translate("x")', 'llm.batch(["x"])', "llm.names()", 'llm.name("x")'):
        assert stopped(line, lookups=model) == mistaken(1, "llm chỉ có `classify` và `summarise`.")
    # Not a value a script can hold or hand on, any more than `tools` is.
    for line in ("x = llm", "print(llm)", "[llm]"):
        assert stopped(line, lookups=model) == mistaken(1, "`llm` chỉ dùng để gọi: `llm.TEN(...)`.")
    assert not play("ask = llm.classify", lookups=model)["ok"]
    assert asked == []


def test_a_question_never_put_is_counted_as_neither_kind_of_call():
    asked, model = a_model()
    source = f"""
        for n in range(30):
            for wrong in (["a"], "a,b", ["a", "a"]):
                try:
                    llm.classify("x", wrong)
                except Exception:
                    pass
            try:
                llm.summarise("x" * {limits.MAX_LLM_TEXT_CHARS + 1})
            except Exception:
                pass
        for n in range(10):
            {SORT}
        for n in range(15):
            tools.read(n=n)
        print("done")
    """

    said = play(source, {"read": answering("x")}, model)

    assert (said["error"], said["output"]) == (None, "done\n")
    assert (len(asked), len(said["asked"])) == (10, 15)


def test_the_counts_of_what_a_model_is_asked_are_the_ones_the_owner_was_told():
    """Each is said to the model that writes scripts and in the docs: a change here is a
    change there."""
    assert (limits.MAX_LLM_CALLS, limits.MAX_LLM_TEXT_CHARS) == (10, 20_000)
    assert (limits.MIN_LLM_LABELS, limits.MAX_LLM_LABELS, limits.MAX_LLM_LABEL_CHARS) == (
        2,
        20,
        100,
    )
    assert (limits.LLM_SUMMARY_CHARS, limits.MAX_LLM_SUMMARY_CHARS) == (500, 4_000)
