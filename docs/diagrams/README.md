---
layout: default
title: Sơ đồ harness
---

# Sơ đồ harness

Năm sơ đồ vẽ bằng archify, mỗi sơ đồ ba file cùng tên:

| Tên | Kiểu archify | Dùng trong |
|---|---|---|
| `crew-architecture` | architecture | [system-architecture.md §2](../system-architecture.md#2-giải-phẫu-harness) |
| `turn-sequence` | sequence | [system-architecture.md §3](../system-architecture.md#3-một-lượt-chat-từ-telegram-đến-câu-trả-lời) |
| `delegation-workflow` | workflow | [system-architecture.md §4](../system-architecture.md#4-master-giao-việc-cho-đội) |
| `approval-lifecycle` | lifecycle | [system-architecture.md §5](../system-architecture.md#5-cổng-duyệt-tool) |
| `context-dataflow` | dataflow | [system-architecture.md §6](../system-architecture.md#6-ngữ-cảnh-đi-vào-trí-nhớ-đi-ra) |

- `.json`: spec nguồn (schema archify). Sửa ở đây.
- `.html`: bản tương tác, script và style inline, xem bằng trình duyệt hoặc serve tĩnh. Không dán vào markdown.
- `.svg`: bản tĩnh, nhúng trong `.md`.
- `index.html`: trang gom cả năm.

## Tái tạo

Skill `archify` nằm trong kit riêng của tác giả (`my-crew/.claude/skills/archify/`), không thuộc repo này. Từ thư mục skill:

```bash
node bin/archify.mjs validate <type> <name>.json --quality showcase --json
node bin/archify.mjs deliver  <type> <name>.json <name>.html --quality showcase --json
node bin/to-svg.mjs <name>.html <name>.svg
node bin/archify.mjs visual-check <name>.html --json
```

`<type>` là một trong `architecture`, `sequence`, `workflow`, `lifecycle`, `dataflow`. `validate` phải trả `ok: true` trước khi `deliver`. `visual-check` báo viewer cao hơn khung 1440×900 (khoảng 1330 px) vì trang có tiêu đề, thanh view, chú giải và thẻ; ví dụ mẫu của skill cũng vậy, nên chấp nhận. Lệnh `visual-check` để lại ảnh chụp `*.visual-check.*` cạnh sơ đồ; xoá trước khi commit.

## Bài học khi viết spec

- **architecture**: khi nhiều đường vào cùng một cạnh của một khối, để router tự đi (bỏ `fromSide`/`toSide`/`via`) rồi chỉ đặt `labelAt` cho nhãn bị va; đặt `via` tường minh chỉ khi cần đường không đi men theo viền region.
- **workflow**: cạnh dọc cùng cột không được ghi `route: "drop"` hay `fromSide`/`toSide`; để tự đi.
- **lifecycle**: lane ngoài lane chính là dải kết quả, chỉ có cột 0..2 và lệch phải so với lane chính (cột 0 của dải trùng cột 2 của lane chính). `route: "straight"` chỉ dùng khi hai trạng thái thẳng hàng theo chiều dọc. Sublabel tối đa khoảng 29 ký tự. Note của view tối đa 140 ký tự.
- **dataflow**: hai luồng đổ vào cùng cạnh dưới của một node có thể dùng chung một trục dọc (cùng `via` x) thay vì tách 7 px; nhãn luồng cao khoảng 27 px, đặt `labelAt` khi đoạn thẳng ngắn hơn nhãn.
