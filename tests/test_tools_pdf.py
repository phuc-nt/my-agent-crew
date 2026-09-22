"""Reading a PDF, whether or not its words are in the file.

The two kinds of PDF are built here rather than committed as fixtures, so the test says
in one place what makes a page "scanned": no text layer, only a picture."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pypdf
import pypdfium2
import pytest

from my_agent_crew.config import Route
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.provider import ProviderChain, ProviderError
from my_agent_crew.tools.pdf import MAX_PAGES, build_pdf_tool, parse_pages
from my_agent_crew.tools.pdf_texts import PDF_NEEDS_VISION, PDF_VISION_FAILED
from my_agent_crew.tools.registry import ToolError


def typeset(path: Path, pages: list[str]) -> Path:
    """A PDF whose words really are in the file, as a typeset document's are.

    Written by hand because neither pypdf nor pypdfium2 can author a text layer, and a
    committed binary fixture would hide what makes these pages different from scanned
    ones: a `/Contents` stream with a `Tj` in it."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # filled in below, once the page object numbers are known
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    page_ids = [4 + 2 * i for i in range(len(pages))]
    kids = b" ".join(b"%d 0 R" % i for i in page_ids)
    objects[1] = b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % len(pages)
    for page_id, text in zip(page_ids, pages, strict=True):
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (page_id + 1)
        )
        stream = b"BT /F1 12 Tf 20 150 Td (" + text.encode("latin-1") + b") Tj ET"
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    path.write_bytes(_assemble(objects))
    return path


def _assemble(objects: list[bytes]) -> bytes:
    """The objects, numbered from one, with the cross-reference table a reader needs."""
    out = BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    start = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    # `%%%%EOF` because the literal marker is `%%EOF` and `%`-formatting halves it.
    trailer = b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
    out.write(trailer % (len(objects) + 1, start))
    return out.getvalue()


def _to_bytes(writer: pypdf.PdfWriter) -> bytes:
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def scanned(path: Path, pages: int = 1) -> Path:
    """A PDF whose pages carry no text at all, the way a photographed page does."""
    writer = pypdf.PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    path.write_bytes(_to_bytes(writer))
    return path


def vision(*replies: str) -> ProviderChain:
    provider = ScriptedProvider([completion(r, cost_usd=0.001) for r in replies], name="vis")
    return ProviderChain({"vis": provider}, (Route("vis", "eyes"),))


async def run_tool(tool, **args) -> str:
    result = await tool.run(args)
    return result.output


def test_a_page_range_is_read_as_written():
    assert parse_pages("2-4", 10) == [1, 2, 3]
    assert parse_pages("3", 10) == [2]
    assert parse_pages("", 3) == [0, 1, 2]


def test_no_range_reads_from_the_start_but_not_for_ever():
    """A 400-page scan asked for in full would spend real money before anyone looked."""
    assert parse_pages("", 400) == list(range(MAX_PAGES))
    assert len(parse_pages("1-400", 400)) == MAX_PAGES


def test_a_range_past_the_end_stops_at_the_end():
    assert parse_pages("2-99", 3) == [1, 2]


@pytest.mark.parametrize("pages", ["nope", "0", "5-2", "-3"])
def test_a_range_that_means_nothing_is_refused(pages: str):
    with pytest.raises(ToolError):
        parse_pages(pages, 10)


def test_a_page_that_does_not_exist_says_how_many_there_are():
    with pytest.raises(ToolError) as exc:
        parse_pages("9", 3)
    assert "3" in str(exc.value)


async def test_a_typeset_pdf_reads_without_any_vision_route(tmp_path: Path):
    """The common case costs nothing: the words are already in the file."""
    typeset(tmp_path / "hop-dong.pdf", ["Hop dong so 12", "Dieu khoan thanh toan"])
    tool = build_pdf_tool((tmp_path,), None)
    result = await tool.run({"path": "hop-dong.pdf"})
    assert "Hop dong so 12" in result.output
    assert "Dieu khoan thanh toan" in result.output
    assert not result.metered and result.cost_usd is None


async def test_each_page_is_labelled_so_the_agent_can_cite_one(tmp_path: Path):
    typeset(tmp_path / "doc.pdf", ["mot", "hai", "ba"])
    output = await run_tool(build_pdf_tool((tmp_path,), None), path="doc.pdf")
    assert output.index("Trang 1") < output.index("Trang 2") < output.index("Trang 3")


async def test_only_the_pages_asked_for_are_read(tmp_path: Path):
    typeset(tmp_path / "doc.pdf", ["mot", "hai", "ba"])
    output = await run_tool(build_pdf_tool((tmp_path,), None), path="doc.pdf", pages="2")
    assert "hai" in output and "mot" not in output and "ba" not in output


async def test_a_mixed_document_reads_text_and_only_pays_for_the_scan(tmp_path: Path):
    """The point of going page by page: a contract with one photographed page should not
    send all forty pages to a vision model."""
    path = tmp_path / "mixed.pdf"
    typeset(path, ["Dieu 1: thanh toan", ""])
    tool = build_pdf_tool((tmp_path,), vision("Chu ky va con dau"))
    result = await tool.run({"path": "mixed.pdf"})
    assert "Dieu 1: thanh toan" in result.output
    assert "Chu ky va con dau" in result.output
    assert result.metered


async def test_a_scanned_page_without_vision_says_it_needs_one(tmp_path: Path):
    """The tool still loads. A typeset PDF reads fine without vision, so refusing to
    register would hide the common case behind a capability it never uses."""
    scanned(tmp_path / "scan.pdf")
    tool = build_pdf_tool((tmp_path,), None)
    output = await run_tool(tool, path="scan.pdf")
    assert PDF_NEEDS_VISION in output


async def test_a_scanned_page_is_read_by_the_vision_model(tmp_path: Path):
    scanned(tmp_path / "scan.pdf")
    tool = build_pdf_tool((tmp_path,), vision("Hợp đồng số 12"))
    result = await tool.run({"path": "scan.pdf"})
    assert "Hợp đồng số 12" in result.output
    assert result.metered  # a vision call costs money and must land on the conversation


async def test_a_vision_failure_marks_that_page_and_keeps_the_rest(tmp_path: Path):
    """One page failing must not throw away the pages that read."""

    provider = ScriptedProvider([ProviderError("hết hạn mức")] * 2, name="vis")
    chain = ProviderChain({"vis": provider}, (Route("vis", "eyes"),))
    scanned(tmp_path / "scan.pdf", pages=2)
    tool = build_pdf_tool((tmp_path,), chain)
    output = await run_tool(tool, path="scan.pdf")
    marker = PDF_VISION_FAILED.split("{error}")[0]
    assert output.count(marker) == 2 and output.count("hết hạn mức") == 2
    assert "Trang 1" in output and "Trang 2" in output


async def test_a_missing_file_says_so(tmp_path: Path):
    tool = build_pdf_tool((tmp_path,), None)
    with pytest.raises(ToolError):
        await tool.run({"path": "nope.pdf"})


async def test_a_file_that_is_not_a_pdf_is_refused(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("xin chào")
    tool = build_pdf_tool((tmp_path,), None)
    with pytest.raises(ToolError):
        await tool.run({"path": "notes.txt"})


async def test_a_path_outside_every_root_is_refused(tmp_path: Path):
    scanned(tmp_path / "scan.pdf")
    tool = build_pdf_tool((tmp_path / "work",), None)
    with pytest.raises(ToolError):
        await tool.run({"path": "../scan.pdf"})


async def test_the_second_root_is_tried_too(tmp_path: Path):
    """A delegate reads the master's inbox, which is not its own workspace."""
    home = tmp_path / "home"
    home.mkdir()
    scanned(home / "scan.pdf")
    tool = build_pdf_tool((tmp_path / "work", home), None)
    assert "Trang 1" in await run_tool(tool, path="scan.pdf")


def test_a_page_renders_to_an_image_the_vision_model_can_read(tmp_path: Path):
    from my_agent_crew.tools.pdf import page_image

    scanned(tmp_path / "scan.pdf")
    url = page_image(tmp_path / "scan.pdf", 0)
    assert url.startswith("data:image/png;base64,")
    assert len(url) > 200  # a real bitmap, not an empty one


def test_the_render_uses_the_page_that_was_asked_for(tmp_path: Path):
    """Off-by-one here would silently read the wrong page of a contract."""
    path = tmp_path / "many.pdf"
    writer = pypdf.PdfWriter()
    for width in (200, 400):
        writer.add_blank_page(width=width, height=200)
    path.write_bytes(_to_bytes(writer))
    document = pypdfium2.PdfDocument(str(path))
    try:
        widths = [round(document[i].get_size()[0]) for i in range(2)]
    finally:
        document.close()
    assert widths == [200, 400]
