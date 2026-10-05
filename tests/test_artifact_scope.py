"""What a canvas tool checks before it touches a canvas: whether the turn may write at all,
whether the canvas is in the agent's reach, how many versions the turn has written, and what
each store refusal tells it to do."""

import asyncio

import pytest

from my_agent_crew.agent.turn_context import (
    API,
    CHAT,
    JOB,
    TELEGRAM,
    canvas_reader_is_away,
    canvas_writes,
    may_write_canvas,
    note_canvas_write,
    set_turn_conversation,
    set_turn_source,
)
from my_agent_crew.artifacts.kinds import (
    ArtifactTooLarge,
    InvalidLanguage,
    InvalidTitle,
    PayloadMismatch,
    StorageFull,
    UnknownKind,
    UnstorableText,
)
from my_agent_crew.store.artifact_models import (
    USER,
    VersionConflict,
    VersionGone,
)
from my_agent_crew.store.db import Store
from my_agent_crew.texts_canvas import (
    ARTIFACT_CHANNEL_CLOSED,
    ARTIFACT_CONTENT_UNSTORABLE,
    ARTIFACT_CREATE_BUDGET,
    ARTIFACT_KIND_CLOSED,
    ARTIFACT_TITLE_UNSTORABLE,
)
from my_agent_crew.tools.artifact_scope import (
    CANVAS_WRITES_PER_TURN,
    NEW_CANVAS,
    canvas_errors,
    check_agent_kind,
    check_budget,
    check_channel,
    in_scope,
    not_found,
)
from my_agent_crew.tools.registry import ToolError

ART = "0123456789ab"
# What an agent's refusal of a kind lists, in the order of the table.
WRITABLE = "markdown, code, html, svg, mermaid"


@pytest.fixture(autouse=True)
def fresh_turn():
    """A sync test shares the main context with the next one, so each starts and ends as a
    chat turn of no conversation."""
    set_turn_source(CHAT)
    set_turn_conversation("")
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


def _canvas(store: Store, agent_id: str = "") -> str:
    author = USER if agent_id == "" else f"agent:{agent_id}"
    return store.artifacts.create("Kế hoạch", "markdown", agent_id, author, "", "#").id


@pytest.mark.parametrize(
    ("source", "writes"),
    [(CHAT, True), (TELEGRAM, True), ("job:coach/brief", True), (API, False)],
)
def test_a_turn_from_the_web_chat_telegram_or_a_job_writes_a_canvas(store: Store, source, writes):
    """What is written on Telegram or by a job reaches the person as a file and a list in
    the chat. Nothing carries a canvas back through the inbound API, so a turn from there
    writes none."""
    set_turn_source(source)
    conv = store.create()
    assert may_write_canvas(conv) is writes
    if writes:
        check_channel(conv)
    else:
        with pytest.raises(ToolError) as caught:
            check_channel(conv)
        assert str(caught.value) == ARTIFACT_CHANNEL_CLOSED


@pytest.mark.parametrize(
    ("root_source", "writes"),
    [(CHAT, True), (TELEGRAM, True), (JOB, True), (API, False), ("", False)],
)
def test_a_delegated_child_writes_when_the_turn_its_chain_began_from_could(
    store: Store, root_source, writes
):
    """A child's own turn names its parent, not a channel; a child opened before chains
    recorded their root has an empty one and never writes."""
    root = store.create()
    child = store.create(root_id=root.id, root_source=root_source)
    set_turn_source(f"delegate:{root.id}")
    assert may_write_canvas(child) is writes


def test_a_person_typing_in_a_childs_own_conversation_writes_from_there(store: Store):
    root = store.create()
    child = store.create(root_id=root.id, root_source=API)
    set_turn_source(CHAT)
    assert may_write_canvas(child) is True


@pytest.mark.parametrize(
    ("source", "away"),
    [(CHAT, False), (TELEGRAM, True), ("job:coach/brief", True), (API, False)],
)
def test_the_reader_of_a_telegram_turn_or_a_job_is_away_from_the_web(store: Store, source, away):
    """Whoever gets the answer away from the web chat does not see a canvas open beside it."""
    set_turn_source(source)
    assert canvas_reader_is_away(store.create()) is away


@pytest.mark.parametrize(
    ("root_source", "away"),
    [(CHAT, False), (TELEGRAM, True), (JOB, True), (API, False), ("", False)],
)
def test_a_delegated_childs_reader_is_where_its_chain_began(store: Store, root_source, away):
    root = store.create()
    child = store.create(root_id=root.id, root_source=root_source)
    set_turn_source(f"delegate:{root.id}")
    assert canvas_reader_is_away(child) is away


def test_a_person_typing_in_a_childs_own_conversation_reads_from_there(store: Store):
    root = store.create()
    child = store.create(root_id=root.id, root_source=TELEGRAM)
    set_turn_source(CHAT)
    assert canvas_reader_is_away(child) is False


@pytest.mark.parametrize("kind", ["image", "pdf", "", "HTML"])
def test_an_agent_writes_the_text_kinds_alone(kind):
    """A picture is bytes an agent cannot write, and one a person imported is no exception."""
    with pytest.raises(ToolError) as caught:
        check_agent_kind(kind)
    assert str(caught.value) == ARTIFACT_KIND_CLOSED.format(kinds=WRITABLE)
    for writable in ("markdown", "code", "html", "svg", "mermaid"):
        check_agent_kind(writable)


def test_the_thirty_first_write_to_one_canvas_in_a_turn_is_refused():
    set_turn_conversation("c1")
    for _ in range(CANVAS_WRITES_PER_TURN):
        check_budget(ART)
        note_canvas_write(ART)
    with pytest.raises(ToolError, match=str(CANVAS_WRITES_PER_TURN)):
        check_budget(ART)
    check_budget("ba9876543210")
    check_budget(NEW_CANVAS)

    set_turn_conversation("c1")
    assert canvas_writes(ART) == 0
    check_budget(ART)


def test_a_turn_creates_at_most_thirty_canvases():
    set_turn_conversation("c1")
    for _ in range(CANVAS_WRITES_PER_TURN):
        note_canvas_write(NEW_CANVAS)
    with pytest.raises(ToolError) as caught:
        check_budget(NEW_CANVAS)
    assert str(caught.value) == ARTIFACT_CREATE_BUDGET.format(limit=CANVAS_WRITES_PER_TURN)
    check_budget(ART)


async def test_a_batched_call_counts_toward_its_turn_and_a_child_turn_counts_apart():
    """`asyncio.gather` and a delegated child's task each run in a copy of the context: a
    call in the batch still belongs to the turn, a child's turn starts its own count."""
    set_turn_conversation("parent")

    async def batched() -> None:
        note_canvas_write(ART)

    await asyncio.gather(batched(), batched())
    assert canvas_writes(ART) == 2

    async def child() -> int:
        set_turn_conversation("child", depth=1)
        note_canvas_write(ART)
        return canvas_writes(ART)

    assert await asyncio.create_task(child()) == 1
    assert canvas_writes(ART) == 2


def test_the_master_reaches_every_canvas_and_another_agent_only_its_own(store: Store):
    here = store.create().id
    persons, coachs = _canvas(store), _canvas(store, "coach")

    def reaches(art: str, agent_id: str, is_master: bool = False) -> bool:
        return in_scope(
            store, art, agent_id=agent_id, is_master=is_master, conversation_id=here, root_id=""
        )

    assert reaches(persons, "boss", is_master=True) and reaches(coachs, "boss", is_master=True)
    assert reaches(coachs, "coach")
    assert not reaches(persons, "coach")
    assert not reaches(coachs, "researcher")
    assert not reaches(persons, USER)


def test_what_a_turn_in_the_chain_only_read_stays_out_of_the_next_childs_reach(store: Store):
    """The master reads the person's canvas, and the coach, delegated to, reads its own:
    neither read shares anything, so the researcher delegated to next finds neither."""
    master = store.create()
    persons, coachs = _canvas(store), _canvas(store, "coach")
    store.artifact_links.mark_read(master.id, persons, 1, 0, 1, 1)
    coach = store.create(root_id=master.id, root_source=CHAT)
    store.artifact_links.mark_read(coach.id, coachs, 1, 0, 1, 1)
    researcher = store.create(root_id=master.id, root_source=CHAT)

    def researcher_reaches(art: str) -> bool:
        return in_scope(
            store,
            art,
            agent_id="researcher",
            is_master=False,
            conversation_id=researcher.id,
            root_id=master.id,
        )

    assert not researcher_reaches(persons) and not researcher_reaches(coachs)
    store.artifact_links.link(master.id, persons, shared=True)
    assert researcher_reaches(persons) and not researcher_reaches(coachs)


@pytest.mark.parametrize(
    ("error", "says"),
    [
        (UnknownKind("pdf"), [WRITABLE]),
        (PayloadMismatch("image"), [WRITABLE]),
        (ArtifactTooLarge("markdown", 600000, 524288), ["600000", "524288", "nhiều canvas"]),
        (InvalidTitle("empty"), ["200"]),
        (InvalidLanguage("bad"), ["40", "python"]),
        (UnstorableText(ARTIFACT_CONTENT_UNSTORABLE), ["Nội dung", "một nửa", "Chưa lưu gì"]),
        (UnstorableText(ARTIFACT_TITLE_UNSTORABLE), ["Tiêu đề", "một nửa", "Chưa lưu gì"]),
        (StorageFull(1000, 2000), ["1000", "2000", "Đừng thử lại"]),
        (VersionGone(ART, 12, 13), ["v12 không còn, bản mới nhất là v13", f"id={ART}"]),
        (VersionConflict(9, "# mới"), ["v9", "artifact_read"]),
        (KeyError(ART), [str(not_found(ART))]),
    ],
)
def test_each_store_refusal_reaches_the_agent_as_guidance(error, says):
    with pytest.raises(ToolError) as caught, canvas_errors(ART):
        raise error
    for part in says:
        assert part in str(caught.value)


def test_a_canvas_out_of_reach_reads_exactly_like_one_that_does_not_exist():
    """Otherwise an agent could learn which canvases exist beyond its reach."""
    with pytest.raises(ToolError) as caught, canvas_errors(ART):
        raise KeyError(ART)
    assert str(caught.value) == str(not_found(ART))


def test_other_failures_pass_through_the_canvas_errors_untouched():
    """A KeyError about anything but the canvas is a bug to log, and a tool's own guidance
    is already worded for the agent."""
    with pytest.raises(KeyError), canvas_errors(ART):
        raise KeyError("seen_version")
    guidance = ToolError("đã có lời dặn")
    with pytest.raises(ToolError) as caught, canvas_errors(ART):
        raise guidance
    assert caught.value is guidance
