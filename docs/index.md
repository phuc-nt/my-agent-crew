---
layout: default
title: Tài liệu my-agent-crew
---

# Tài liệu my-agent-crew

**Phiên bản**: 0.3.0 · **Cập nhật**: 2026-09-22

my-agent-crew là một agent harness nhỏ chạy trên máy cá nhân: nhiều agent, mỗi agent là một thư mục tệp, một vòng lặp chung có cổng duyệt tool, trí nhớ trên đĩa, web UI và Telegram. Bộ tài liệu này viết cho người chưa từng xây harness, minh hoạ bằng một bộ cài thật.

## Thứ tự đọc

| # | Tài liệu | Đọc khi |
|---|---|---|
| 1 | [system-architecture.md](system-architecture.md) | muốn hiểu harness gồm gì, mỗi phần làm gì, khớp nhau ra sao (5 sơ đồ) |
| 2 | [project-overview-pdr.md](project-overview-pdr.md) | muốn biết vì sao nó tồn tại và nó cam kết gì |
| 3 | [deployment-guide.md](deployment-guide.md) | muốn cài, chạy thường trực, thêm agent, publish doc |
| 4 | [codebase-summary.md](codebase-summary.md) | sắp sửa code, cần biết khối nào ở tệp nào |
| 5 | [code-standards.md](code-standards.md) | sắp commit |
| — | [design.md](design.md), [agents.md](agents.md), [tools.md](tools.md), [memory.md](memory.md), [channels.md](channels.md), [testing.md](testing.md) | tham chiếu sâu từng mảng |

## Năm sơ đồ động

| Sơ đồ | Câu hỏi nó trả lời | Xem |
|---|---|---|
| Giải phẫu harness | có những khối nào, ở đâu | [HTML](diagrams/crew-architecture.html) · [SVG](diagrams/crew-architecture.svg) |
| Một lượt qua Telegram | tin nhắn đi qua đâu, theo thứ tự nào | [HTML](diagrams/turn-sequence.html) · [SVG](diagrams/turn-sequence.svg) |
| Master giao việc | ai làm gì, cô lập ở đâu | [HTML](diagrams/delegation-workflow.html) · [SVG](diagrams/delegation-workflow.svg) |
| Vòng đời duyệt tool | khi nào dừng, ai quyết, hết hạn thì sao | [HTML](diagrams/approval-lifecycle.html) · [SVG](diagrams/approval-lifecycle.svg) |
| Ngữ cảnh và trí nhớ | model biết gì, nhớ bằng gì | [HTML](diagrams/context-dataflow.html) · [SVG](diagrams/context-dataflow.svg) |

Gallery: [diagrams/index.html](diagrams/index.html). Spec và cách tái tạo: [diagrams/README.md](diagrams/README.md).

## Bắt đầu nhanh

```bash
uv sync
MY_AGENT_ROUTES=fake:echo uv run python -m my_agent_crew   # thử không tốn tiền
# rồi với model thật:
export OPENROUTER_API_KEY=… && uv run python -m my_agent_crew
```

## Publish để sơ đồ chuyển động

Bộ tài liệu này đã publish tại **<https://phuc-nt.github.io/my-agent-crew/>** (GitHub Pages, nguồn `main` / `/docs`) — mở link "HTML" ở bảng trên để xem sơ đồ chuyển động.

Bản `.html` của sơ đồ là trang tự chứa; chỉ cần phục vụ `docs/` như site tĩnh. Nhanh nhất là GitHub Pages với nguồn `/docs`, hoặc `python3 -m http.server 8080 --directory docs` trên máy. Chi tiết và các cách khác ở [deployment-guide.md §9](deployment-guide.md#9-publish-bộ-doc-để-sơ-đồ-archify-chuyển-động).

## Quy ước

- Mỗi tài liệu chuẩn có front matter, dòng phiên bản, và mục "Câu hỏi mở" ở cuối.
- Ví dụ lấy từ bộ cài thật nhưng đã bỏ định danh, số liệu và đường dẫn cá nhân.
- Định danh trong code là tiếng Anh; tài liệu là tiếng Việt.

## Câu hỏi mở

- Chưa có bản tiếng Anh của bộ tài liệu.
