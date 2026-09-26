# Thiết kế

**Phiên bản**: 0.8.0 · **Cập nhật**: 2026-09-26

## Mục tiêu

Một agent đa năng duy nhất mà một người dùng hằng ngày qua web UI: chat, cho nó dùng tool,
duyệt những tool rủi ro, xem nó tốn bao nhiêu. Mọi thứ khác đều phụ thuộc vào vòng lặp đó.

Từ 0.2.0, cùng vòng lặp đó có thể được khởi tạo nhiều lần thành các **agent có tên** (một HLV
sức khoẻ, một trợ lý cá nhân) giữ persona, trí nhớ, workspace và lịch riêng, và UI hiển thị
trực tiếp mọi run của mọi agent. Bản thân vòng lặp không đổi; profile và scheduler nằm
quanh nó.

## Những gì cố ý không lặp lại từ my-crew

| my-crew | Vấn đề đã đo được | Ở đây |
|---|---|---|
| Đội agent theo vai, router, đồ thị task DAG | Phần lớn giá trị đến từ một agent giỏi; code điều phối chiếm phần lớn codebase và danh sách bug | Một vòng lặp agent; profile chỉ thay đổi đầu vào của nó. Không có agent sống lâu nói chuyện với nhau: giao việc là một tool call, sâu một cấp, và cuộc trò chuyện con chạy một lượt rồi trả câu trả lời |
| Profile + YAML công ty + cài đặt theo từng agent | Bề mặt cấu hình quá lớn để giữ được test; secret có thể lọt vào YAML | Biến môi trường + `config.yaml` theo whitelist; `agent.yaml` có bộ key cố định và không có secret |
| Web UI thêm muộn, nhiều trang | UI chạy sau tính năng; test là một thế giới riêng | UI là bề mặt chính; ba tầng test dùng chung một hợp đồng event |
| Tệp phình quá 1000 dòng | Khó review, khó cho công cụ LLM | Ngân sách 200 dòng được một test ép buộc |
| Theo dõi chi phí lạc quan | Giá chưa biết bị âm thầm tính là 0 | `cost_usd=None` được tính vào `unknown_cost_calls` và hiển thị trên UI |
| Chuỗi tiếng Việt rải rác | Định danh trôi dạt, khó bản địa hoá | Chỉ `texts.py` và `i18n/vi.ts` |

## Hình dạng runtime

```
browser ──/api/conversations/{id}/messages (SSE)──┐
Telegram poller ──────────────────────────────────┤
any platform ──POST /api/inbound (JSON, sync)─────┴─▶ Inbound ──▶ agent loop (one turn on one conversation)
                                                        │           │  provider chain (ordered routes, fallback before first item)
                                                        │           │  tool registry (workspace, web, memory, shell, delegate)
                                                        │           │  skills + persona/memory + crew roster (system prompt)
                                                        │           └─ store (SQLite: conversations, messages, approvals, runs)
                                                        ├─ activity hub (live runs → SSE /api/activity/stream)
                                                        └─ Scheduler    (cron/every jobs per agent, 20 s tick)
```

- **Một cửa cho mọi nền tảng.** Cổng inbound tìm agent, mở hoặc dùng lại cuộc trò chuyện
  (một cuộc mỗi agent mỗi kênh mỗi ngày), canh giữ nó khi có approval đang chờ, chạy lượt
  dưới sự theo dõi của activity và ghi lại nguồn của run. Web đọc luồng event; Telegram và
  `POST /api/inbound` nhận `TurnReply` đã gom (text, status, steps). Không nền tảng nào đặc
  biệt, nên một thay đổi ở backend tới được tất cả và một tính năng được test bằng cách post
  vào API.

- **Trạng thái bền là nhật ký message.** Một lượt tiếp tục từ message assistant cuối cùng đã lưu:
  các tool call chưa xong được giải quyết trước, nên crash giữa lượt là khôi phục được.
  SQLite mở ở chế độ WAL với `synchronous=NORMAL` (`store/connection.py`): mỗi commit chỉ
  nối vào log thay vì ép tệp chính xuống đĩa, nên hàng chục lần ghi nhỏ của một lượt rẻ;
  mất điện có thể mất vài commit cuối nhưng không hỏng tệp, crash tiến trình không mất gì.
  Ghi rồi đọc lại dùng `RETURNING` trong một câu lệnh. Đọc tệp live từ ngoài thì mở bằng
  `mode=ro` (không phải `immutable=1`, vì bản đó không thấy phần còn nằm trong log WAL).
- **Duyệt là hạng nhất.** Một tool `requires_approval` tạm dừng lượt với một event `approval_required`
  và một `Approval` được lưu; UI hiện một thanh, endpoint quyết định tiếp tục đúng lượt đó.
  Cuộc trò chuyện đánh dấu `autonomous` bỏ qua chỗ dừng. Các từ chối cứng — path thoát khỏi
  workspace, đích mạng private/loopback — không duyệt được.
- **Approval không ai trả lời thì đóng lại an toàn.** Mỗi `Approval` mang một hạn chót
  (`approval_ttl_seconds`, mặc định 600); tick của scheduler quét những cái quá hạn,
  đóng chúng là `expired`, tiếp tục lượt với tool bị từ chối
  và gửi câu trả lời như mọi lượt khác, nên một yêu cầu không ai thấy không bao giờ treo
  cuộc trò chuyện. Endpoint quyết định cũng nhận `always`: duyệt kèm nó thì tool được thêm vào
  danh sách `auto_approve` của cuộc trò chuyện và các lần gọi tool đó về sau chạy không cần hỏi,
  cho tới khi chip trên header thu hồi. Danh sách hỏi của shell vẫn tạm dừng một `shell_run`
  đã được cho phép luôn. Các yêu cầu đã quyết vẫn đọc được ở `GET /api/approvals`.
- **Fallback nhìn thấy được.** Mỗi tuyến bỏ cuộc đều được log, phát thành event `route_fallback`
  và ghi thành step `fallback` trên run, nên một model cứ lỗi mãi sẽ hiện trên timeline
  thay vì âm thầm tốn thêm ở tuyến kế tiếp. Step `fallback` mang thời gian của lần thử hỏng
  đó; step `model` mà request đã mở dời ra sau nó để đo tuyến kế tiếp, nên run hồi phục không
  để lại step model nào mở, còn khi mọi tuyến đều hỏng thì run chỉ còn các step `fallback`.
- **Model đang nghĩ cũng là đang chạy.** Model có suy nghĩ có thể im lặng khá lâu trước chữ
  đầu tiên, nên luồng stream đọc `delta.reasoning` và phát event `thinking` một lần mỗi lần
  gọi model. Web hiện "Agent đang suy nghĩ…" còn step `model` trên run tính cả quãng im lặng
  đó. Nội dung suy nghĩ không hiện và không lưu, chỉ lưu số `reasoning_tokens`.
- **Chỉ fallback trước khi có output.** Chuỗi chỉ thử tuyến kế tiếp nếu tuyến trước lỗi trước
  khi trả ra bất cứ gì; lỗi giữa stream được đưa lên bề mặt, không bao giờ bị che bằng một lần thử lại âm thầm.
- **Chi phí trung thực.** Mỗi message assistant lưu `cost_usd` hoặc `None`. Cuộc trò chuyện giữ
  `spent_usd` và `unknown_cost_calls`; `cost_cap_usd` dừng trước lần gọi model kế tiếp
  (0 = không giới hạn).
- **Provider echo là một tính năng sản phẩm.** `MY_AGENT_ROUTES=fake:echo` chạy cả stack mà không cần
  key; `/tool <name> {json}` điều khiển tool thật qua đường duyệt thật. Đó cũng là thứ
  live smoke và test trình duyệt dựa vào.
- **Output của tool bị cắt** trước khi vào ngữ cảnh: mặc định 8000 ký tự, theo từng
  agent qua `tool_output_chars`.

## Profile agent

`MY_AGENT_HOME/agents/<id>/agent.yaml` mô tả một agent: bộ key cố định, không có secret,
mọi giá trị chưa đặt kế thừa từ cài đặt toàn cục. Agent `default` luôn tồn tại và chính là
cài đặt cấp cao nhất, nên một home mới không cần profile. Tệp persona và trí nhớ là Markdown
trong thư mục agent, được đọc vào system prompt mỗi lượt. Tham chiếu key và bố cục thư mục:
[agents.md](agents.md); tệp trí nhớ và tool: [memory.md](memory.md); bộ tool và giới hạn
của nó: [tools.md](tools.md).

**Chế độ work.** `mode: work` đổi các mặc định sang những gì một job lập trình cần — trần chi
tiêu cao hơn, nhiều step hơn, và bật autonomous — vì người yêu cầu refactor không ngồi đó để
duyệt từng lần ghi tệp. Đó là một mặc định khác, không phải một luật khác: các tool luôn hỏi
vẫn hỏi, và trần vẫn dừng lượt. Agent work cũng nhận `delegate` trừ khi danh sách cho phép
`tools` của nó bỏ tool này ra, nên một chuyên gia vẫn là chuyên gia thay vì âm thầm lập một
đội riêng.

**Master.** Agent `default` là agent mà người dùng nói chuyện. Nó mang `delegate` và, trừ khi
`MY_AGENT_HOME/agent.yaml` tuỳ chọn của nó nêu một danh sách `delegates`, có thể gọi tới mọi
agent khác trong home; system prompt của nó liệt kê đội đó mỗi lượt. Điều này giữ sản phẩm là
"một agent giỏi, tự chủ" trong khi vẫn cho nó bố trí người cho một job: người dùng không chọn
agent, master chọn — trên web cũng như trên Telegram. Đội giữ lịch của mình và đơn giản là
cũng có tên trong danh sách. Khi một lượt của master chỉ là một lần `delegate` và agent con làm
xong, câu trả lời của con được chuyển nguyên văn cho người dùng (`agent/delegate_relay.py`) thay
vì tốn thêm một lần gọi model để kể lại; agent con, từ lần gọi thứ 25, được nhắc kết luận và
không còn tool (`agent/child_wrap_up.py`) để không bị trần bước cắt giữa chừng. Chi tiết:
[agents.md](agents.md#agent-master).

**Mẫu.** Ba profile đi kèm ứng dụng — một lập trình viên, một cố vấn và một nghiên cứu viên — cài bằng
`agent add <id>` hoặc `POST /api/agents/install` (thứ mà tab đội gọi), kéo theo các agent
đồng cấp mà vai đó giao việc cho và một bộ skill dùng chung. Mọi manifest đều chạy được ngay
như khi cài (workspace chung của home, các tuyến toàn cục); `--workspace` ghim một vai vào
một repository. Cài qua API thì gia nhập đội đang chạy ngay lập tức, còn lịch thì khởi động
lúc boot. Chúng là điểm xuất phát để sửa, không phải framework: mỗi cái là một
`agent.yaml` với cùng bộ key cố định, nên không có gì phải học ngoài định dạng profile.

**Kit.** Người đã dùng Claude Code hoặc opencode có sẵn một `.claude/` hoặc
`.opencode/` đầy subagent, command, skill và hook. Thay vì một công cụ di trú,
đội đọc nguyên các thư mục đó: `.agents/`, `.claude/` và
`.opencode/` dưới home và dưới thư mục agent. Agent Markdown thành thành viên đội,
tệp command thành slash command, hook chạy với cùng hợp đồng JSON và cùng tên tool qua một
bảng alias. Profile yaml giữ tiếng nói cuối với bất kỳ id nào cả hai cùng định nghĩa. Kit nằm
trong workspace mà agent làm việc thì cố ý không được đọc: repository đó là nguồn dữ liệu cho
đội, và `.claude/` của nó thuộc về người phát triển nó. Chi tiết:
[agents.md](agents.md#kit-agents-claude-opencode).

## Trí nhớ

Trí nhớ là Markdown trên đĩa ở hai phạm vi: những gì đội biết về **người dùng**
(`users/owner/`, mọi agent đều đọc) và những gì **một agent** biết về công việc của chính nó
(`MEMORY.md` cùng ghi chú theo ngày trong thư mục của nó). Tham chiếu đầy đủ: [memory.md](memory.md).

Hai phạm vi thay vì một, vì hai bên có người đọc khác nhau. Một sự thật về người dùng — họ
thích được trả lời thế nào, họ đang làm gì — mà phải học lại ở từng agent là sai: nói với HLV
một điều mà trợ lý không biết chính là lỗi mà cách này sửa. Ghi chú công việc thì ngược lại:
số đo của HLV sẽ là nhiễu trong prompt của trợ lý, và ghi chú của mọi agent dồn vào một tệp
sẽ vỡ trần của section.

Ghi khi người dùng có mặt thì vào ngay; ghi từ một job không ai trông thành **đề xuất** trong
`memory_proposals`. Ranh giới là ai có thể phản đối, không phải lần ghi trông rủi ro tới đâu:
một job theo lịch ghi đè profile của người dùng bằng một phỏng đoán sai thì không ai bắt được.
Cùng lý lẽ đó khiến **hợp nhất** — lần ghi lại `MEMORY.md` theo lịch từ các ghi chú gần đây —
là một đề xuất giữ lại văn bản nó thay thế, nên lùi một bước luôn khả thi.

## Activity hub và run

Mọi lượt model — chat, tiếp tục sau duyệt, prompt theo lịch, command theo lịch — là một **run**.
Run ghi agent của nó, nguồn (`chat`, `job:<id>`),
cuộc trò chuyện, trạng thái, các step (lần gọi model kèm chi phí, tool call kèm kết quả và thời lượng), chi tiêu
và một tóm tắt. Run đang chạy được giữ trong bộ nhớ và phát dạng SSE trên `/api/activity/stream`
(`snapshot` khi kết nối, rồi các frame `run` và `event`); run đã xong được đọc từ SQLite.
Run còn đánh dấu đang chạy khi server khởi động sẽ bị đóng là `failed` với tóm tắt
`interrupted`. Run được ghi và phát ở ranh giới step: token stream (`text_delta`,
`thinking`) chỉ cộng dồn vào step đang dựng trong bộ nhớ, không ghi SQLite và không lên
luồng activity (rail không hiện từng chữ). Mỗi watcher có hàng đợi 256 frame; một tab
ngừng đọc bị cắt và trình duyệt kết nối lại với `snapshot` mới, thay vì giữ mọi event
của mọi run trong bộ nhớ server. `/api/stats` giữ câu trả lời cuối cùng theo số lần ghi
của store và chỉ tính lại khi có gì đó được ghi.

## Scheduler

`scheduler/` biến mỗi lịch được bật thành một job `<agent_id>/<schedule_id>`. Một lịch có
đúng một trong `cron` (năm trường, theo múi giờ của người dùng) hoặc `every` (`30m`, `2h`, `1d`) và đúng
một trong `prompt` hoặc `command`. **Job prompt** mở một cuộc trò chuyện autonomous mới cho agent
và chạy một lượt; **job command** chạy chuỗi lệnh bằng `shell_run` trong workspace của agent và
chỉ ghi step đó; **job consolidate**, thêm bởi một cron `memory_consolidate`, ghi lại
`MEMORY.md` của agent bằng một lần gọi model và không mở cuộc trò chuyện nào, nên không gửi gì cả. Tick là 20 s; `POST /api/jobs/{id}/run` khởi động một job ngay lập tức và
trả 202. Đồng hồ của lịch là múi giờ của người dùng: key `timezone` trong `config.yaml` (hoặc
`MY_AGENT_TIMEZONE`), một tên IANA như `Asia/Ho_Chi_Minh`, và múi giờ của máy khi chưa đặt.
Mọi dấu thời gian trong database vẫn là UTC và được đổi sang ngày của người dùng cho
prompt, `/status`, thống kê activity và sổ cái sử dụng.
`PATCH /api/jobs/{id}/state` tạm dừng hoặc tiếp tục một lịch lúc chạy; ghi đè này được lưu
trong database, sống qua restart và chỉ áp dụng với lịch
mà profile bật — lịch tắt trong yaml được báo là `enabled: false, paused: false` và
không bật được từ UI. `GET /api/jobs/{id}/runs` liệt kê các run đã qua của job đó.

## Kênh

`channels/` cho người dùng nói chuyện với đội trên thứ khác ngoài web UI. Hiện nay
đó là Telegram: `agent.yaml` của master có `telegram: {token_env, chat_id}` được một
bot lúc khởi động khi biến môi trường được nêu tên đã đặt, dựng lại tại chỗ
khi khối trong profile hoặc token của nó đổi từ web UI. Chat đó là
cuộc trò chuyện của master, nên điện thoại và web UI là cùng một cơ chế: một agent đứng ở
cửa, giao việc phía sau. Lượt đi qua cổng inbound như mọi nền tảng khác, với
nguồn `telegram`, câu trả lời gửi về dạng text và `sendPhoto`, slash command được trả lời
không cần gọi model, và scheduler đẩy câu trả lời của job prompt của bất kỳ agent nào
tới chat dưới tiền tố `[Name]`, với `MEDIA:` của nó đọc từ workspace của agent đó.
Hành vi đầy đủ, lệnh, offset và secret: [channels.md](channels.md).

## Tool shell và tệp của agent

`shell_run` thực thi một lệnh trong workspace của agent với môi trường tối thiểu
(PATH, HOME, LANG, TERM, TMPDIR, USER, SHELL) và timeout có giới hạn; nó luôn cần duyệt
trừ khi cuộc trò chuyện hoặc agent là autonomous. `GET /api/agents/{id}/files?path=` chỉ phục vụ tệp
từ bên trong workspace đó, và đó là cách một dòng `MEDIA: charts/sleep.png` của assistant được
UI hiển thị inline.

Ảnh đi chiều ngược lại qua `image_read`: model chat trên các tuyến của agent được
chọn vì giá và văn bản, nên tool gửi tệp xuống một chuỗi `vision_routes` riêng
kèm một câu hỏi và trả câu trả lời dạng text. Agent nào cũng có nó, master đọc một lần
để định tuyến bức ảnh và chuyên gia đọc lại để lấy chi tiết mình cần, và lần gọi
được tính vào cuộc trò chuyện như một completion. [tools.md](tools.md#ảnh).

## Web UI

React + Vite, không có thư viện state. Hai reducer thuần ghim hợp đồng server từ cả hai phía:
một trên luồng event của một cuộc trò chuyện, một trên luồng activity của rail. Mỗi
vùng (một cuộc trò chuyện, danh sách, subscription activity, agent cùng job cùng stats) do
một hook sở hữu, và một run kết thúc là tín hiệu duy nhất làm mới các vùng còn lại.
Mọi chuỗi đều lấy từ một tệp chuỗi tiếng Việt.

Bundle tách thành ba phần (`react`, `vendor`, mã ứng dụng), tên tệp mang hash nội dung;
server phục vụ `/assets/*` với `Cache-Control: immutable` và nén gzip mọi phản hồi trên
1 KB trừ luồng SSE, nên một bản phát hành chỉ đổi mã ứng dụng để trình duyệt giữ nguyên
hai phần kia, còn `index.html` luôn được hỏi lại.

Chỉ có một chat, với master: danh sách cuộc trò chuyện chứa các cuộc trò chuyện của master
và cuộc mới luôn được mở cho nó. Màn hình chào nói với tư cách master và nêu tên
đội; một chip trên header (`Đội: N`) mở tab đội trong rail, liệt kê mọi agent
(master trước, kèm huy hiệu mode, live, lịch và Telegram) và cài một mẫu đi kèm
bằng một cú bấm. Cuộc trò chuyện của agent được giao việc không nằm trong danh sách, nhưng mở được từ thẻ run
hoặc mục **Cần bạn xử lý**.

Màn hình chia theo việc thuộc về ai. Những gì cuộc trò chuyện bạn đang ở trong đó đang làm nằm
trong khung chat: một view activity của cuộc trò chuyện hiện các run của chính cuộc đó, từng step
kèm tham số và output của tool. Trên màn hình rộng, nó là một cột neo bên phải luồng
tin, luôn mở và giữ chỗ ngay cả trước run đầu tiên, nên chat không nhảy
khi việc bắt đầu. Hẹp hơn, nó gập thành một dải một dòng giữa luồng tin và ô soạn;
một trong hai được render, không bao giờ cả hai bị CSS ẩn. Những gì thuộc về cả
đội nằm trên một màn hình quản lý riêng (`#/manage/<section>`) thay vì trong một rail cạnh
luồng tin — để chúng cạnh nhau khiến việc của đội và việc của cuộc trò chuyện trông như
cùng một thứ. Nav của nó gom các mục thành theo dõi (activity, duyệt, chi phí), đội
(đội, tool, job, trí nhớ) và hệ thống (kết nối, cài đặt); trên điện thoại các nhóm dàn phẳng
thành một hàng cuộn ngang. Các mục của nó: activity (run đang chạy, và một mục **Cần bạn xử lý** cho các run đang chờ
duyệt, đã lỗi hoặc bị dừng), duyệt (các yêu cầu đã quyết kèm kết quả — đã duyệt,
bị từ chối, hết hạn), đội, tool, job (run kế/run trước, nút chạy ngay, công tắc tạm dừng/tiếp tục và
lịch sử run của job khi cần), trí nhớ, chi phí theo agent, model và ngày — trong đó bảy ngày
gần nhất và bảng theo model được đọc thẳng từ nhật ký message với số token của nó, nên
con số là thứ thực sự được tính tiền chứ không phải ước lượng — kết nối, và cài đặt.

Một run có thể mở riêng ở `#/manage/activity/<run_id>`: lấy theo id, nên link tới một run
mà danh sách chưa từng tải vẫn hoạt động, và tải lại trang vẫn ở đó. Phía trên mỗi timeline, một
dòng nói run đang làm gì lúc này — một câu và một số đếm (`3/7 bước`) thay vì
phần trăm, vì không có gì trong dữ liệu run nói còn bao nhiêu step nữa, nên
phần trăm sẽ là bịa. Run đã kết thúc thì thay vào đó nói nó kết thúc ra sao; một run đã xong
mà bảo đang suy nghĩ thì đọc như bị treo.

Header chat là tiêu đề và ba pill: chi tiêu so với trần, tuỳ chọn, và số thành viên
đội. Pill mang dòng tóm tắt và mở một thẻ với chi tiết: thẻ chi tiêu
có thanh, phần còn lại và phần đã giao việc; thẻ tuỳ chọn giữ công tắc autonomous,
các skill tuỳ chọn dạng công tắc và các tool được cho phép luôn, mỗi cái kèm link thu hồi.
Thẻ đóng khi Escape (bắt trước phím tắt Escape của chính app, focus trả về pill)
hoặc bấm ra ngoài; bấm bên trong giữ thẻ mở. Thẻ ở mọi nơi dùng chung một từ vựng —
một hàng là icon, nhãn, gợi ý ⓘ, giá trị căn phải bằng chữ số đều (tabular; chỉ id và đường dẫn dạng `code` mới giữ font mono), một
thanh mỏng tuỳ chọn và một dòng phụ có màu — nên cột activity mở bằng một thẻ tóm tắt
(chi tiêu, step, run được giao việc, model) và cài đặt là một bộ thẻ tóm tắt chỉ đọc
dẫn tới mục nơi một thứ được thay đổi thay vì lặp lại danh sách của nó.

Thanh duyệt hiện hạn chót của yêu cầu đang chờ và một nút "luôn cho phép" cạnh
duyệt/từ chối. Màn chat và màn quản lý mỗi màn có một error boundary, nên một crash khi
render hiện thẻ lỗi có nút tải lại thay vì trang trắng. Bên trong chat, thread và cột activity
có boundary riêng, nên một phần vỡ không kéo sập phần còn lại; màn quản lý có một boundary cho
mỗi trang, nên một mục vỡ vẫn để lại nav, và chọn trang khác là thoát khỏi lỗi. (Ý tưởng cho view run mượn từ view session
của openhuman — không mượn code.)

Về thị giác, mọi giá trị đi qua một bộ token trong `web/src/styles/tokens.css`: thang chữ,
khoảng cách, bo góc, bóng, bề mặt và các màu trạng thái, mỗi màu có bản sáng và tối. Chế độ
tối theo hệ điều hành, không có công tắc riêng. Font Inter đóng gói kèm bundle, gồm cả bộ
ký tự tiếng Việt, không tải từ CDN. Icon là một bộ nét SVG vẽ tay trong
`components/ui/icon.tsx` thay cho emoji, vì emoji mỗi nền tảng vẽ một kiểu và theme không
đổi được màu của nó. Mỗi agent có một avatar là chữ cái đầu trên nền màu riêng, băm từ id
nên ở đâu cũng cùng một màu. Logo trên sidebar cũng là favicon và icon khi cài app:
`npm run icons` vẽ các PNG từ `web/public/favicon.svg`. Thẻ **Cần bạn xử lý** xám khi
trống và chỉ chuyển màu cảnh báo khi có việc chờ; trong lịch sử duyệt, yêu cầu hết hạn mang
nhãn xám, còn màu cảnh báo giữ cho yêu cầu bị từ chối và yêu cầu đang chờ. Nền tô của nút chính
và badge (`--accent-fill`) giữ màu xanh thương hiệu ở cả hai chế độ, vì bản xanh sáng hơn của
chế độ tối chỉ dành cho chữ và viền: chữ trắng trên nó không đạt 4.5:1.

Trên điện thoại, cuộc trò chuyện chiếm cả màn hình. Danh sách trượt vào từ nút menu, đóng
khi bấm Escape, chạm ra ngoài hoặc chọn một cuộc, và focus trả về nút đã mở nó. Khi mở,
drawer là modal: phần chat bên dưới `inert`, và Escape chỉ đóng drawer chứ không thu dải
activity nằm dưới. ⌘K mở drawer ngay ở ô tìm kiếm, vì ô đó nằm trong drawer đang đóng. Chấm
báo có việc chờ trên nút menu cũng nằm trong tên nút, để trình đọc màn hình nghe được. Nav của màn
quản lý thành một hàng pill, tự cuộn tới mục đang mở.

## Điểm mở rộng

- Provider (`llm/`): thứ stream ra một câu trả lời, nối vào nơi server dựng provider cho mỗi
  agent.
- Tool (`tools/`): một spec cho model cộng một hàm chạy; đánh dấu cần duyệt khi
  nó thay đổi trạng thái, và nối vào nơi server dựng bộ tool cho mỗi agent.
- Skill: một tệp Markdown có `name` (và tuỳ chọn `always`, `description`) trong `MY_AGENT_HOME/skills`
  hoặc trong `skills_dirs` của một agent.
- Agent: một thư mục dưới `MY_AGENT_HOME/agents/` với `agent.yaml` và các tệp persona.
- Kênh (`channels/`): start, stop và deliver, dựng từ khối profile của master; giữ
  secret dưới dạng tên biến môi trường trong profile.
- Credential (`server/`): một biến môi trường đã biết là một hàng trong catalogue (nhóm, secret hay URL, kiểm tra
  trực tiếp tuỳ chọn); bất cứ thứ gì khác mà một skill đọc vẫn đặt được từ Kết nối dưới mục "Biến khác".
  Thay đổi được áp dụng ngay: đội được dựng lại từ môi trường mới và một thay đổi gây hỏng
  (ví dụ xoá key duy nhất mà một tuyến cần) bị từ chối trước khi ghi bất cứ gì.
  Một hàng rào cục bộ phủ mọi path: `Host` phải là IP, `localhost` hoặc tên trong
  `MY_AGENT_ALLOWED_HOSTS`, và `Origin` phải khớp đúng host:port; 403 nêu tên host.
