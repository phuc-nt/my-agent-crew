from my_agent_crew import texts
from my_agent_crew.store import Store
from my_agent_crew.tools.memory import build_memory_tools
from my_agent_crew.tools.registry import ToolRegistry


async def test_save_then_search_finds_by_every_term(store: Store):
    reg = ToolRegistry(build_memory_tools(store))
    await reg.execute("memory_save", {"text": "Người dùng thích cà phê đen buổi sáng"})
    await reg.execute("memory_save", {"text": "Dự án my-crew dùng Python"})
    hit = await reg.execute("memory_search", {"query": "cà phê sáng"})
    miss = await reg.execute("memory_search", {"query": "cà phê Python"})
    assert "cà phê đen" in hit.output and "my-crew" not in hit.output
    assert miss.output == texts.MEMORY_EMPTY


async def test_empty_note_is_rejected(store: Store):
    reg = ToolRegistry(build_memory_tools(store))
    result = await reg.execute("memory_save", {"text": "   "})
    assert result.ok is False and store.notes.count() == 0


async def test_notes_survive_across_conversations(store: Store):
    reg = ToolRegistry(build_memory_tools(store))
    await reg.execute("memory_save", {"text": "ghi nhớ A"})
    assert store.notes.count() == 1
    assert store.notes.search("ghi nhớ")[0][1] == "ghi nhớ A"
