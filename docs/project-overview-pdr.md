---
layout: default
title: Tổng quan sản phẩm và yêu cầu
---

# Tổng quan sản phẩm và yêu cầu (PDR)

**Phiên bản**: 0.8.0 · **Cập nhật**: 2026-09-26

## 1. Vấn đề

Một người muốn có vài trợ lý AI làm việc thật cho mình — thư ký nhắc việc, huấn luyện viên sức khoẻ, đội hỗ trợ lập trình — chạy trên máy cá nhân, dùng model rẻ qua OpenRouter, nói chuyện qua Telegram và web. Các harness có sẵn hoặc quá nặng (nhiều dịch vụ, DB ngoài), hoặc quá mỏng (một script gọi API, không có duyệt tool, không nhớ), hoặc khoá vào một nhà cung cấp model.

## 2. Giải pháp

my-agent-crew: một tiến trình Python, một tệp SQLite, một thư mục home. Nhiều agent, mỗi agent là một thư mục tệp văn bản. Một vòng lặp lượt chung cho mọi kênh và mọi job, với cổng duyệt tool, trần chi phí, và trí nhớ trên đĩa mà người dùng đọc và sửa được.

## 3. Người dùng

| Ai | Cần gì |
|---|---|
| Chủ máy (một người) | chat với master, duyệt tool, xem agent làm gì, sửa trí nhớ, tin lịch chạy đúng giờ |
| Người tự xây agent | thêm agent bằng thư mục, thêm tool bằng một hàm, thêm skill bằng markdown |
| Người học harness | đọc code và tài liệu hiểu được cấu thành, không cần biết trước |

## 4. Tính năng (v0.5.0)

- Nhiều agent với persona, tool, model, lịch riêng; master giao việc qua `delegate`.
- Web UI hai khu: **khung chat** (chat SSE có markdown, tiêu đề tự đặt, tiến trình lượt chạy và
  hoạt động của riêng cuộc đang mở) và **khu quản lý** chín tab định tuyến bằng hash — Hoạt động,
  Duyệt, Đội, Công cụ, Lịch chạy, Ghi nhớ, Chi phí, Kết nối, Cài đặt.
- Quản lý đội ngay trên web: thêm/sửa/xoá agent, sửa tệp tính cách, xem lời nhắc hệ thống đã ghép,
  ma trận ai dùng tool nào, trang kết nối.
- Telegram cho master: tin, ảnh, album; đội trả lời qua master.
- Scheduler cron trong tiến trình; job là cuộc trò chuyện autonomous.
- Trí nhớ: ghi chú ngày, `MEMORY.md`, facts người dùng dùng chung, consolidate thành đề xuất có duyệt.
- Agent làm việc với người: `ask_user` hỏi lại ở ngã ba thật (web và Telegram đều trả lời được),
  `progress_note` báo đang làm gì, dòng `FILE:` gửi tệp đính kèm, `pdf_read` đọc tài liệu.
- Vault wiki trong trí nhớ agent: trang theo chủ đề có nguồn và liên kết `[[...]]`, dựng lại từ ghi chú.
- `shell_network: false`: sandbox hệ điều hành cho agent giữ dữ liệu không được rời máy.
- Kit `.agents/` kiểu Claude Code: lệnh, agent, skill, hook.
- Provider chain có fallback nhìn thấy; provider giả cho test.
- Mẫu agent và CLI `agent add`.

## 5. Yêu cầu

**Chức năng**
- Mọi tin từ người đi qua `POST /api/inbound`; job đi thẳng vào cùng vòng lặp lượt. Không có đường nào khác tới model.
- Tool cần duyệt phải dừng lượt cho tới khi có quyết định, trừ cuộc trò chuyện autonomous; `shell_ask_patterns` hỏi cả khi autonomous.
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

- Bộ cài thật (master + ba agent cá nhân + ba agent kỹ thuật) chạy liên tục qua launchd, lịch nổ đúng giờ địa phương, Telegram trả lời.
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

## 9. Lộ trình và việc còn mở

**Hoàn thành**

- v0.1 một agent + web
- v0.2 nhiều agent, delegate, Telegram
- v0.3 kit `.agents/`, ảnh qua vision route, album, múi giờ, persona ba tệp, bộ tài liệu
- v0.4 web UI dựng lại quanh việc nhìn thấy agent đang làm gì, quản lý cả đội trên web
- v0.5 hỏi lại, báo tiến độ, gửi tệp, wiki trí nhớ, sandbox ngoại tuyến

Chi tiết mỗi bản: [CHANGELOG](../CHANGELOG.md).

**Việc còn mở**

- **Provider `fake` (echo) trong đội thật.** Trình sửa tuyến không cho thêm `fake` vào đội chưa
  dùng nó, nhưng `config.yaml` sửa tay vẫn nhận, và đội đó sẽ trả lời bằng tiếng vọng. Chưa
  quyết: giữ `fake` cho demo/test, hay chỉ bật nó khi không có provider thật nào.
- **Báo "tin bị ngắt" có thể không kịp gửi dưới launchd.** Khi dừng, bot chờ lượt đang chạy tới
  30 s rồi mới báo (tối đa 5 s). launchd mặc định chỉ đợi 20 s sau SIGTERM rồi SIGKILL, nên
  plist cần `ExitTimeOut` 45 như mẫu ở [deployment-guide §5](deployment-guide.md).
- **Trình sửa tuyến chưa có nút đổi thứ tự.** Muốn đưa tuyến lên trước thì phải xoá rồi thêm lại.
- **Server không có đăng nhập.** Chỉ hàng rào Host/Origin chặn trang lạ; ai tới được cổng là
  điều khiển được đội. Chỉ dùng cục bộ hoặc trong tailnet riêng (`MY_AGENT_ALLOWED_HOSTS`).
- **Tài liệu chỉ có tiếng Việt.**
- **Cân nhắc:**
  - Telegram riêng cho từng agent; hiện chỉ master có bot.
  - TTL cho lượt `delegate`.
  - Dockerfile.
  - Tìm kiếm trí nhớ tốt hơn so khớp từ.
  - Trang xem lại lượt chạy hiện cả lượt con được `delegate`.

## 10. Thuật ngữ

| Từ | Nghĩa ở đây |
|---|---|
| harness | phần mềm bao quanh model: ngữ cảnh, tool, trí nhớ, kiểm soát |
| master | agent nhận tin từ người và giao việc |
| lượt (turn) | một vòng của vòng lặp agent: từ tin mới đến câu trả lời cuối |
| run / step | bản ghi một lượt và các bước trong nó |
| approval | yêu cầu duyệt một tool call |
| autonomous | cuộc trò chuyện bỏ qua cổng duyệt |
| delegate | tool để master chạy một lượt con ở agent khác |
| persona | `AGENTS.md` + `SOUL.md` |
| kit | thư mục `.agents/` kiểu Claude Code |
| home | `~/.my-agent-crew/` |

## Câu hỏi mở

- Chưa có yêu cầu về nhiều người dùng; `users/owner/` là giả định một chủ.
