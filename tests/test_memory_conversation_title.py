from __future__ import annotations

import asyncio

from my_agent_crew.activity import ActivityHub
from my_agent_crew.inbound import Inbound
from my_agent_crew.llm.fake import completion
from my_agent_crew.memory.conversation_title import (
    TITLE_MAX_CHARS,
    clean_title,
    heuristic_title,
    title_on_first_message,
)
from my_agent_crew.texts import (
    CONVERSATION_TITLE_DEFAULT,
    INBOUND_CONVERSATION_TITLE,
    TITLE_PROMPT,
)


async def settle(kept: list[asyncio.Task[None]]) -> None:
    await asyncio.gather(*kept, return_exceptions=True)


def test_the_first_sentence_becomes_the_title_and_the_rest_is_dropped():
    assert heuristic_title("Tìm sách hay đi. Tôi thích trinh thám.") == "Tìm sách hay đi"


def test_a_long_opening_is_cut_at_a_word_so_no_title_ends_mid_word():
    title = heuristic_title("Hãy giúp tôi lập kế hoạch ôn thi tiếng Nhật trong ba tháng tới nhé")

    assert len(title) <= TITLE_MAX_CHARS
    assert not title.endswith(" ") and title.split()[-1] in title


def test_a_message_spread_over_lines_still_yields_one_line():
    assert heuristic_title("Chào bạn\n\nnhớ  giúp   tôi") == "Chào bạn nhớ giúp tôi"


def test_a_message_of_only_spaces_names_nothing():
    assert heuristic_title("   \n  ") == ""


def test_a_model_that_answers_with_decoration_still_gives_a_bare_title():
    assert clean_title('"Kế hoạch ôn thi"\nGiải thích thêm...') == "Kế hoạch ôn thi"


async def test_the_sidebar_row_is_named_before_the_model_is_asked(deps_factory):
    deps = deps_factory(script=[completion("Kế hoạch ôn thi tiếng Nhật")])
    conv = deps.store.create()
    kept: list[asyncio.Task[None]] = []

    immediate = title_on_first_message(kept.append, deps, conv.id, "Giúp tôi ôn thi tiếng Nhật")

    assert immediate == "Giúp tôi ôn thi tiếng Nhật"
    assert deps.store.get(conv.id).title == immediate
    await settle(kept)
    assert deps.store.get(conv.id).title == "Kế hoạch ôn thi tiếng Nhật"


async def test_a_name_the_person_typed_is_never_overwritten_by_the_model(deps_factory):
    deps = deps_factory(script=[completion("Tiêu đề của model")])
    conv = deps.store.create()
    kept: list[asyncio.Task[None]] = []

    title_on_first_message(kept.append, deps, conv.id, "Giúp tôi ôn thi")
    deps.store.update(conv.id, title="Tên tôi tự đặt")
    await settle(kept)

    assert deps.store.get(conv.id).title == "Tên tôi tự đặt"


async def test_only_the_first_message_names_the_conversation(deps_factory):
    deps = deps_factory(script=[completion("Tiêu đề đầu")])
    conv = deps.store.create()
    kept: list[asyncio.Task[None]] = []

    title_on_first_message(kept.append, deps, conv.id, "Câu đầu tiên")
    await settle(kept)
    second = title_on_first_message(kept.append, deps, conv.id, "Câu thứ hai hoàn toàn khác")

    assert second == "Tiêu đề đầu"
    assert deps.store.get(conv.id).title == "Tiêu đề đầu"


async def test_a_conversation_opened_by_a_channel_keeps_the_name_the_channel_gave_it(deps_factory):
    deps = deps_factory(script=[completion("không nên được gọi")])
    named = INBOUND_CONVERSATION_TITLE.format(channel="telegram", date="2026-09-22")
    conv = deps.store.create(title=named, channel="telegram:42")
    kept: list[asyncio.Task[None]] = []

    assert title_on_first_message(kept.append, deps, conv.id, "Chào bạn") == named
    assert kept == []
    assert deps.store.get(conv.id).title == named


async def test_a_failing_model_leaves_the_first_sentence_in_place(deps_factory):
    deps = deps_factory(script=[])  # an exhausted script raises inside the task
    conv = deps.store.create()
    kept: list[asyncio.Task[None]] = []

    title_on_first_message(kept.append, deps, conv.id, "Đặt lịch chạy bộ")
    await settle(kept)

    assert deps.store.get(conv.id).title == "Đặt lịch chạy bộ"


async def test_a_conversation_is_named_once_even_if_two_messages_race(deps_factory):
    deps = deps_factory(script=[completion("Tiêu đề model")])
    conv = deps.store.create()
    kept: list[asyncio.Task[None]] = []

    # Different sentences: were the second message to start its own naming, it would be
    # the one heard from, so the assertion below pins the guard and not the text.
    title_on_first_message(kept.append, deps, conv.id, "Câu hỏi đầu")
    title_on_first_message(kept.append, deps, conv.id, "Câu hỏi thứ hai khác hẳn")
    await settle(kept)

    assert len(kept) == 1
    assert deps.store.get(conv.id).title == "Tiêu đề model"


async def test_a_cancelled_naming_does_not_lock_the_conversation_out_of_a_later_one(
    deps_factory,
):
    """A task cancelled at shutdown must not leave the conversation permanently unnameable."""
    deps = deps_factory(script=[completion("Tiêu đề model")])
    conv = deps.store.create()
    kept: list[asyncio.Task[None]] = []

    title_on_first_message(kept.append, deps, conv.id, "Câu hỏi đầu")
    kept[0].cancel()
    await settle(kept)
    deps.store.update(conv.id, title=CONVERSATION_TITLE_DEFAULT)

    title_on_first_message(kept.append, deps, conv.id, "Thử lại lần nữa")
    await settle(kept)

    assert len(kept) == 2
    assert deps.store.get(conv.id).title == "Tiêu đề model"


async def test_naming_a_conversation_is_billed_like_every_other_model_call(deps_factory):
    deps = deps_factory(script=[completion("Tiêu đề model", cost_usd=0.02)])
    conv = deps.store.create()
    kept: list[asyncio.Task[None]] = []

    title_on_first_message(kept.append, deps, conv.id, "Câu hỏi đầu")
    await settle(kept)

    assert deps.store.get(conv.id).spent_usd == 0.02


async def test_deleting_a_conversation_while_it_is_being_named_is_not_an_error(
    deps_factory, caplog
):
    deps = deps_factory(script=[completion("Tiêu đề model")])
    conv = deps.store.create()
    kept: list[asyncio.Task[None]] = []

    title_on_first_message(kept.append, deps, conv.id, "Câu hỏi đầu")
    deps.store.delete(conv.id)
    await settle(kept)

    assert not [r for r in caplog.records if r.levelname == "ERROR"]


async def test_watchers_hear_about_the_name_twice_so_the_sidebar_never_needs_a_reload(
    deps_factory,
):
    deps = deps_factory(script=[completion("Tiêu đề model")])
    conv = deps.store.create()
    kept: list[asyncio.Task[None]] = []
    seen: list[str] = []

    title_on_first_message(
        kept.append, deps, conv.id, "Câu hỏi đầu", publish=lambda c: seen.append(c["title"])
    )
    await settle(kept)

    assert seen == ["Câu hỏi đầu", "Tiêu đề model"]


async def test_a_conversation_that_already_has_a_name_is_left_alone(deps_factory):
    deps = deps_factory(script=[completion("không nên được gọi")])
    conv = deps.store.create(title="Đã có tên")
    kept: list[asyncio.Task[None]] = []

    assert title_on_first_message(kept.append, deps, conv.id, "Chào") == "Đã có tên"
    assert kept == []


async def test_a_brand_new_conversation_starts_from_the_default_name(deps_factory):
    deps = deps_factory(script=[completion("Tiêu đề model")])
    conv = deps.store.create()

    assert conv.title == CONVERSATION_TITLE_DEFAULT


async def test_naming_queues_behind_a_turn_of_a_conversation_that_ran_before(deps_factory):
    """Naming waits for the answer, and a turn on a conversation that already ran is
    still a turn to wait for.

    `tracked` only lowers the terminal signal when the caller reads its first event, so a
    waiter made in between would read the *previous* turn's raised signal and ask the
    model while the answer is still streaming, over the same chain."""
    deps = deps_factory(script=[completion("Câu trả lời")])
    hub = ActivityHub(deps.store)
    inbound = Inbound({deps.agent.id: deps}, hub)
    conv = deps.store.create()
    hub._finished.setdefault(conv.id, asyncio.Event()).set()  # as a finished run leaves it

    stream = inbound.stream(conv.id, "Xin chào bạn")
    waited = asyncio.create_task(hub.wait_finished(conv.id, 5.0))
    await asyncio.sleep(0)

    assert not waited.done(), "naming would have started while the turn was still running"
    async for _ in stream:
        pass
    assert await waited is not None


async def test_a_turn_that_never_ends_leaves_the_first_sentence_as_the_name(deps_factory):
    """Naming gives up rather than asking the model while the turn still holds the chain."""
    deps = deps_factory(script=[completion("Tiêu đề model")])
    conv = deps.store.create()
    kept: list[asyncio.Task[None]] = []

    async def never_finishes() -> None:
        raise TimeoutError  # what `_name_conversation` raises when the wait runs out

    title_on_first_message(kept.append, deps, conv.id, "Câu hỏi đầu", after=never_finishes)
    await settle(kept)

    assert deps.store.get(conv.id).title == "Câu hỏi đầu"


async def test_a_model_that_reads_the_instructions_back_does_not_get_to_name_anything(
    deps_factory,
):
    # The echo provider does exactly this, and a real model occasionally does too.
    deps = deps_factory(script=[completion(TITLE_PROMPT.format(message="Đặt lịch chạy bộ"))])
    conv = deps.store.create()
    kept: list[asyncio.Task[None]] = []

    title_on_first_message(kept.append, deps, conv.id, "Đặt lịch chạy bộ")
    await settle(kept)

    assert deps.store.get(conv.id).title == "Đặt lịch chạy bộ"
