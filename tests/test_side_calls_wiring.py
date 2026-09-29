"""Each place that asks a model beside a turn writes the call down under its purpose."""

from __future__ import annotations

import asyncio
import json
import os
from io import BytesIO
from pathlib import Path

import httpx
import pypdf
import pytest

from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.turn_context import set_turn_conversation
from my_agent_crew.agents import default_profile
from my_agent_crew.agents.context import ensure_agent_dirs
from my_agent_crew.config import Route, Settings
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.metered_chain import MeteredChain
from my_agent_crew.llm.provider import ProviderChain
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.memory import agent_store
from my_agent_crew.memory.consolidate import consolidate_memory
from my_agent_crew.memory.conversation_title import title_on_first_message
from my_agent_crew.memory.session_summary import summarize_conversation
from my_agent_crew.memory.wiki_compile import compile_wiki
from my_agent_crew.server.tool_assembly import build_tools
from my_agent_crew.store import Store
from my_agent_crew.tools import Tool
from my_agent_crew.tools.image import build_image_tool
from tests.conftest import collect

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PAGES = json.dumps(
    [
        {
            "title": "Hạn Eco",
            "kind": "entities",
            "body": "Hạn nộp hồ sơ Eco là thứ tư, đã dời một lần từ thứ hai tuần trước.",
            "sources": ["note:2026-09-19"],
        }
    ],
    ensure_ascii=False,
)


def vision(*replies: str, cost_usd: float = 0.002) -> ProviderChain:
    provider = ScriptedProvider([completion(r, cost_usd=cost_usd) for r in replies], name="vis")
    return ProviderChain({"vis": provider}, (Route("vis", "eyes"),))


def scanned_pdf(path: Path) -> None:
    """A page with no text layer, which only a vision model can read."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    writer.write(buffer)
    path.write_bytes(buffer.getvalue())


async def long_read(args: dict) -> str:
    return "Sổ chi tiêu tháng chín, từng dòng một. " * 2000


async def test_the_tools_that_ask_a_model_write_down_what_for(tmp_path: Path, store: Store):
    settings = Settings(home=tmp_path / "home", routes=(Route("scripted", "m"),))
    profile = default_profile(settings)
    ensure_agent_dirs(profile)
    (profile.workspace / "meal.png").write_bytes(PNG)
    scanned_pdf(profile.workspace / "scan.pdf")
    own = ScriptedProvider([completion("Các khoản chi lặp lại.", cost_usd=0.004)])
    chain = ProviderChain({"scripted": own}, settings.routes)
    extra = [Tool("long_read", "Đọc sổ dài.", {"type": "object", "properties": {}}, long_read)]
    conv = store.create()
    set_turn_conversation(conv.id)

    async with httpx.AsyncClient() as client:
        tools = build_tools(profile, client, store, [], extra, vision("Phở.", "Hợp đồng"), chain)
        assert (await tools.execute("image_read", {"path": "meal.png"})).ok
        assert (await tools.execute("pdf_read", {"path": "scan.pdf"})).ok
        assert (await tools.execute("long_read", {})).shaped_kind == "summary"

    calls = store.side_calls.for_conversation(conv.id)
    assert [(c.purpose, c.agent_id) for c in calls] == [
        ("image", "default"),
        ("pdf", "default"),
        ("tool_summary", "default"),
    ]
    assert [c.cost_usd for c in calls] == [0.002, 0.002, 0.004]


async def test_a_run_that_read_a_picture_costs_the_model_and_the_picture(
    deps_factory, store: Store, tmp_path: Path
):
    (tmp_path / "meal.png").write_bytes(PNG)
    metered = MeteredChain(vision("Phở bò."), store, "default", "image")
    deps = deps_factory(
        script=[
            completion(tool_calls=[ToolCall("c1", "image_read", {"path": "meal.png"})]),
            completion("Một bát phở bò."),
        ],
        extra_tools=[build_image_tool((tmp_path,), metered)],
    )
    hub = ActivityHub(deps.store)
    conv = deps.store.create()

    await collect(tracked(hub, run_turn(deps, conv.id, "ảnh gì?"), "default", "chat", "t", conv.id))

    [run] = hub.recent()
    # Two model calls at 0.001 each, and the picture at 0.002.
    assert run.spent_usd == pytest.approx(0.004) and run.unknown_cost_calls == 0
    assert deps.store.get(conv.id).spent_usd == pytest.approx(0.004)
    [picture] = deps.store.side_calls.for_conversation(conv.id)
    assert picture.purpose == "image" and picture.cost_usd == 0.002


async def test_a_title_is_written_down_against_its_own_conversation(deps_factory):
    deps = deps_factory(script=[completion("Kế hoạch ôn thi", cost_usd=0.003)])
    earlier, conv = deps.store.create(), deps.store.create()
    set_turn_conversation(earlier.id)  # the task copies whatever turn its creator was in
    kept: list[asyncio.Task[None]] = []

    title_on_first_message(kept.append, deps, conv.id, "Giúp tôi ôn thi tiếng Nhật")
    await asyncio.gather(*kept)

    [call] = deps.store.side_calls.for_conversation(conv.id)
    assert (call.purpose, call.agent_id, call.cost_usd) == ("title", "default", 0.003)
    assert deps.store.side_calls.for_conversation(earlier.id) == []


async def test_a_recap_is_written_down_against_the_conversation_it_recaps(deps_factory):
    deps = deps_factory(script=[completion("Đã nhắc chạy bộ.", cost_usd=0.02)])
    old = deps.store.create(agent_id="default", channel="telegram:42")
    deps.store.append(old.id, Message(role="user", content="Nhắc tôi chạy bộ"))
    deps.store.append(old.id, Message(role="assistant", content="Đã ghi"))
    new = deps.store.create(agent_id="default", channel="telegram:42")
    set_turn_conversation(new.id)  # a recap runs as the next conversation opens

    assert await summarize_conversation(deps, old.id) == "Đã nhắc chạy bộ."

    [call] = deps.store.side_calls.for_conversation(old.id)
    assert call.purpose == "session_summary" and call.cost_usd == 0.02
    assert deps.store.side_calls.for_conversation(new.id) == []


async def test_memory_upkeep_is_counted_once_and_belongs_to_no_conversation(deps_factory):
    deps = deps_factory(
        script=[
            completion("- Sếp ngủ trước 23h.", cost_usd=0.001),
            completion(PAGES, cost_usd=0.002),
        ]
    )
    memory = deps.agent.memory_file
    agent_store.write_memory_md(memory, "- Sếp thích trà.")
    agent_store.write_note(deps.agent.memory_dir, "2026-09-19", "Hạn Eco dời sang thứ tư.")
    stamp = memory.stat().st_mtime + 10
    os.utime(deps.agent.memory_dir / "2026-09-19.md", (stamp, stamp))
    hub = ActivityHub(deps.store)

    assert await consolidate_memory(deps, hub) is not None
    assert await compile_wiki(deps, hub) is not None

    purposes = {p["purpose"]: p for p in deps.store.usage.by_purpose()}
    # The runs keep a copy of these calls, but the ledger reads no runs: each counts once.
    assert set(purposes) == {"consolidate", "wiki"}
    assert purposes["consolidate"]["cost_usd"] == pytest.approx(0.001)
    assert purposes["wiki"]["cost_usd"] == pytest.approx(0.002)
    rows = deps.store._conn.execute("SELECT conversation_id FROM side_calls").fetchall()
    assert [row[0] for row in rows] == [None, None]
    assert sum(run.spent_usd for run in hub.recent(5)) == pytest.approx(0.003)
