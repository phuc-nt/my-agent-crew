"""The longer chains: turns where the model has to carry a result from one tool call into
the next, and turns where it has to delegate more than once or wait for a worker that
itself works in several steps. These are where a cheap model that passes the short tasks
tends to lose the thread, and where the loop's per-step overhead compounds."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from llm_bench_tasks import BRIEF_KEYWORD, SALES_ROWS, SALES_TOTAL, Task, _contains, _has_number

SALES_MAX_ITEM = "dinner"
SALES_AVERAGE = "317"  # 1587 / 5 = 317.4; the integer part is what every answer shares
TEAM_SIZE = "4"


def _all(*checks: Callable[[str, Path], bool]) -> Callable[[str, Path], bool]:
    return lambda answer, home: all(check(answer, home) for check in checks)


def _file_has(relative: str, *needles: str) -> Callable[[str, Path], bool]:
    def passed(answer: str, home: Path) -> bool:
        path = home / "workspace" / relative
        if not path.is_file():
            return False
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        return all(n.lower() in text for n in needles)

    return passed


def _file_lacks(relative: str, needle: str) -> Callable[[str, Path], bool]:
    def passed(answer: str, home: Path) -> bool:
        path = home / "workspace" / relative
        return path.is_file() and needle.lower() not in path.read_text(encoding="utf-8").lower()

    return passed


def _file_number(relative: str, number: str) -> Callable[[str, Path], bool]:
    def passed(answer: str, home: Path) -> bool:
        path = home / "workspace" / relative
        if not path.is_file():
            return False
        plain = re.sub(r"(?<=\d)[.,](?=\d{3}(?!\d))", "", path.read_text(encoding="utf-8"))
        return re.search(rf"(?<![\d.,]){number}(?![\d])", plain) is not None

    return passed


TASKS: tuple[Task, ...] = (
    # Three dependent tool calls by the master alone: compute, write, read back.
    Task(
        "pipeline",
        "Đọc data/sales.csv trong workspace, tìm mục (item) có amount lớn nhất và tổng cột "
        "amount. Ghi hai điều đó vào reports/sales.md, rồi đọc lại tệp vừa ghi và trả lời "
        "tên mục lớn nhất cùng con số tổng.",
        _all(
            _file_has("reports/sales.md", SALES_MAX_ITEM),
            _file_number("reports/sales.md", SALES_TOTAL),
            _contains(SALES_MAX_ITEM),
            _has_number(SALES_TOTAL),
        ),
    ),
    # Read, derive a second document, verify it with a search, answer from the source.
    Task(
        "revise",
        "Đọc docs/brief.md, tạo docs/brief-v2.md có nội dung giống hệt nhưng đổi «quận 3» "
        "thành «quận 1». Sau đó tìm (grep) chuỗi «quận 1» trong docs/ để chắc tệp mới đúng, "
        "và cuối cùng cho tôi biết đội ngũ của quán có mấy người.",
        _all(
            _file_has("docs/brief-v2.md", "quận 1", BRIEF_KEYWORD),
            _file_lacks("docs/brief-v2.md", "quận 3"),
            _has_number(TEAM_SIZE),
        ),
    ),
    # Three shell commands where each answer feeds the next question.
    Task(
        "shell_chain",
        "Dùng shell, làm lần lượt ba bước riêng biệt trên data/sales.csv (đường dẫn tương "
        "đối trong workspace): (1) đếm số dòng dữ liệu không kể tiêu đề, (2) in ra dòng có "
        "amount lớn nhất, (3) tính trung bình cột amount từ tổng và số dòng ở bước 1. Trả "
        "lời tên mục ở bước 2 và số trung bình ở bước 3.",
        _all(_contains(SALES_MAX_ITEM), _has_number(SALES_AVERAGE)),
    ),
    # One delegation whose worker takes several steps itself; the master then verifies.
    Task(
        "delegate_write",
        "Nhờ helper dùng shell tính tổng cột amount trong data/sales.csv và ghi đúng con "
        "số đó vào tệp reports/helper-total.txt trong workspace. Khi helper báo xong, bạn "
        "tự đọc tệp đó và trả lời con số đọc được.",
        _all(_file_number("reports/helper-total.txt", SALES_TOTAL), _has_number(SALES_TOTAL)),
        children=1,
    ),
    # Two delegations in sequence: the second is only asked after the first answers.
    Task(
        "delegate_twice",
        "Làm hai việc lần lượt, mỗi việc nhờ helper một lần riêng. Trước hết nhờ helper "
        "đếm số dòng dữ liệu (không kể tiêu đề) trong data/sales.csv. Nhận được kết quả "
        "rồi mới nhờ helper cho biết mục (item) có amount lớn nhất trong cùng tệp. Cuối "
        "cùng trả lời cả hai kết quả.",
        _all(_has_number(SALES_ROWS), _contains(SALES_MAX_ITEM)),
        children=2,
    ),
    # Two workers at once, then a combined answer.
    Task(
        "delegate_fanout",
        "Nhờ helper đếm số dòng dữ liệu (không kể tiêu đề) trong data/sales.csv, đồng thời "
        "nhờ auditor đọc docs/brief.md và cho biết tên quán cà phê. Gộp hai kết quả lại "
        "trong câu trả lời cho tôi.",
        _all(_has_number(SALES_ROWS), _contains(BRIEF_KEYWORD)),
        children=2,
    ),
)
