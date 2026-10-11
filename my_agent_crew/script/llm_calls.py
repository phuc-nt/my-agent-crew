"""What a script asks a model itself: `llm.classify(text, labels)` and
`llm.summarise(text, max_chars=...)`.

Some of what a script sorts through no code can judge: which of a few kinds a message is,
what a long answer comes to. For that it asks a model, and gets one text back. The asking is
a question put to the parent, as a lookup is (`replies.py`): the parent holds the model and
its key, makes the call and answers (`model_calls.py`). Nothing of the model reaches the
process but that one text.

This module is the part both sides read: the process that runs the script, and the server
that answers it. What a text, the labels and a length must be is said once, here. The process
checks before it asks, so a call written wrongly is a mistake the script can catch and costs
it nothing; the server checks again, since nothing the process sends is taken on trust for
having been checked there.

Each asking is one of the script's calls (`MAX_CALLS`), and one of the fewer it may put to a
model (`MAX_LLM_CALLS`), however it ends.
"""

from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_script as t
from my_agent_crew import texts_script_llm as words
from my_agent_crew.script import limits
from my_agent_crew.script.limits import Halt, ScriptError

if TYPE_CHECKING:
    from my_agent_crew.script.machine import Machine

# The kind of question this is, among those a script puts to the parent.
LLM = "llm"
CLASSIFY, SUMMARISE = "classify", "summarise"
# What each is called with, in the order it is written.
PARAMS: dict[str, tuple[str, ...]] = {
    CLASSIFY: ("text", "labels"),
    SUMMARISE: ("text", "max_chars"),
}
# Which of the two a question is, beside what it is asked with.
NAME = "name"


def plain(label: str) -> str:
    """A label as it is compared: whatever its case, its spacing, and the way its accents
    were typed. A letter of the owner's language has two spellings that look the same."""
    return unicodedata.normalize("NFC", " ".join(label.split())).casefold()


def _wrong(name: str, wrong: str) -> ScriptError:
    """A call that cannot be made as written: how it is written, then what was wrong."""
    shape = (
        words.LLM_CLASSIFY
        if name == CLASSIFY
        else words.LLM_SUMMARISE.format(default=limits.LLM_SUMMARY_CHARS)
    )
    return ScriptError(words.LLM_USAGE.format(shape=shape, wrong=wrong))


def _text(name: str, text: Any) -> str:
    """Measured before it is read: a text far too long is turned away for its length alone."""
    most = limits.MAX_LLM_TEXT_CHARS
    if type(text) is str and len(text) > most:
        raise _wrong(name, words.LLM_TEXT_TOO_LONG.format(size=len(text), most=most))
    if type(text) is not str or not text.strip():
        raise _wrong(name, words.LLM_BAD_TEXT)
    return text


def _labels(labels: Any) -> list[str]:
    """Told apart as they are compared, so no answer can be two of them at once."""
    least, most = limits.MIN_LLM_LABELS, limits.MAX_LLM_LABELS
    chars = limits.MAX_LLM_LABEL_CHARS
    fits = (
        type(labels) in (list, tuple)
        and least <= len(labels) <= most
        and all(type(label) is str and len(label) <= chars and plain(label) for label in labels)
        and len({plain(label) for label in labels}) == len(labels)
    )
    if not fits:
        raise _wrong(CLASSIFY, words.LLM_BAD_LABELS.format(least=least, most=most, chars=chars))
    return list(labels)


def _max_chars(asked: Any) -> int:
    most = limits.MAX_LLM_SUMMARY_CHARS
    if type(asked) is not int or not 1 <= asked <= most:
        raise _wrong(SUMMARISE, words.LLM_BAD_MAX_CHARS.format(most=most))
    return asked


def checked(arguments: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Which of the two is asked for, and what with, as it is sent, shown and put to the
    model; or a `ScriptError` that says how the call is written."""
    name = arguments.get(NAME)
    if type(name) is not str or name not in PARAMS:
        raise ScriptError(words.LLM_NO_SUCH)
    given = {key: value for key, value in arguments.items() if key != NAME}
    needed = {"text"} if name == SUMMARISE else set(PARAMS[name])
    if not needed <= given.keys() <= set(PARAMS[name]):
        raise _wrong(name, words.LLM_WRONG_ARGUMENTS)
    text = _text(name, given["text"])
    if name == CLASSIFY:
        return name, {"text": text, "labels": _labels(given["labels"])}
    most = _max_chars(given.get("max_chars", limits.LLM_SUMMARY_CHARS))
    return name, {"text": text, "max_chars": most}


def call_model(machine: Machine, name: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
    """`llm.NAME(...)` as a script writes it: checked, counted, asked of the parent, and the
    answer handed back. A call past either count ends the script, as one call too many of
    any kind does; one that was never sent is counted as neither."""
    params = PARAMS.get(name)
    if params is None:
        raise ScriptError(words.LLM_NO_SUCH)
    asked = {**dict(zip(params, args, strict=False)), **kwargs}
    # Each parameter given once, and only this call's own.
    if len(args) > len(params) or len(asked) != len(args) + len(kwargs) or NAME in asked:
        raise _wrong(name, words.LLM_WRONG_ARGUMENTS)
    name, asked = checked({NAME: name, **asked})
    budget = machine.budget
    if budget.model_calls >= limits.MAX_LLM_CALLS:
        raise Halt(words.LLM_TOO_MANY_CALLS.format(most=limits.MAX_LLM_CALLS))
    if budget.calls >= limits.MAX_CALLS:
        raise Halt(t.SCRIPT_TOO_MANY_CALLS.format(most=limits.MAX_CALLS))
    budget.model_calls += 1
    budget.calls += 1
    return budget.made(machine.ask(LLM, {NAME: name, **asked}))
