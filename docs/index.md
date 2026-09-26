---
layout: default
title: Tài liệu my-agent-crew
---

# Tài liệu my-agent-crew

**Phiên bản**: 0.8.0 · **Cập nhật**: 2026-09-26

my-agent-crew là một agent harness nhỏ chạy trên máy cá nhân: nhiều agent, mỗi agent là một thư mục tệp, một vòng lặp chung có cổng duyệt tool, trí nhớ trên đĩa, web UI và Telegram. Bộ tài liệu này viết cho người chưa từng xây harness, minh hoạ bằng một bộ cài thật.

## Thứ tự đọc

| # | Tài liệu | Đọc khi |
|---|---|---|
| 1 | [Kiến trúc hệ thống](system-architecture.md) | muốn hiểu harness gồm gì, mỗi phần làm gì, khớp nhau ra sao (5 sơ đồ động) |
| 2 | [Tổng quan sản phẩm](project-overview-pdr.md) | muốn biết vì sao nó tồn tại và nó cam kết gì |
| 3 | [Cài đặt và vận hành](deployment-guide.md) | muốn cài, chạy thường trực, thêm agent, publish doc |
| 4 | [Bản đồ mã nguồn](codebase-summary.md) | sắp mở code, cần định hướng theo gói và bảng API (không phải bản đồ từng tệp) |
| 5 | [Chuẩn viết code](code-standards.md) | sắp commit |
| — | [Thiết kế](design.md) · [Agent](agents.md) · [Tool](tools.md) · [Trí nhớ](memory.md) · [Kênh](channels.md) · [Kiểm thử](testing.md) | tham chiếu sâu từng mảng |
| — | [Nhật ký thay đổi](../CHANGELOG.md) | muốn biết bản này khác bản trước ở đâu |

## Năm sơ đồ động

Sơ đồ chạy ngay trong trang — bấm tên view trên thanh để xem từng lớp:

<iframe src="diagrams/crew-architecture.html" title="Giải phẫu harness my-agent-crew" loading="lazy" style="width:100%;height:1140px;border:1px solid #d0d7de;border-radius:8px;background:#fff"></iframe>

Bốn sơ đồ còn lại nằm trong [Kiến trúc hệ thống](system-architecture.md), cũng nhúng động:

| Sơ đồ | Câu hỏi nó trả lời | Xem riêng |
|---|---|---|
| Giải phẫu harness | có những khối nào, ở đâu | [HTML](diagrams/crew-architecture.html) · [SVG](diagrams/crew-architecture.svg) |
| Một lượt qua Telegram | tin nhắn đi qua đâu, theo thứ tự nào | [HTML](diagrams/turn-sequence.html) · [SVG](diagrams/turn-sequence.svg) |
| Master giao việc | ai làm gì, cô lập ở đâu | [HTML](diagrams/delegation-workflow.html) · [SVG](diagrams/delegation-workflow.svg) |
| Vòng đời duyệt tool | khi nào dừng, ai quyết, hết hạn thì sao | [HTML](diagrams/approval-lifecycle.html) · [SVG](diagrams/approval-lifecycle.svg) |
| Ngữ cảnh và trí nhớ | model biết gì, nhớ bằng gì | [HTML](diagrams/context-dataflow.html) · [SVG](diagrams/context-dataflow.svg) |

Gallery: [diagrams/index.html](diagrams/index.html). Spec và cách tái tạo: [Sơ đồ harness](diagrams/README.md).

## Bắt đầu nhanh

```bash
uv sync
MY_AGENT_ROUTES=fake:echo uv run python -m my_agent_crew   # thử không tốn tiền
# rồi với model thật:
export OPENROUTER_API_KEY=… && uv run python -m my_agent_crew
```

## Publish để sơ đồ chuyển động

Bộ tài liệu này đã publish tại **<https://phuc-nt.github.io/my-agent-crew/>** (GitHub Pages, nguồn `main` / `/docs`) — sơ đồ chạy ngay trong trang. Trên GitHub hoặc trình đọc markdown, iframe không hiện; dùng link "SVG" trong bảng trên.

Bản `.html` của sơ đồ là trang tự chứa; chỉ cần phục vụ `docs/` như site tĩnh. Nhanh nhất là GitHub Pages với nguồn `/docs`, hoặc `python3 -m http.server 8080 --directory docs` trên máy. Chi tiết và các cách khác ở [deployment-guide.md §9](deployment-guide.md#9-publish-bộ-doc-để-sơ-đồ-archify-chuyển-động).

## Quy ước

- Mỗi tài liệu chuẩn có front matter, dòng phiên bản, và mục "Câu hỏi mở" ở cuối.
- Ví dụ lấy từ bộ cài thật nhưng đã bỏ định danh, số liệu và đường dẫn cá nhân.
- Tiếng Anh ở mọi nơi (code, README, CHANGELOG, commit); tiếng Việt chỉ ở `docs/` và chuỗi hiển thị cho người dùng — xem [code-standards.md §1](code-standards.md#1-python).
- Code là nguồn sự thật. Tài liệu mô tả khái niệm, luồng và hợp đồng người dùng thấy; không ghi tên tệp, hàm, tệp test hay số liệu — xem [code-standards.md §7](code-standards.md#7-tài-liệu).

## Câu hỏi mở

- `docs/` cố ý chỉ có tiếng Việt (viết cho đội maintain người Việt); chưa quyết có bản tiếng Anh cho người ngoài không.
