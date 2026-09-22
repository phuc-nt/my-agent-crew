"""What `pdf_read` says to the agent and to the person.

A page it could not read gets a bracketed line saying why, in place of that page's text.
That is deliberate: the agent must be able to tell a page that was blank from a page it
failed at, and an exception would throw away every page that did read."""

from __future__ import annotations

PDF_NOT_FOUND = "Không có file PDF ở '{path}'."
PDF_NOT_PDF = "'{path}' không phải file PDF."
PDF_BROKEN = "Không đọc được file PDF: {error}."
PDF_EMPTY = "File PDF không có trang nào."
PDF_BAD_RANGE = "Khoảng trang '{pages}' không hợp lệ. Viết dạng '1-5' hoặc '3'."
PDF_OUT_OF_RANGE = "File chỉ có {count} trang, không có trang {page}."
PDF_PAGE_HEADING = "--- Trang {number} ---"
PDF_NEEDS_VISION = (
    "[Trang scan, không có route thị giác nào được cấu hình nên không đọc được."
    " Thêm 'vision_routes' cho agent để đọc các trang dạng ảnh.]"
)
PDF_RENDER_FAILED = "[Không dựng được ảnh của trang này: {error}]"
PDF_VISION_FAILED = "[Không đọc được trang scan: {error}]"
PDF_SCAN_QUESTION = (
    "Đây là ảnh chụp một trang tài liệu. Hãy chép lại toàn bộ chữ trên trang,"
    " giữ nguyên thứ tự và cách xuống dòng. Không thêm nhận xét nào."
)
