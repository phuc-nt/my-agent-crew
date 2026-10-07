"""`tools.batch` as a script writes it: how a batch is asked for, what is checked before any of
it is sent, how its calls are counted, and what comes back (`script/calls.py`). Run in the
interpreter alone: the tools are the test's and a batch is made call by call. What the parent
does with a batch is in `test_script_batch_run.py`."""

from __future__ import annotations

import json
import tracemalloc

import pytest

from my_agent_crew import texts_script as t
from my_agent_crew.script import limits
from my_agent_crew.script.limits import MAX_ARGUMENT_CHARS, MAX_BATCH, MAX_CALLS, Halt, ScriptError
from tests.script_helpers import Calls, play, printed

TOO_MANY_CALLS = t.SCRIPT_TOO_MANY_CALLS.format(most=MAX_CALLS)
GOOD = '{"tool": "a"}'


def halted(line: int, reason: str) -> str:
    return t.SCRIPT_HALTED.format(line=line, reason=reason)


def answering(said: str):
    return lambda arguments: said


def failing(said: str):
    def fail(arguments):
        raise ScriptError(said)

    return fail


def refusing(reason: str):
    def refuse(arguments):
        raise Halt(reason)

    return refuse


def at(index: int) -> str:
    return t.SCRIPT_BATCH_ITEM.format(index=index)


def batch_of(*items: str) -> str:
    return f"tools.batch([{', '.join(items)}])"


def arguments_of(text: str) -> str:
    return f'{{"tool": "a", "args": {text}}}'


# --- what comes back ---


def test_a_batch_is_answered_call_by_call_in_the_order_it_was_asked():
    batches: list[Calls] = []

    ended = play(
        """
        answers = tools.batch([
            {"tool": "read", "args": {"n": 1}},
            {"tool": "read", "args": {"n": 2}},
            {"tool": "count"},
        ])
        print(json.dumps(answers))
        """,
        {"read": lambda arguments: f"trang {arguments['n']}", "count": answering("3")},
        batches=batches,
    )

    assert ended["ok"], ended["error"]
    assert json.loads(ended["output"]) == [
        {"ok": True, "output": "trang 1"},
        {"ok": True, "output": "trang 2"},
        {"ok": True, "output": "3"},
    ]
    # The three were handed over together, and a call without `args` is one with none.
    assert batches == [[("read", {"n": 1}), ("read", {"n": 2}), ("count", {})]]


def test_a_call_that_failed_is_an_answer_of_its_own_and_the_others_are_kept():
    ended = play(
        """
        answers = tools.batch([{"tool": "fine"}, {"tool": "bad"}, {"tool": "fine"}])
        print(json.dumps(answers))
        """,
        {"fine": answering("được"), "bad": failing("không được")},
    )

    assert ended["ok"], ended["error"]
    assert json.loads(ended["output"]) == [
        {"ok": True, "output": "được"},
        {"ok": False, "error": "không được"},
        {"ok": True, "output": "được"},
    ]
    assert [name for name, _ in ended["asked"]] == ["fine", "bad", "fine"]


def test_the_calls_may_be_given_by_the_name_calls():
    batches: list[Calls] = []

    ended = play(
        'print(len(tools.batch(calls=[{"tool": "a"}, {"tool": "a", "args": {"n": 2}}])))',
        {"a": answering("x")},
        batches=batches,
    )

    assert (ended["ok"], ended["output"]) == (True, "2\n")
    assert batches == [[("a", {}), ("a", {"n": 2})]]


def test_what_is_sent_is_what_json_can_carry_the_same_as_for_a_call_made_alone():
    batches: list[Calls] = []

    printed_ = play(
        'tools.batch([{"tool": "a", "args": {"pair": (1, 2), "deep": {"k": [(3, 4)]}}}])',
        {"a": answering("x")},
        batches=batches,
    )

    assert printed_["ok"], printed_["error"]
    assert batches == [[("a", {"pair": [1, 2], "deep": {"k": [[3, 4]]}})]]


def test_a_batch_may_be_as_long_as_the_most_and_not_one_call_longer():
    many = f"print(len(tools.batch([{GOOD}] * {MAX_BATCH})))"

    assert printed(many, {"a": answering("x")}) == f"{MAX_BATCH}\n"
    over = play(f"tools.batch([{GOOD}] * {MAX_BATCH + 1})", {"a": answering("x")})
    assert over["error"] == f"Lỗi ở dòng 1: {t.SCRIPT_BATCH_TOO_MANY.format(most=MAX_BATCH)}"
    assert over["asked"] == []


# --- a batch asked for the wrong way ---

WRONG_BATCHES = {
    "tools.batch()": t.SCRIPT_BATCH_USAGE,
    f"tools.batch({GOOD})": t.SCRIPT_BATCH_USAGE,
    "tools.batch([], [])": t.SCRIPT_BATCH_USAGE,
    f"tools.batch([{GOOD}], [{GOOD}])": t.SCRIPT_BATCH_USAGE,
    f"tools.batch([{GOOD}], calls=[{GOOD}])": t.SCRIPT_BATCH_USAGE,
    f"tools.batch(calls=[{GOOD}], more=1)": t.SCRIPT_BATCH_USAGE,
    f"tools.batch(requests=[{GOOD}])": t.SCRIPT_BATCH_USAGE,
    'tools.batch("a")': t.SCRIPT_BATCH_USAGE,
    "tools.batch(None)": t.SCRIPT_BATCH_USAGE,
    f"tools.batch(({GOOD},))": t.SCRIPT_BATCH_USAGE,
    'tools.batch(calls="a")': t.SCRIPT_BATCH_USAGE,
    "tools.batch([])": t.SCRIPT_BATCH_EMPTY,
    "tools.batch(calls=[])": t.SCRIPT_BATCH_EMPTY,
    f"tools.batch([{GOOD}] * {MAX_BATCH + 1})": t.SCRIPT_BATCH_TOO_MANY.format(most=MAX_BATCH),
}
# A call of the batch that is not written as one: the first such is named by its place.
BAD_CALLS = [
    "3",
    "'a'",
    "['a']",
    "{}",
    '{"args": {}}',
    '{"tool": 3}',
    '{"tool": None}',
    '{"tool": ["a"]}',
    '{"tool": "a", "arg": {}}',
    '{"tool": "a", "name": "b"}',
    '{"tool": "a", "args": []}',
    '{"tool": "a", "args": "x"}',
    '{"tool": "a", "args": None}',
    '{"tool": "a", "args": [1]}',
    '{1: "a"}',
]
WRONG_BATCHES.update({batch_of(GOOD, bad): at(1) for bad in BAD_CALLS})
WRONG_BATCHES[batch_of("3", GOOD)] = at(0)
WRONG_BATCHES[batch_of(GOOD, GOOD, "3")] = at(2)
WRONG_BATCHES[batch_of(GOOD, "3", "{}")] = at(1)
# A call that is written as one but could not be sent as it is.
TOO_LONG = t.SCRIPT_BATCH_AT.format(
    index=1, error=t.SCRIPT_ARGS_TOO_BIG.format(most=MAX_ARGUMENT_CHARS)
)
NOT_JSON = t.SCRIPT_BATCH_AT.format(index=1, error=t.SCRIPT_TOOL_ARGS_JSON)
WRONG_BATCHES[batch_of(GOOD, arguments_of(f'{{"text": "x" * {MAX_ARGUMENT_CHARS}}}'))] = TOO_LONG
WRONG_BATCHES.update(
    {
        batch_of(GOOD, arguments_of(args)): NOT_JSON
        for args in ('{"when": {1, 2}}', '{"fn": len}', "{(1, 2): 3}")
    }
)


@pytest.mark.parametrize("call", WRONG_BATCHES)
def test_a_batch_asked_for_the_wrong_way_is_a_mistake_and_nothing_is_sent(call):
    batches: list[Calls] = []

    ended = play(call, {"a": answering("x")}, batches=batches)

    assert (batches, ended["asked"]) == ([], [])
    assert ended["error"] == f"Lỗi ở dòng 1: {WRONG_BATCHES[call]}"
    caught = printed(
        f"try:\n    {call}\nexcept Exception as e:\n    print(e)", {"a": answering("x")}
    )
    assert caught == f"{WRONG_BATCHES[call]}\n"


def test_the_words_a_wrongly_asked_for_batch_is_told():
    assert t.SCRIPT_BATCH_USAGE == (
        'tools.batch nhận một list các lời gọi: tools.batch([{"tool": "TEN", "args": {...}}, ...]).'
    )
    assert at(3) == (
        'phần tử 3 của lô (đếm từ 0) phải là {"tool": "TEN", "args": {...}}: '
        "`tool` là chuỗi, `args` là dict hoặc bỏ trống, không có khoá nào khác."
    )


# --- how many calls a batch is ---

SPENDS_NONE = """
for n in range(MORE):
    try:
        CALL
    except Exception:
        pass
for n in range(MOST):
    tools.a()
print("done")
"""


@pytest.mark.parametrize("call", WRONG_BATCHES)
def test_a_batch_that_was_refused_is_none_of_the_calls(call):
    source = SPENDS_NONE.replace("MORE", str(MAX_CALLS + 5)).replace("MOST", str(MAX_CALLS))

    assert printed(source.replace("CALL", call), {"a": answering("x")}) == "done\n"


def test_each_call_of_a_batch_is_one_of_the_twenty_five():
    source = """
    tools.batch([{"tool": "a"}] * 3)
    for n in range(CALLS):
        tools.a()
    print("done")
    """
    tools = {"a": answering("x")}

    fits = play(source.replace("CALLS", str(MAX_CALLS - 3)), tools)
    over = play(source.replace("CALLS", str(MAX_CALLS - 2)), tools)

    assert (fits["ok"], fits["output"], len(fits["asked"])) == (True, "done\n", MAX_CALLS)
    assert (over["output"], over["error"]) == ("", halted(4, TOO_MANY_CALLS))
    assert len(over["asked"]) == MAX_CALLS


def test_a_call_of_a_batch_that_failed_was_still_a_call():
    source = """
    tools.batch([{"tool": "bad"}] * 5)
    for n in range(CALLS):
        tools.good()
    """
    tools = {"bad": failing("không được"), "good": answering("x")}

    fits = play(source.replace("CALLS", str(MAX_CALLS - 5)), tools)
    over = play(source.replace("CALLS", str(MAX_CALLS - 4)), tools)

    assert (fits["ok"], len(fits["asked"])) == (True, MAX_CALLS)
    assert over["error"] == halted(4, TOO_MANY_CALLS)


def test_a_batch_longer_than_the_calls_left_is_a_mistake_the_script_may_mend_and_costs_none():
    left = 5
    source = f"""
    for n in range({MAX_CALLS - left}):
        tools.a()
    try:
        tools.batch([{GOOD}] * {left + 1})
    except Exception as e:
        print(e)
    tools.batch([{GOOD}] * {left})
    print("done")
    """

    ended = play(source, {"a": answering("x")})

    said = t.SCRIPT_BATCH_ROOM.format(count=left + 1, left=left, most=MAX_CALLS)
    assert (ended["ok"], ended["output"]) == (True, f"{said}\ndone\n")
    assert len(ended["asked"]) == MAX_CALLS


def test_the_call_after_the_last_of_the_twenty_five_ends_the_script_batch_or_not():
    for call in ("tools.a()", f"tools.batch([{GOOD}])"):
        ended = play(f"for n in range({MAX_CALLS}):\n    tools.a()\n{call}", {"a": answering("x")})

        assert ended["error"] == halted(3, TOO_MANY_CALLS)
        assert len(ended["asked"]) == MAX_CALLS


def test_a_call_a_batch_may_not_make_ends_the_script_whatever_it_wrote():
    ended = play(
        """
        try:
            tools.batch([{"tool": "fine"}, {"tool": "stop"}])
        except Exception:
            print("caught")
        finally:
            print("cleanup")
        print("after")
        """,
        {"fine": answering("được"), "stop": refusing("không gọi được từ script")},
    )

    assert (ended["ok"], ended["output"]) == (False, "")
    assert ended["error"] == halted(3, "không gọi được từ script")


# --- what a batch answered is held ---


@pytest.fixture
def little_room(monkeypatch):
    """A quarter of a megabyte to hold, measured as the process that runs a script measures it."""
    monkeypatch.setattr(limits, "MAX_LIVE_BYTES", 256 * 1024)
    already = tracemalloc.is_tracing()
    if not already:
        tracemalloc.start()
    yield
    if not already:
        tracemalloc.stop()


READS = (
    'answers = tools.batch([{{"tool": "read", "args": {{"n": n}}}} for n in range({count})])\n'
    "print(len(answers))"
)


def test_what_a_batch_answered_is_held_like_anything_else(little_room):
    """Each answer is too little to make the script look at what it holds; together they are
    not, and it is looked at once they are all there."""
    reads = {"read": lambda arguments: "x" * 40_000 + str(arguments["n"])}

    held = play(READS.format(count=10), reads)

    assert held["error"] == halted(1, t.SCRIPT_OUT_OF_ROOM)
    assert len(held["asked"]) == 10
    assert printed(READS.format(count=2), reads) == "2\n"


# --- the example the model is shown ---


def test_the_example_the_model_is_shown_runs_as_written():
    batches: list[Calls] = []

    ended = play(
        t.SCRIPT_BATCH_EXAMPLE,
        {"TEN": lambda arguments: f"kết quả {arguments['id']}"},
        batches=batches,
    )

    assert (ended["ok"], ended["output"]) == (True, "kết quả 1\nkết quả 2\nkết quả 3\n")
    assert batches == [[("TEN", {"id": 1}), ("TEN", {"id": 2}), ("TEN", {"id": 3})]]
