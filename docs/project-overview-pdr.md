---
layout: default
title: Tổng quan sản phẩm và yêu cầu
---

# Tổng quan sản phẩm và yêu cầu (PDR)

**Phiên bản**: 0.3.0 · **Cập nhật**: 2026-09-22

## 1. Vấn đề

Một người muốn có vài trợ lý AI làm việc thật cho mình — thư ký nhắc việc, huấn luyện viên sức khoẻ, đội hỗ trợ lập trình — chạy trên máy cá nhân, dùng model rẻ qua OpenRouter, nói chuyện qua Telegram và web. Các harness có sẵn hoặc quá nặng (nhiều dịch vụ, DB ngoài), hoặc quá mỏng (một script gọi API, không có duyệt tool, không nhớ), hoặc khoá vào một nhà cung cấp model.

## 2. Giải pháp

my-agent-crew: một tiến trình Python, một tệp SQLite, một thư mục home. Nhiều agent, mỗi agent là một thư mục tệp văn bản. Một vòng lặp `run_turn` cho mọi kênh và mọi job, với cổng duyệt tool, trần chi phí, và trí nhớ trên đĩa mà người dùng đọc và sửa được.

## 3. Người dùng

| Ai | Cần gì |
|---|---|
| Chủ máy (một người) | chat với master, duyệt tool, xem agent làm gì, sửa trí nhớ, tin lịch chạy đúng giờ |
| Người tự xây agent | thêm agent bằng thư mục, thêm tool bằng một hàm, thêm skill bằng markdown |
| Người học harness | đọc code và tài liệu hiểu được cấu thành, không cần biết trước |

## 4. Tính năng (v0.3.0)

- Nhiều agent với persona, tool, model, lịch riêng; master giao việc qua `delegate`.
- Web UI: chat SSE, thanh duyệt, timeline run, panel đội, job, trí nhớ, thống kê chi phí.
- Telegram cho master: tin, ảnh, album; đội trả lời qua master.
- Scheduler cron trong tiến trình; job là cuộc trò chuyện autonomous.
- Trí nhớ: ghi chú ngày, `MEMORY.md`, facts người dùng dùng chung, consolidate thành đề xuất có duyệt.
- Kit `.agents/` kiểu Claude Code: lệnh, agent, skill, hook.
- Provider chain có fallback nhìn thấy; provider giả cho test.
- Mẫu agent và CLI `agent add`.

## 5. Yêu cầu

**Chức năng**
- Mọi tin từ người đi qua `POST /api/inbound`; job đi thẳng `run_turn`. Không có đường nào khác tới model.
- Tool có `requires_approval` phải dừng lượt cho tới khi có quyết định, trừ cuộc trò chuyện autonomous; `shell_ask_patterns` hỏi cả khi autonomous.
- Approval không được trả lời sau `approval_ttl_seconds` coi như từ chối.
- Mỗi lượt là một run có step, xem được sau khi kết thúc.
- Chi phí lượt con cộng vào lượt cha; trần chi phí của con không vượt phần còn lại của cha.

**Phi chức năng**
- Một tiến trình, không dịch vụ ngoài ngoài OpenRouter và Telegram.
- Khởi động lại bất kỳ lúc nào không mất dữ liệu: mọi trạng thái ở SQLite hoặc tệp.
- Bí mật chỉ ở tệp env; log không chứa token.
- Backend và web có test chạy trong CI, không cần mạng.

## 6. Ràng buộc

- Python 3.12+, FastAPI, SQLite; web React 19 đóng gói sẵn.
- Định danh tiếng Anh, chuỗi hiển thị tiếng Việt tách riêng.
- Home nằm ngoài repo; repo không bao giờ chứa dữ liệu người dùng.

## 7. Tiêu chí thành công

- Bộ cài thật (master + Pong + HLV + 8 vai trò) chạy liên tục qua launchd, lịch nổ đúng giờ địa phương, Telegram trả lời.
- Người chưa từng xây harness đọc [system-architecture.md](system-architecture.md) và trả lời được: tin nhắn đi qua những khối nào, tool được duyệt ở đâu, agent nhớ bằng gì.
- `pytest`, `vitest`, Playwright xanh trong CI.

## 8. Rủi ro

| Rủi ro | Giảm nhẹ |
|---|---|
| Model rẻ gọi tool sai hoặc lặp | `max_steps`, `cost_cap_usd`, `tool_output_chars`, cổng duyệt |
| Agent con tốn hết ngân sách cha | trần con = phần còn lại của cha |
| Trí nhớ phình hoặc lệch | consolidate là đề xuất có duyệt, giữ bản cũ |
| Lộ bí mật qua log hoặc doc | redact, tệp env ngoài repo, quy tắc placeholder trong doc |
| Một cuộc trò chuyện chạy song song hai lượt | `InboundBusy` 409 |

## 9. Lộ trình

- Đã: v0.1 một agent + web; v0.2 nhiều agent, delegate, Telegram; v0.3 kit `.agents/`, ảnh qua vision route, album, múi giờ, persona ba tệp, bộ tài liệu này.
- Cân nhắc: Telegram cho từng agent; TTL cho lượt delegate; Dockerfile; tìm kiếm trí nhớ tốt hơn.

## 10. Thuật ngữ

| Từ | Nghĩa ở đây |
|---|---|
| harness | phần mềm bao quanh model: ngữ cảnh, tool, trí nhớ, kiểm soát |
| master | agent nhận tin từ người và giao việc |
| lượt (turn) | một lần `run_turn`: từ tin mới đến câu trả lời cuối |
| run / step | bản ghi một lượt và các bước trong nó |
| approval | yêu cầu duyệt một tool call |
| autonomous | cuộc trò chuyện bỏ qua cổng duyệt |
| delegate | tool để master chạy một lượt con ở agent khác |
| persona | `AGENTS.md` + `SOUL.md` |
| kit | thư mục `.agents/` kiểu Claude Code |
| home | `~/.my-agent-crew/` |

## Câu hỏi mở

- Chưa có yêu cầu về nhiều người dùng; `users/owner/` là giả định một chủ.
