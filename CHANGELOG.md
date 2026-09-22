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

- **Wiki bộ nhớ: mỗi agent một kho trang** ở `memory/wiki/`, chia ba thư mục `entities`,
  `concepts`, `syntheses`. Ghi chú hằng ngày viết theo ngày — đúng cho lúc ghi, sai cho lúc
  hỏi: "hạn Eco là khi nào" nằm rải trong mười một ghi chú. Một trang gom các mảnh đó lại
  dưới tên của chính thứ đó, nên câu hỏi có một chỗ để được trả lời. Lời nhắc biên dịch nói
  rõ ba thư mục khác nhau ở chỗ nào — có tên riêng, ý niệm lặp lại, hay kết luận bắc qua
  nhiều thứ — vì chỉ liệt kê tên chúng trong mẫu JSON thì model dồn hết vào `entities`.
- **Mỗi trang phải khai nguồn.** `sources` ghi `note:YYYY-MM-DD` hoặc `conv:<id>`;
  `wiki_apply` từ chối trang không có nguồn. Đây không phải kiểm tra đầu vào mà là điểm
  chính của kho: một trang không nói được nó từ đâu ra là một trang tự bịa, và cho lọt một
  trang như vậy làm mọi trang còn lại bớt đáng tin.
- **Chỉ một phần tệp thuộc về máy.** Khối liên kết giữa hai dấu mốc được viết lại sau mỗi
  lần biên dịch; phần còn lại thuộc về người hoặc model đã viết nó và được trả về nguyên
  vẹn. Không có ranh giới đó thì kho hoặc đóng băng, hoặc không tin được.
- **Liên kết `[[Tên trang]]`** dựng thành đồ thị hai chiều, viết lại sau mỗi lần biên dịch
  hoặc mỗi lần sửa trang qua web — sửa một liên kết làm đổi thứ *trang khác* nói là nó
  được trỏ tới từ đâu.
- **Biên dịch từ ghi chú** nối tiếp ngay sau `memory_consolidate`, không có cron riêng, vì
  cả hai đọc cùng một tập ghi chú. Kết quả là một **đề xuất** mang cả lô trang kèm nội dung
  cũ để hoàn tác một bước; agent `autonomous` tự áp dụng. Biên dịch hỏng không làm hỏng lượt
  dọn bộ nhớ đã chạy xong trước đó.
- **Lint và hai bảng theo dõi.** Kho xuống cấp lặng lẽ: một trang mất nguồn cuối cùng, một
  liên kết trỏ tới trang chưa ai viết, một trang ngừng được cập nhật. Lint đọc cả kho một
  lượt và báo bốn loại: `unsourced`, `dangling`, `review`, `stale` (quá 90 ngày, hoặc không
  có ngày cập nhật — coi việc thiếu bằng chứng là còn mới là cách một kho bắt đầu nói dối).
  Không xoá gì: một liên kết treo thường là trang *nên có*, tức là việc cần làm cho lần
  biên dịch sau. Hai tệp `wiki/reports/open-questions.md` và `stale.md` được viết lại toàn
  bộ mỗi lần, vì bảng mà cộng dồn sẽ báo mãi những lỗi đã sửa từ mấy tháng trước.
- **Ba công cụ cho agent**: `wiki_get`, `wiki_search`, `wiki_apply`.
- **Tab Wiki trong màn hình quản lý** và các endpoint
  `GET/PUT/DELETE /api/agents/{id}/memory/wiki…`: xem kho theo nhóm, tìm, mở một trang, sửa,
  xoá, xem báo cáo lint, và chạy biên dịch ngay mà không phải đợi job ban đêm.
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
- **Kết quả công cụ quá dài được rút gọn thông minh thay vì cắt cụt.** JSON rút theo cấu
  trúc: mọi key top-level còn nguyên, mảng mất đuôi, chuỗi dài mất khúc giữa, và chuỗi trả
  về vẫn parse được. Con số, boolean và null không bao giờ bị viết lại — số liệu sổ sách và
  sức khoẻ đi qua đường này. Văn bản thường thì giữ nguyên văn 40% đầu và 20% cuối, khúc
  giữa nhờ chính tuyến của agent tóm tắt, kèm nhãn nói rõ đoạn nào là tóm tắt. Tóm tắt lỗi,
  chậm hay rỗng đều rơi về cắt thường; công cụ luôn trả lời.
- **Provider `ollama`** (OpenAI-compatible, `OLLAMA_BASE_URL`, mặc định
  `http://127.0.0.1:11434/v1`). Không cần khoá nên luôn được dựng; máy không chạy ollama thì
  tuyến rơi xuống tuyến kế. Trang Kết nối hiện địa chỉ đang dò, đủ để phân biệt "chưa chạy"
  với "sai host".
- **Thẻ lượt chạy nói rõ model đã đọc bản rút gọn** — nhãn ghi kiểu rút gọn và độ dài gốc, để
  một câu trả lời ngắn dựng trên nguồn đã bị tỉa không bị đọc nhầm thành bức tranh đầy đủ.
- **Công cụ `ask_user`: agent hỏi lại thay vì đoán.** Gặp chỗ không thể tự biết — hạn nào,
  tài khoản nào, có làm tiếp không — agent dừng lượt và hỏi một câu, kèm danh sách lựa chọn
  nếu có. Khác một lần xin phép công cụ ở ba điểm, nên đừng đọc nó như xin phép: agent đặt
  `autonomous: true` vẫn dừng, vì câu hỏi tồn tại đúng để không tự quyết; câu hỏi đóng bằng
  đường riêng, `/approve` và `/deny` bị từ chối trên nó; và hết hạn chờ không phải là từ
  chối — agent nhận giá trị `default` rồi đi tiếp, im lặng được hiểu là "cứ theo mặc định".
  Mỗi cuộc trò chuyện chỉ mở một câu hỏi. Trả lời ở web bằng thẻ câu hỏi, hoặc ở Telegram
  bằng chính tin nhắn kế tiếp — gõ số để chọn, gõ chữ thì được nhận nguyên văn.
- **Dòng thời gian lượt chạy có trạng thái chờ riêng.** Chỗ dừng vì câu hỏi trước đây hiện
  ra như không có gì, đọc thành một agent suy nghĩ hàng giờ. Nay nó là một bước riêng mang
  nội dung câu hỏi, tiêu đề thẻ ghi "Đang chờ bạn trả lời" và tắt hiệu ứng chạy — việc chỉ
  nhúc nhích khi có người gõ, nên không hứa hẹn tiến triển nào khác.
- **Công cụ `pdf_read`.** Trang chữ được đọc thẳng thành text; trang scan đi qua tuyến vision
  như ảnh, mỗi trang một lượt gọi, nên đọc bản scan dài thì tốn. Mặc định 50 trang, `pages`
  chọn một khoảng (`'1-5'`, `'3'`). Máy không có tuyến vision vẫn dựng công cụ: trang chữ đọc
  bình thường, trang scan báo không đọc được thay vì làm hỏng cả lượt.

### Thay đổi

- `web_search` không còn nằm trong nhóm công cụ tuỳ chọn: nó luôn được dựng, nên một agent khai
  `web_search` trong `tools:` không còn im lặng mất công cụ.
- **`docs/tools.md` nói rõ hệ quả của việc `shell_run` lọc biến môi trường**: script chạy được
  ở terminal của bạn vẫn có thể hỏng khi job chạy, vì mọi biến ngoài danh sách cho phép đều
  biến mất. Script cần một giá trị không phải bí mật thì tự đọc từ tệp, đừng trông vào biến
  môi trường — nới danh sách cho phép là trao khoá API cho mọi lệnh do model viết. Hành vi lọc
  không đổi; nay đã có test neo lại.

### Sửa

- **Kết quả công cụ bị cắt không còn vượt trần `tool_output_chars`.** Dòng nhãn "đã cắt bớt"
  trước đây được cộng thêm vào sau khi đã cắt đủ trần, nên bản trả về luôn dài hơn trần vài
  chục ký tự. Nay nhãn được trả bằng chính ngân sách đó. Test cũ đo bằng biên `+ 40` nên
  không thấy; nay có một test quét nhiều trần và nhiều dạng dữ liệu để neo đúng bất biến này.

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
