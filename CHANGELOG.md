---
layout: default
title: Nhật ký thay đổi
---

# Nhật ký thay đổi

Mọi thay đổi đáng kể của my-agent-crew. Định dạng theo [Keep a Changelog](https://keepachangelog.com/vi/1.1.0/),
số hiệu theo [SemVer](https://semver.org/lang/vi/). Số hiệu chung cho cả backend và web: cùng một
bản phát hành, `pyproject.toml` và `web/package.json` luôn cùng số.

## [Chưa phát hành]

### Thêm

- **`web_search` chạy được trên mọi máy** — thêm nguồn DuckDuckGo không cần khoá, đứng cuối
  danh sách nên luôn có ít nhất một nguồn. Thứ tự thử: firecrawl → Brave → Tavily → DuckDuckGo;
  nguồn hỏng bị bỏ qua và ghi log, chỉ khi tất cả cùng hỏng thì công cụ mới báo không tới được
  dịch vụ. Trước đây cả đội không có công cụ này vì không máy nào đặt khoá tìm kiếm.
- **`fetch_url` đọc trang dạng markdown qua firecrawl** — giữ tiêu đề, danh sách và bảng thay vì
  chữ thô, hạn mức nâng từ 6 000 lên 20 000 ký tự. Firecrawl hỏng thì tự quay về chữ thô.
- **Hai biến môi trường mới** `FIRECRAWL_BASE_URL` và `FIRECRAWL_API_KEY`. Khoá chỉ được gửi khi
  có đặt, nên host tự dựng không cần khoá và một base url gõ nhầm không mang khoá đi đâu cả.
- **Trang Kết nối hiện thứ tự nguồn tìm kiếm** và host firecrawl đang dùng, đủ để phân biệt
  "chưa bật" với "cấu hình sai".
- **Kỹ năng khai báo được lệnh nó cần** — `requires.bins: [gws]` và `cliHelp: "gws --help"`
  trong front matter. Máy thiếu lệnh thì kỹ năng vẫn nằm trong danh sách kèm nhãn
  "thiếu: gws", và thân kỹ năng mở đầu bằng một dòng cảnh báo — agent biết vì sao không làm
  được thay vì thất bại giữa chừng. Tab Cài đặt hiện cùng nhãn đó.
- **Một quy tắc trong lời nhắc hệ thống**: lệnh chưa chắc cú pháp thì chạy `--help` một lần,
  không thử quá hai cú pháp mới cho cùng một việc. Có vì một lượt chạy theo lịch đã đốt 16
  bước đoán tham số của một chương trình nó chưa từng gặp.
- **Job theo lịch tự gắn kỹ năng mà prompt gọi tên** — chỉ tên có gạch nối (`gws-shared`),
  vì một tên một từ như `ledger` xuất hiện trong cả những prompt không liên quan.
- **Mẫu script gom dữ liệu cho job** ở `docs/examples/job-data-script.sh`: một lệnh trả một
  khối JSON, mỗi nguồn hỏng tự ghi lỗi của nó thay vì làm hỏng cả lượt chạy.

### Thay đổi

- `web_search` không còn nằm trong nhóm công cụ tuỳ chọn: nó luôn được dựng, nên một agent khai
  `web_search` trong `tools:` không còn im lặng mất công cụ.
- **`docs/tools.md` nói rõ hệ quả của việc `shell_run` lọc biến môi trường**: script chạy được
  ở terminal của bạn vẫn có thể hỏng khi job chạy, vì mọi biến ngoài danh sách cho phép đều
  biến mất. Script cần một giá trị không phải bí mật thì tự đọc từ tệp, đừng trông vào biến
  môi trường — nới danh sách cho phép là trao khoá API cho mọi lệnh do model viết. Hành vi lọc
  không đổi; nay đã có test neo lại.

## [0.4.0] — 2026-09-22

Bản này dựng lại web UI quanh một ý: **nhìn thấy agent đang làm gì**, và quản lý được cả đội
ngay trên web thay vì sửa YAML bằng tay.

### Thêm

- **Reply hiển thị dạng markdown** — tiêu đề, danh sách, bảng, khối code có tô màu, thay cho một
  khối chữ thô. Liên kết mở tab mới; HTML thô không được render.
- **Tự đặt tiêu đề cuộc trò chuyện** từ câu đầu tiên của người dùng, chạy nền sau khi lượt kết
  thúc nên không làm chậm câu trả lời. Đổi tên tay vẫn được và luôn thắng tiêu đề tự đặt.
- **Tiến trình chạy ngay trong khung chat**: đang gọi model hay đang chạy tool, bước thứ mấy,
  đã tiêu bao nhiêu — thấy ngay lúc đang chờ, không phải mở tab khác.
- **Khu quản lý tách khỏi chat**, điều hướng bằng hash route `#/manage/<section>` với chín tab:
  Hoạt động, Duyệt, Đội, Công cụ, Lịch chạy, Ghi nhớ, Chi phí, Kết nối, Cài đặt. Tải lại trang
  vẫn ở đúng tab.
- **Mở riêng một lượt chạy** bằng `#/manage/activity/<run_id>` — chia sẻ được, tải lại vẫn ở đó,
  và mở được cả lượt cũ mà danh sách hoạt động không còn giữ.
- **Quản lý agent trên web**: thêm, sửa, xoá agent (cả master lẫn agent con), sửa tệp tính cách
  (`AGENTS.md`, `SOUL.md`), xem lời nhắc hệ thống đã ghép để biết model thật sự đọc gì.
- **Ma trận công cụ** — cả đội dùng những tool nào, agent nào dùng cái gì, trong một bảng.
- **Trang kết nối** — khoá API, Telegram, vision route, xem chỗ nào đã cấu hình chỗ nào chưa.
- **HTTP API quản lý agent**: `POST /api/agents`, `PATCH /api/agents/{id}`, `DELETE /api/agents/{id}`,
  `PUT /api/agents/{id}/files/{name}`, `GET /api/agents/{id}/prompt`, `POST /api/agents/reload`,
  `GET /api/tools`, `GET /api/connections`.
- **`scripts/gates.sh`** — chạy cả chín cổng CI bằng một lệnh, theo đúng thứ tự `ci.yml`, dừng ở
  cổng đỏ đầu tiên và gọi tên nó (~22 giây). Cùng với đó là một test giữ số hiệu phiên bản ở năm
  chỗ khai báo không lệch nhau.

### Đổi

- **Cột "Hoạt động" giờ thuộc về cuộc trò chuyện đang mở**, nằm trong khung chat, thay vì một
  thanh chung hiện hoạt động của mọi cuộc. Hoạt động toàn đội chuyển sang tab Hoạt động của khu
  quản lý.
- Các tab Đội, Lịch chạy, Duyệt, Ghi nhớ, Chi phí được phân loại lại theo phạm vi: cái nào chung
  cả đội thì nằm ở khu quản lý, cái nào thuộc một cuộc trò chuyện thì nằm trong khung chat.
- Ghi `arguments` của một bước tool dưới dạng mapping tên → giá trị (trước đây cả cụm bị ép thành
  một chuỗi, hiển thị thành một hàng mỗi ký tự). Phía đọc chịu được cả hai hình dạng nên các lượt
  chạy ghi trước bản này vẫn xem được.

### Sửa

- Lượt trả lời rỗng không còn bị coi là lượt đã xong — web UI im lặng không báo gì.
- Lượt chạy vừa kết thúc khi đang xem giờ hiện đúng trạng thái và thời điểm kết thúc: bản trong
  bộ nhớ của trang thiếu thời điểm đó, nên trang đọc lại đúng một lần vào khung mà trạng thái đổi.
- Sáu tệp Python được đưa về đúng định dạng `ruff format`; cổng `ruff format --check` trong CI
  từ nay được chạy ở mọi vòng phát triển, không chỉ `ruff check`.

### Lưu ý khi nâng cấp

Không cần migration. Lược đồ SQLite chỉ thêm bảng, đều `CREATE TABLE IF NOT EXISTS`; tệp
`config.yaml`, `agent.yaml` và thư mục home giữ nguyên hình dạng. Nâng cấp là kéo code mới rồi
khởi động lại tiến trình.

## [0.3.0] — 2026-09-21

- Kit `.agents/` kiểu Claude Code: lệnh, agent, skill, hook.
- Đọc ảnh qua vision route; album Telegram gộp trong một lượt; múi giờ của người dùng.
- Persona ba tệp; bộ tài liệu tiếng Việt với năm sơ đồ động, publish lên GitHub Pages.

## [0.2.0]

- Nhiều agent, `delegate` để master giao việc cho agent khác, kênh Telegram.

## [0.1.0]

- Một agent, vòng lặp `run_turn` có cổng duyệt tool, web UI, trí nhớ trên đĩa.

[0.4.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.4.0
[0.3.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.3.0
[0.2.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.2.0
[0.1.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.1.0
