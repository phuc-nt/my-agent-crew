"""`image_read`: a picture goes down the vision chain, the answer and the price come back."""

from pathlib import Path

from my_agent_crew.agent.events import ToolResultEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.config import Route, load_settings
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.provider import ProviderChain, ProviderError
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.tools import ToolRegistry
from my_agent_crew.tools.image import IMAGE_TOOL_NAME, build_image_tool
from tests.conftest import collect

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def vision(*script) -> tuple[ProviderChain, ScriptedProvider]:
    provider = ScriptedProvider(list(script), name="vis")
    return ProviderChain({"vis": provider}, (Route("vis", "eyes"),)), provider


def picture(directory: Path, name: str = "meal.png") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(PNG)
    return path


async def test_the_picture_reaches_the_vision_model_as_a_data_url(tmp_path: Path):
    chain, provider = vision(completion("Một bát phở bò.", cost_usd=0.002))
    path = picture(tmp_path / "ws")
    registry = ToolRegistry([build_image_tool((tmp_path / "ws",), chain)])

    result = await registry.execute(IMAGE_TOOL_NAME, {"path": "meal.png", "question": "Món gì?"})

    assert result.ok and result.output == "Một bát phở bò."
    assert result.metered and result.cost_usd == 0.002
    request = provider.requests[0]
    assert request.messages[-1].content == "Món gì?"
    assert request.messages[-1].images[0].startswith("data:image/png;base64,")
    assert request.tools == () and request.model == "eyes"
    assert path.is_file()


async def test_an_absolute_path_in_a_second_root_is_read_and_one_outside_is_refused(
    tmp_path: Path,
):
    """The crew home is a root so a delegate can look at the master's inbox."""
    chain, _ = vision(completion("ok"), completion("ok"))
    home, ws = tmp_path / "home", tmp_path / "ws"
    inbox = picture(home / "workspace" / "inbox", "file_2.jpg")
    elsewhere = picture(tmp_path / "elsewhere", "secret.jpg")
    registry = ToolRegistry([build_image_tool((ws, home), chain)])

    assert (await registry.execute(IMAGE_TOOL_NAME, {"path": str(inbox)})).ok
    refused = await registry.execute(IMAGE_TOOL_NAME, {"path": str(elsewhere)})
    assert not refused.ok and "ngoài" not in refused.output and "home" in refused.output


async def test_missing_unsupported_and_oversized_pictures_are_refused_before_any_call(
    tmp_path: Path,
):
    chain, provider = vision()
    ws = tmp_path / "ws"
    picture(ws, "notes.txt")
    picture(ws, "big.png").write_bytes(b"\x00" * 64)
    registry = ToolRegistry([build_image_tool((ws,), chain, max_bytes=16)])

    for args, word in (
        ({"path": "nope.png"}, "Không có tệp ảnh"),
        ({"path": "notes.txt"}, "Không hỗ trợ định dạng .txt"),
        ({"path": "big.png"}, "vượt mức"),
    ):
        result = await registry.execute(IMAGE_TOOL_NAME, args)
        assert not result.ok and word in result.output and not result.metered
    assert provider.requests == []


async def test_a_vision_model_that_fails_is_reported_and_the_next_route_is_tried(
    tmp_path: Path,
):
    first = ScriptedProvider([ProviderError("HTTP 502")], name="a")
    second = ScriptedProvider([completion("Ảnh chụp màn hình đồng hồ.")], name="b")
    chain = ProviderChain({"a": first, "b": second}, (Route("a", "x"), Route("b", "y")))
    ws = tmp_path / "ws"
    picture(ws)
    registry = ToolRegistry([build_image_tool((ws,), chain)])

    assert (await registry.execute(IMAGE_TOOL_NAME, {"path": "meal.png"})).output.startswith("Ảnh")

    dead = ProviderChain(
        {"a": ScriptedProvider([ProviderError("down")], name="a")}, (Route("a", "x"),)
    )
    failed = await ToolRegistry([build_image_tool((ws,), dead)]).execute(
        IMAGE_TOOL_NAME, {"path": "meal.png"}
    )
    assert not failed.ok and "Không đọc được ảnh" in failed.output


async def test_the_price_of_the_look_lands_on_the_conversation(deps_factory, tmp_path: Path):
    chain, _ = vision(completion("Cơm gà.", cost_usd=0.01))
    deps = deps_factory(
        script=[
            completion(tool_calls=(ToolCall("c1", IMAGE_TOOL_NAME, {"path": "meal.png"}),)),
            completion("Bữa trưa là cơm gà."),
        ],
        extra_tools=[build_image_tool((deps_workspace := tmp_path / "home" / "workspace",), chain)],
    )
    picture(deps_workspace)
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "tôi vừa ăn gì?"))

    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result.ok and result.output == "Cơm gà."
    # two scripted completions at 0.001 each, plus the look
    assert abs(deps.store.get(conv.id).spent_usd - 0.012) < 1e-9


def test_every_agent_gets_image_read_only_when_a_vision_route_has_a_provider(tmp_path: Path):
    from my_agent_crew.server import build_runtime

    (tmp_path / "agents" / "pong").mkdir(parents=True)
    (tmp_path / "agents" / "pong" / "agent.yaml").write_text("name: Pong\n", encoding="utf-8")
    base = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"}

    without = build_runtime(load_settings(env=base))  # default vision routes need a key
    assert all(
        IMAGE_TOOL_NAME not in without.deps_for(a).tools.names() for a in ("default", "pong")
    )

    with_ = build_runtime(load_settings(env={**base, "MY_AGENT_VISION_ROUTES": "fake:echo"}))
    assert all(IMAGE_TOOL_NAME in with_.deps_for(a).tools.names() for a in ("default", "pong"))
