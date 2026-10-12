"""A script's own model calls, made here for it and kept as calls of the script.

The process that runs a script holds no key and reaches no network. It asks (`replies.py`)
and the server answers: with the agent's own model, on the first of its routes and no other,
offered no tool. The process is handed the answer as a text and nothing else of the call.

Each asking is one nested call of the script, like a tool it called: it takes one from what
the scripts of the turn may make between them, is listed on the run card with what it cost,
and is told to the turn the moment it ends, which is where its cost reaches the run and the
conversation (`agent/nested_calls.py`). The ledger hears of it as a side call made for a
script (`llm/metered_chain.py`). It is never one the approval gate is asked about: it changes
nothing.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_script as t
from my_agent_crew import texts_script_llm as words
from my_agent_crew.activity.step_previews import argument_preview, failure_preview, preview
from my_agent_crew.agent.nested_calls import nested_budget, note_nested_call
from my_agent_crew.agents.profile_settings import REASONING_EFFORTS
from my_agent_crew.llm.metered_chain import MeteredChain
from my_agent_crew.llm.provider import ProviderChain, ProviderError
from my_agent_crew.llm.types import Completion, Message
from my_agent_crew.script import limits
from my_agent_crew.script.limits import Halt, ScriptError
from my_agent_crew.script.llm_calls import LLM, checked
from my_agent_crew.script.model_answers import messages, taken
from my_agent_crew.script.nested import ScriptRun
from my_agent_crew.tools.result import NestedCall

if TYPE_CHECKING:
    from my_agent_crew.agent.loop import AgentDeps

logger = logging.getLogger(__name__)
# What the ledger files these calls under (`store/side_calls.py`).
PURPOSE = "script"
# Sorting a text among a few labels, or shortening it, needs little thought.
LEAST_EFFORT = REASONING_EFFORTS[0]
# Puts the messages to a model: what it said, and what that cost where the provider told.
Ask = Callable[[Sequence[Message]], Awaitable[tuple[str, float | None]]]


def agents_model(deps: AgentDeps) -> Ask:
    """The agent's own model as its scripts may ask it. The first route alone: a call a
    script makes is not moved to the next model when this one fails, nor to the dearer one
    the agent itself may step up to. A route told how hard to think is told the least; one
    told nothing is told nothing, since not every model takes the word."""

    async def ask(asked: Sequence[Message]) -> tuple[str, float | None]:
        # Read when a script asks, not when the tool was handed out: the agent's routes are
        # replaced when its file is read again.
        first = [
            replace(route, reasoning=LEAST_EFFORT) if route.reasoning else route
            for route in deps.chain.routes[:1]
        ]
        # Filed by the chain under the conversation of the turn this is asked in. A script
        # of a schedule is asked in none, and its calls are written with none.
        chain = MeteredChain(
            ProviderChain(deps.chain.providers, first), deps.store, deps.agent.id, PURPOSE
        )
        said, cost = "", None
        async for item in chain.stream(asked, ()):
            if isinstance(item, Completion):
                said, cost = item.message.content, item.usage.cost_usd
        return said, cost

    return ask


def scripts_model(deps: AgentDeps) -> Ask | None:
    """What the agent's scripts ask when they ask a model: its own, or none for an agent
    whose file says its scripts ask no model (`script_llm: false`)."""
    return agents_model(deps) if deps.settings.script_llm else None


@dataclass
class ModelCalls:
    """What one script asks a model, counted among the calls it makes (`run`)."""

    run: ScriptRun
    # None where a script is run over tools alone, with no model to ask.
    ask: Ask | None = None
    # Counted here as by the process, which is not taken at its word for what is paid for.
    asked: int = 0

    def lookup(self, kind: str, arguments: dict[str, Any]) -> Any:
        """A question of the script's. One for a model is handed back to be waited for; any
        other is answered where it always was (`ScriptRun.lookup`)."""
        if kind == LLM:
            return self.answer(arguments)
        return self.run.lookup(kind, arguments)

    async def answer(self, arguments: dict[str, Any]) -> str:
        """The text the script is handed. A call written wrongly was never made and is not
        counted; one past a count ends the script; one that was made and came to nothing is
        a failed call of the script and a mistake it may catch."""
        name, asked = checked(arguments)
        if self.ask is None:
            raise ScriptError(words.LLM_NOT_HERE)
        if self.asked >= limits.MAX_LLM_CALLS:
            raise Halt(words.LLM_TOO_MANY_CALLS.format(most=limits.MAX_LLM_CALLS))
        budget = nested_budget()
        if budget is not None and not budget.take(1):
            raise Halt(t.SCRIPT_TURN_CALLS_SPENT.format(most=budget.limit))
        self.asked += 1
        self.run.made += 1
        number, started = self.run.made, time.monotonic()
        said, cost, answer, failed, shown = "", None, "", "", ""
        try:
            said, cost = await self.ask(messages(name, asked))
            answer = taken(name, asked, said)
        except ScriptError as unusable:  # answered, and paid for, but not as it was asked
            failed = str(unusable)
            answered = preview(said)
            shown = words.LLM_SAID.format(error=failed, answer=answered) if answered else failed
        except ProviderError as exc:
            logger.warning("a script's llm.%s got no answer: %s", name, exc)
            failed, shown = words.LLM_FAILED, words.LLM_FAILED_BECAUSE.format(error=exc)
        except Exception as exc:  # what broke around one call fails that call, not the script
            logger.exception("a script's llm.%s crashed", name)
            failed = words.LLM_FAILED
            shown = words.LLM_FAILED_BECAUSE.format(error=type(exc).__name__)
        nested = NestedCall(
            name=f"{LLM}.{name}",
            arguments=argument_preview(asked),
            ok=not failed,
            output=failure_preview(shown) if failed else preview(answer),
            ms=int((time.monotonic() - started) * 1000),
            cost_usd=cost,
            metered=True,
        )
        # What the script was handed of this call, counted with what its tools handed it.
        self.run.received += len(failed or answer)
        self.run.ended[number] = nested
        note_nested_call(nested)  # shown as it ends, though the script has not
        if failed:
            raise ScriptError(failed)
        return answer
