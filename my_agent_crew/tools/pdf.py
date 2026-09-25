"""`pdf_read`: the text of a PDF, and the pages that have no text.

A PDF is two different documents wearing one extension. One was typeset, and its words are
in the file: pypdf hands them over for nothing. The other was photographed, and its pages
are pictures of words, where pypdf finds nothing at all. Returning "" for the second kind
would be the worst answer, because the agent cannot tell an empty page from a page it
failed to read, and would report the document as blank.

So a page with no text is rendered to an image and sent down the same vision chain
`image_read` uses. That costs money and takes a moment, which is why it happens per page
and only for the pages that need it.

Where there is no vision route the tool still registers, and a scanned page comes back
saying it needs one. Refusing to load the tool would hide typeset PDFs, which read fine
without vision, behind a capability they never use.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from my_agent_crew.llm.provider import ProviderChain, ProviderError
from my_agent_crew.tools.image import describe
from my_agent_crew.tools.pdf_texts import (
    PDF_BAD_RANGE,
    PDF_BROKEN,
    PDF_EMPTY,
    PDF_NEEDS_VISION,
    PDF_NOT_FOUND,
    PDF_NOT_PDF,
    PDF_OUT_OF_RANGE,
    PDF_PAGE_HEADING,
    PDF_RENDER_FAILED,
    PDF_SCAN_QUESTION,
    PDF_VISION_FAILED,
)
from my_agent_crew.tools.registry import Tool, ToolError, ToolResult
from my_agent_crew.tools.workspace import resolve_inside

if TYPE_CHECKING:
    import pypdf

# pypdf and pypdfium2 are imported where they are used: together they take a noticeable
# slice of server start-up, and most sessions never open a PDF.

PDF_TOOL_NAME = "pdf_read"
MAX_PAGES = 50
RENDER_SCALE = 2  # ~144 dpi: enough for a vision model to read body text.

PDF_DESCRIPTION = (
    "Đọc nội dung một file PDF trong workspace. Trả về text theo từng trang."
    " Trang là ảnh scan sẽ được đọc bằng mô hình thị giác, nên tốn thêm chi phí:"
    " với file dài, hãy dùng 'pages' để chỉ đọc phần cần."
)
PDF_PARAM_PATH = "Đường dẫn file PDF, tính từ workspace."
PDF_PARAM_PAGES = (
    f"Khoảng trang cần đọc, ví dụ '1-5' hoặc '3'. Bỏ trống để đọc từ đầu, tối đa {MAX_PAGES} trang."
)
PDF_PARAM_QUESTION = "Điều cần tìm trong các trang scan. Chỉ dùng cho trang phải đọc bằng thị giác."


def parse_pages(pages: str, count: int) -> list[int]:
    """The zero-based page numbers a `pages` string asks for.

    Empty means "from the start", capped, rather than the whole file: a 400-page scan asked
    for in full would spend a lot of money before anyone noticed."""
    text = pages.strip()
    if not text:
        return list(range(min(count, MAX_PAGES)))
    parts = text.split("-", 1)
    try:
        first = int(parts[0])
        last = int(parts[1]) if len(parts) == 2 else first
    except ValueError:
        raise ToolError(PDF_BAD_RANGE.format(pages=pages)) from None
    if first < 1 or last < first:
        raise ToolError(PDF_BAD_RANGE.format(pages=pages))
    if first > count:
        raise ToolError(PDF_OUT_OF_RANGE.format(count=count, page=first))
    return list(range(first - 1, min(last, count, first - 1 + MAX_PAGES)))


def open_pdf(path: Path) -> pypdf.PdfReader:
    import pypdf

    if not path.is_file():
        raise ToolError(PDF_NOT_FOUND.format(path=path))
    if path.suffix.lower() != ".pdf":
        raise ToolError(PDF_NOT_PDF.format(path=path))
    try:
        return pypdf.PdfReader(str(path))
    except Exception as exc:  # pypdf raises several unrelated types on a bad file
        raise ToolError(PDF_BROKEN.format(error=exc)) from exc


def page_image(path: Path, index: int) -> str:
    """One page as a PNG data URL, for a vision model to read."""
    import pypdfium2

    document = pypdfium2.PdfDocument(str(path))
    try:
        buffer = BytesIO()
        document[index].render(scale=RENDER_SCALE).to_pil().save(buffer, format="PNG")
    finally:
        document.close()
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


async def read_scanned_page(
    path: Path, index: int, chain: ProviderChain | None, question: str
) -> tuple[str, float | None]:
    """A page with no text of its own, read as a picture."""
    if chain is None:
        return PDF_NEEDS_VISION, None
    try:
        url = page_image(path, index)
    except Exception as exc:
        return PDF_RENDER_FAILED.format(error=exc), None
    try:
        return await describe(chain, url, question or PDF_SCAN_QUESTION)
    except ProviderError as exc:
        return PDF_VISION_FAILED.format(error=exc), None


def build_pdf_tool(roots: Sequence[Path], vision: ProviderChain | None) -> Tool:
    async def run(args: dict[str, Any]) -> ToolResult:
        path = resolve_pdf(str(args.get("path") or ""), roots)
        reader = open_pdf(path)
        count = len(reader.pages)
        if not count:
            raise ToolError(PDF_EMPTY)
        wanted = parse_pages(str(args.get("pages") or ""), count)
        question = str(args.get("question") or "")
        chunks: list[str] = []
        spent: float | None = None
        for index in wanted:
            text = (reader.pages[index].extract_text() or "").strip()
            if not text:
                text, cost = await read_scanned_page(path, index, vision, question)
                if cost is not None:
                    spent = (spent or 0.0) + cost
            chunks.append(f"{PDF_PAGE_HEADING.format(number=index + 1)}\n{text}")
        return ToolResult(
            ok=True,
            output="\n\n".join(chunks),
            cost_usd=spent,
            metered=spent is not None,
        )

    return Tool(
        name=PDF_TOOL_NAME,
        description=PDF_DESCRIPTION,
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": PDF_PARAM_PATH},
                "pages": {"type": "string", "description": PDF_PARAM_PAGES},
                "question": {"type": "string", "description": PDF_PARAM_QUESTION},
            },
            "required": ["path"],
        },
        run=run,
        parallel=True,
    )


def resolve_pdf(path: str, roots: Sequence[Path]) -> Path:
    """Where the file actually is, searched across the agent's workspace and then the crew
    home, where the master's inbox keeps what the person sent.

    Containment is lexical, so every root "resolves" a plain relative name whether or not
    anything is there. Returning the first of those would mean a delegate asked for a file
    in the inbox got told it was missing from its own workspace instead."""
    candidates = []
    for root in roots:
        try:
            candidate = resolve_inside(root, path)
        except ToolError:
            continue
        if candidate.is_file():
            return candidate
        candidates.append(candidate)
    if candidates:
        return candidates[0]  # nothing exists; report it against the first legal root
    raise ToolError(PDF_NOT_FOUND.format(path=path))
