# Thiết kế

**Phiên bản**: 0.9.2 · **Cập nhật**: 2026-09-28

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
                                                        ├─ QueueDrain   (what waited while busy → a turn of its own)
                                                        └─ Scheduler    (cron/every jobs per agent, 20 s tick)
```

- **Một cửa cho mọi nền tảng.** Cổng inbound tìm agent, mở hoặc dùng lại cuộc trò chuyện
  (một cuộc mỗi agent mỗi kênh mỗi ngày), giữ nó mỗi lúc một lượt, chạy lượt
  dưới sự theo dõi của activity và ghi lại nguồn của run. Web đọc luồng event; Telegram và
  `POST /api/inbound` nhận `TurnReply` đã gom (text, status, steps). Không nền tảng nào đặc
  biệt, nên một thay đổi ở backend tới được tất cả và một tính năng được test bằng cách post
  vào API.

- **Một lượt một lúc; tin đến sau thì chờ hoặc rẽ lượt.** Cổng inbound giữ cuộc trò chuyện từ lúc
  trao ra một lượt: một claim, thành run sống khi lượt được đọc lần đầu; claim không ai đọc hết hạn
  sau 15 s. Tin đến trong lúc đó không chạy song song và không bị từ chối: nó vào bảng
  `queued_messages` của cuộc trò chuyện (tối đa 20, tin thứ 21 nhận 429) và người gửi nhận một event
  `queued` (`item_id`, `kind`, `position`) thay cho lượt. Tin thường là `follow_up`: khi lượt đang
  chạy kết thúc, `QueueDrain` ghép mọi tin đang chờ theo thứ tự, cách nhau một dòng trống, thành một
  tin người dùng và chạy một lượt cho nó ở nền, với nguồn của tin đầu. Tin bắt đầu bằng
  `/steer <chữ>` hay một lệnh mà kit của agent định nghĩa là `steer`: lượt đang chạy lấy nó ở đầu
  vòng kế tiếp — sau kết quả của tool đang chạy, trước lần gọi model sau đó — thành một tin người
  dùng, hiện trên run là một step `steer`, và trả lời nó ngay trong lượt ấy. Steer phải chờ tool
  đang chạy xong, nên một `delegate` dài làm nó trễ; steer đến sau lần kiểm cuối của lượt thì ở lại
  hàng và được trả lời như tin thường. `/tmp/x` hay một lệnh không ai định nghĩa là tin thường;
  `/steer` không kèm chữ bị từ chối (422) cả khi rảnh lẫn khi bận, còn lúc rảnh `/steer X` chỉ là
  tin `X`. Cuộc trò chuyện đang chờ duyệt vẫn từ chối tin mới (409). Một quyết định hay câu trả lời
  giữ cuộc trò chuyện ngay lúc được đưa ra, trước khi lượt nó tiếp tục kịp chạy, nên tin gửi ngay
  sau đó chờ lượt ấy, còn quyết định thứ hai cho cùng yêu cầu nhận 409.
- **Hàng đợi bền và dừng được.** Chuyển tin từ hàng vào lịch sử là một transaction: dòng rời hàng và
  tin vào nhật ký trong cùng một commit, nên tin đã báo "đã xếp hàng" không bao giờ mất. Hàng sống
  qua restart: khởi động xong, server drain mọi cuộc trò chuyện còn tin, trừ cuộc đang chờ duyệt
  (lượt tiếp tục sau quyết định sẽ drain nó). Server chạy `--no-schedule` không tự bắt đầu việc gì,
  nên hàng còn lại nằm đó tới khi lượt kế của cuộc trò chuyện ấy xong. Lúc tắt, drain dừng trước mọi
  thứ khác nên không lượt mới nào bắt đầu giữa chừng. Xoá cuộc trò chuyện xoá luôn hàng của nó.
  `GET /api/conversations/{id}` liệt kê tin đang chờ trong `queued`, và
  `POST /api/conversations/{id}/stop` lấy hết hàng, trả lại chữ trong `cleared` và huỷ lượt nền mà
  hàng đang chạy (`cancelled`). Nó chỉ với tới lượt do chính hàng khởi chạy: lượt mà một tab đang
  đọc, lượt bot Telegram chạy cho tin vừa đến hay lượt của một job không phải của nó để dừng, và khi
  đó `cancelled` là `false`.

- **Trạng thái bền là nhật ký message.** Một lượt tiếp tục từ message assistant cuối cùng đã lưu:
  các tool call chưa xong được giải quyết trước, nên crash giữa lượt là khôi phục được. Tin mới
  của người thì khác: call nào lượt trước bỏ lại không có kết quả (tab đóng, server tắt giữa lúc
  tool chạy) được đóng trước khi tin được ghi, bằng quyết định đã biết của nó (từ chối, hết hạn,
  câu trả lời) hoặc bằng một kết quả nói nó bị ngắt và không rõ đã chạy hay chưa. Không call nào
  chạy lại mà không ai hỏi, và thứ tự tin vẫn hợp lệ với provider; call còn chờ duyệt thì để nguyên.
  SQLite mở ở chế độ WAL với `synchronous=NORMAL` (`store/connection.py`): mỗi commit chỉ
  nối vào log thay vì ép tệp chính xuống đĩa, nên hàng chục lần ghi nhỏ của một lượt rẻ;
  mất điện có thể mất vài commit cuối nhưng không hỏng tệp, crash tiến trình không mất gì.
  Ghi rồi đọc lại dùng `RETURNING` trong một câu lệnh. Đọc tệp live từ ngoài thì mở bằng
  `mode=ro` (không phải `immutable=1`, vì bản đó không thấy phần còn nằm trong log WAL).
- **Lời đã nói tìm lại được.** `store/search_index.py` dựng bảng FTS5 `messages_fts` và
  trigger giữ nó khớp `messages` (insert/delete, không update vì `messages` chỉ thêm) trong
  cùng transaction với `apply_schema`, nên một crash giữa chừng không để lại chỉ mục rỗng mà
  lần khởi động sau tưởng đã xong. Bộ gõ `unicode61 remove_diacritics 2` tự bỏ dấu khi so
  khớp nhưng không đụng tới `đ`; trigger và backfill tự thay `đ`/`Đ` bằng `d`/`D` trước khi
  đưa vào chỉ mục, để gõ "doc" vẫn khớp "đọc". `store/search.py` là nơi cả `conversation_search`
  (tool cho model, phạm vi theo agent) lẫn `GET /api/messages/search` (cho người, ở phần Web UI
  bên dưới) cùng đọc.
- **Duyệt là hạng nhất.** Một tool `requires_approval` tạm dừng lượt với một event `approval_required`
  và một `Approval` được lưu; UI hiện một thanh, endpoint quyết định tiếp tục đúng lượt đó.
  Cuộc trò chuyện đánh dấu `autonomous` bỏ qua chỗ dừng. Các từ chối cứng — path thoát khỏi
  workspace, đích mạng private/loopback — không duyệt được.
- **Approval không ai trả lời thì đóng lại an toàn.** Mỗi `Approval` mang một hạn chót
  (`approval_ttl_seconds`, mặc định 600; một lịch hay khối `telegram` đặt được hạn riêng, cuộc
  trò chuyện chúng mở giữ hạn đó và cuộc của agent con chép của cha); tick của scheduler quét những cái quá hạn,
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
  (0 = không giới hạn). Mọi lần gọi model nằm ngoài vòng lặp lượt — đặt tiêu đề, tóm tắt
  phiên, tóm tắt output tool dài, đọc ảnh, đọc trang PDF scan, cô đọng bộ nhớ, dựng wiki —
  đi qua `MeteredChain` và để lại một dòng trong bảng `side_calls` kèm mục đích của nó (chỉ số
  liệu, không bao giờ prompt). Sổ cái sử dụng (`/api/stats`: `days`, `models`, `purposes`) cộng
  hai bảng đó và không đọc run, nên không lần gọi nào bị đếm hai lần hay bị bỏ sót. Tool có gọi
  model (ảnh, PDF scan, bản tóm tắt được dùng) được tính vào run và cuộc trò chuyện như một
  completion; giá không rõ được đếm riêng, không bao giờ coi là 0. Lần gọi bị bỏ dở sau chunk
  đầu tiên vẫn được ghi, với giá không rõ. Bản tóm tắt hết giờ hay rỗng — tool rơi về cắt —
  chỉ nằm trong sổ cái: run và cuộc trò chuyện không có con số nào để cộng.
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
cũng có tên trong danh sách. Khi một lượt của master chỉ là một lần `delegate` và việc được giao
đi tới `done` (`tools/delegate_outcome.py`: dữ kiện của runtime trước, rồi dòng `Status:` con
khai), câu trả lời của con được chuyển nguyên văn cho người dùng (`agent/delegate_relay.py`) thay
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
Khi server khởi động, run còn đánh dấu đang chạy bị đóng là `error` với tóm tắt
`interrupted`. Run đang dừng chờ duyệt mà cuộc trò chuyện còn một yêu cầu chưa quyết thì
được giữ lại trong bộ nhớ, nên quyết định đến sau lần khởi động lại chạy tiếp chính run đó
thay vì mở run thứ hai; run chờ duyệt không còn yêu cầu nào để chờ (yêu cầu đã được quyết
khi không tiến trình nào giữ run) bị đóng như trên, và xoá một cuộc trò chuyện cũng đóng
ngay run đang chờ duyệt trong đó. Run được ghi và phát ở ranh giới step: token stream (`text_delta`,
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
một hook sở hữu, và một run kết thúc là tín hiệu làm mới các vùng còn lại. Cuộc trò chuyện
đang mở còn tải lại khi một run mà tab này không stream (Telegram, một job, một quyết định
trên máy khác) dừng chờ duyệt hay chạy tiếp sau quyết định, và một lần nữa khi luồng activity
nối lại, vì trong lúc luồng đứt một run có thể đã chạy rồi xong; lịch sử duyệt đọc lại khi
tập yêu cầu đang chờ đổi. Mọi chuỗi đều lấy từ một tệp chuỗi tiếng Việt.

Ô soạn không khoá khi agent đang bận: gõ và Enter vẫn gửi được, chỉ đổi chỗ tin đi tới. Tin
thường ra một chip "Đã xếp hàng, chạy sau lượt này" và không đụng luồng của lượt đang chạy —
web gửi nó bằng một POST riêng, chỉ đọc event `queued` từ đó, không chạm `AbortController` hay
reducer của lượt. Tin bắt đầu bằng `/steer` hay một lệnh kit ra chip "Sẽ chèn vào lượt đang
chạy"; khi server chèn nó (event `steer`), chip biến thành một tin người dùng ngay trong luồng,
và bước `steer` của run vẽ một hạt rỗng trên timeline để phân biệt "người nói" với "agent nói".
Stop là lối duy nhất lấy chữ về: nó gọi server trước (`POST …/stop`, hạn ba giây) để hàng có cơ
hội bị xoá đúng thứ tự trước khi web abort luồng ở máy, rồi trả chữ các chip vào đầu ô soạn theo
thứ tự chúng được gửi. Chip là các chip xác nhận, không có nút huỷ riêng — quản lý hàng đợi
không phải phạm vi tính năng này. Một lượt drain (Telegram, một job, một tab khác) mà web không
dừng được từ đây báo `cancelled: false`; lúc đó Stop chỉ xoá chip và nói "đang chạy ở nơi khác
nên chưa dừng được từ đây" thay vì im lặng, còn khi Stop chỉ xoá chip mà không có gì đang chạy
thì không thông báo gì, vì nói "chạy ở nơi khác" lúc đó là sai. Hàng sống qua F5 vì chip của
thread lấy từ `queued` trong chi tiết cuộc trò chuyện mỗi lần `loaded`, không giữ riêng ở máy.

Bundle tách thành ba phần (`react`, `vendor`, mã ứng dụng), tên tệp mang hash nội dung;
server phục vụ `/assets/*` với `Cache-Control: immutable` và nén gzip mọi phản hồi trên
1 KB trừ luồng SSE, nên một bản phát hành chỉ đổi mã ứng dụng để trình duyệt giữ nguyên
hai phần kia, còn `index.html` luôn được hỏi lại.

Chính `index.html` cho trang biết server đã chạy bản build khác: trang so script entry có
hash (`/assets/index-*.js`) nó đang chạy với entry mà `/` đang phục vụ. Không so số phiên
bản, vì server hay được khởi động lại từ một working tree chưa bump phiên bản, và bump một
mình không đổi gì mà một lần tải lại mang về. Một app đã cài trên điện thoại có thể mở nhiều
ngày, nên trang nhìn lại khi được focus hay hiện lại (tối đa mỗi 30 giây, không bao giờ khi
tab đang ẩn) và sau mỗi lần luồng activity nối lại, vì một luồng đứt là dáng của một lần
khởi động lại khi nhìn từ trình duyệt. Entry khác thì thanh "Có bản mới" mời tải lại; một
lần nhìn hỏng không nói gì, vì server đang tắt không phải bản mới, còn Vite dev server
không có entry hash nên không bao giờ hiện thanh. Cài đặt ghi phiên bản của trang cạnh
phiên bản của server, và chỉ lấy tên đó từ một lần nhìn thấy server phục vụ đúng entry của
trang — trang tải trước một lần khởi động lại không được mang tên của bản nó không chạy.

Chỉ có một chat, với master: danh sách cuộc trò chuyện chứa các cuộc trò chuyện của master
và cuộc mới luôn được mở cho nó. Màn hình chào nói với tư cách master và nêu tên
đội; một chip trên header (`Đội: N`) mở tab đội trong rail, liệt kê mọi agent
(master trước, kèm huy hiệu mode, live, lịch và Telegram) và cài một mẫu đi kèm
bằng một cú bấm. Cuộc trò chuyện của agent được giao việc không nằm trong danh sách, nhưng mở được từ thẻ run
hoặc mục **Cần bạn xử lý**. Danh sách xếp các cuộc dưới Hôm nay / Hôm qua / Cũ hơn theo lịch
của chính người xem, không theo ngày UTC, và mỗi dòng nói nó đổi cách đây bao lâu. Từ tám
cuộc trở lên, sidebar thêm một ô tìm lọc tiêu đề tại chỗ trên trang, có debounce, gọi
`GET /api/messages/search` để tìm cả trong nội dung tin nhắn — không chỉ cuộc trò chuyện của
agent đang mở mà của cả đội, mỗi kết quả mang huy hiệu tên agent khi khác agent hiện tại và
bấm vào mở đúng cuộc trò chuyện đó. Tiêu đề không khớp gì nhưng nội dung có kết quả thì
không hiện "không có kết quả", vì phần "Trong nội dung" bên dưới đã nói lên điều đó.

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
thành một hàng cuộn ngang. Các mục của nó: activity (một mục **Cần bạn xử lý** cho các run
đã lỗi hoặc bị dừng, mỗi run một nút "Đã xem"; các run đang chạy; rồi lịch sử run đã lưu,
lọc theo agent ngay ở server và theo trạng thái, nguồn trong trang, đọc lùi thêm bằng
"Xem thêm"), duyệt (các yêu cầu đang chờ, quyết ngay tại chỗ — cho phép, từ chối hay trả lời
câu hỏi — kèm đồng hồ đếm tới hạn chót; bên dưới là lịch sử các yêu cầu đã quyết kèm kết
quả — đã duyệt, bị từ chối, hết hạn, đã trả lời), đội, tool, job (lịch đọc thành chữ cạnh
cron gốc, run kế/run trước kèm giờ đồng hồ, run trước kết thúc ra sao, nút chạy ngay, công
tắc tạm dừng/tiếp tục, nút sửa lịch mở trình sửa agent, và lịch sử run của job khi cần),
trí nhớ, chi phí theo agent, model và ngày — trong đó bảy ngày gần nhất và bảng theo model
được đọc thẳng từ nhật ký message với số token của nó, nên con số là thứ thực sự được tính
tiền chứ không phải ước lượng — kết nối, và cài đặt. Yêu cầu chờ duyệt và run hỏng nằm ở hai
trang vì việc làm với chúng khác nhau: yêu cầu thì quyết, lỗi thì đọc rồi cất đi. Mỗi mục
trên nav đếm đúng thứ của nó (activity: run đang chạy và lỗi chưa xem; duyệt: yêu cầu đang
chờ; job: job có run gần nhất hỏng; trí nhớ: đề xuất chờ), và mỗi trang chỉ sang trang kia
khi bên đó có việc, nên "không có gì cần xử lý" chỉ hiện khi đúng cho cả màn quản lý. Số yêu
cầu đang chờ còn đứng trước tiêu đề tab và lên badge của app đã cài, và nút Quản lý mở thẳng
trang duyệt khi có yêu cầu chờ.

Một run có thể mở riêng ở `#/manage/activity/<run_id>`: lấy theo id, nên link tới một run
mà danh sách chưa từng tải vẫn hoạt động, và tải lại trang vẫn ở đó. Phía trên mỗi timeline, một
dòng nói run đang làm gì lúc này — một câu và một số đếm (`3/7 bước`) thay vì
phần trăm, vì không có gì trong dữ liệu run nói còn bao nhiêu step nữa, nên
phần trăm sẽ là bịa. Run đã kết thúc thì thay vào đó nói nó kết thúc ra sao; một run đã xong
mà bảo đang suy nghĩ thì đọc như bị treo.

Trang riêng của run còn cho tải cả lượt chạy về, dạng JSON (cho máy, và làm nguồn dựng case
eval) hoặc Markdown (để đọc, dán vào issue): bản ghi của run, đúng những tin nhắn của run đó
trong cuộc trò chuyện, mọi lời gọi tool kèm tham số và kết quả, và bản ghi cuộc trò chuyện của
từng agent con mà run đã giao việc. Run mới ghi lại cuộc trò chuyện đang đứng ở tin nào khi nó
bắt đầu (`after_seq`), nên tin của nó là các tin sau mốc đó và trước mốc của run kế tiếp trong
cùng cuộc; run tiếp tục sau khi duyệt vẫn là run ấy nên giữ mốc cũ. Run có từ trước khi có mốc
thì được cắt theo giờ bắt đầu và kết thúc, và bản xuất ghi `slice: "by_time"` để người đọc biết.
Hai lượt chạy chồng nhau trong một cuộc thì ranh giới giữa chúng chỉ gần đúng. Agent con chỉ đi
theo khi run của nó mang nguồn `delegate:<cuộc trò chuyện của run được xuất>`: mã lời gọi do
provider cấp có thể trùng giữa hai cuộc, và tra theo mã trần sẽ kéo bản ghi của agent khác vào.

Bản xuất khác thứ người đã thấy trên màn hình: nó có mọi thứ tool đã chạm tới (đầu ra shell,
trang web, tệp trong workspace, dữ liệu một agent con mang về). Server che khoá theo cách tốt
nhất có thể, không bảo đảm: giá trị của mọi biến môi trường trong tiến trình server có tên
chứa `KEY`, `TOKEN`, `SECRET`, `PASSWORD` hay `CREDENTIAL` và dài từ 8 ký tự, cùng những
chuỗi có dạng khoá quen thuộc (`sk-…`, `Bearer …`, JWT), đều thành `[đã che]`. Một bí mật đến
từ chỗ khác (người dùng gõ vào, một tệp hay trang web tool đọc được) thì không bị che. Vì vậy
đầu bản xuất và dưới hai link tải đều nhắc đọc lại trước khi dán ra ngoài. Kết quả tool dài quá
2 000 ký tự bị cắt và ghi rõ dài bao nhiêu, trừ khi gọi với `full=1`. Tệp đến dưới dạng
`attachment` với `Cache-Control: no-store`, qua cùng hàng rào Host/Origin như mọi đường khác.

Header chat là tiêu đề và ba pill: chi tiêu so với trần, tuỳ chọn, và số thành viên
đội. Pill mang dòng tóm tắt và mở một thẻ với chi tiết: thẻ chi tiêu
có thanh, phần còn lại, phần đã giao việc và chỗ nâng trần (thêm một bước, hoặc gõ trần mới
mà 0 là bỏ trần) — cũng chỗ đó nằm trong thông báo hết ngân sách, và ô soạn khoá tới khi
trần được nâng, vì server sẽ dừng lượt trước khi nó bắt đầu; thẻ tuỳ chọn giữ công tắc
autonomous, các skill tuỳ chọn dạng công tắc và các tool được cho phép luôn, mỗi cái kèm link
thu hồi, cùng nút xuất cả cuộc trò chuyện ra `<tiêu đề>.md`.
Thẻ đóng khi Escape (bắt trước phím tắt Escape của chính app, focus trả về pill)
hoặc bấm ra ngoài; bấm bên trong giữ thẻ mở. Thẻ ở mọi nơi dùng chung một từ vựng —
một hàng là icon, nhãn, gợi ý ⓘ, giá trị căn phải bằng chữ số đều (tabular; chỉ id và đường dẫn dạng `code` mới giữ font mono), một
thanh mỏng tuỳ chọn và một dòng phụ có màu — nên cột activity mở bằng một thẻ tóm tắt
(chi tiêu, step, run được giao việc, model) và cài đặt là một bộ thẻ tóm tắt chỉ đọc
dẫn tới mục nơi một thứ được thay đổi thay vì lặp lại danh sách của nó.

Thanh duyệt hiện hạn chót của yêu cầu đang chờ và một nút "luôn cho phép" cạnh
duyệt/từ chối; khi dòng tóm tắt tham số phải cắt bớt, "Xem đầy đủ" mở toàn bộ tham số
nguyên văn, ở thanh duyệt, ở thẻ tool và trong lịch sử duyệt. Màn chat và màn quản lý mỗi
màn có một error boundary, nên một crash khi
render hiện thẻ lỗi có nút tải lại thay vì trang trắng. Bên trong chat, thread và cột activity
có boundary riêng, nên một phần vỡ không kéo sập phần còn lại; màn quản lý có một boundary cho
mỗi trang, nên một mục vỡ vẫn để lại nav, và chọn trang khác là thoát khỏi lỗi. (Ý tưởng cho view run mượn từ view session
của openhuman — không mượn code.)

Vài thứ chỉ thuộc về người đang nhìn màn hình này, nên sống trong `localStorage` của trình
duyệt chứ không ở server: mỗi cuộc trò chuyện đã được xem tới đâu (chấm chưa đọc), bản nháp
chưa gửi của từng cuộc, các chip lọc của lịch sử run, những lỗi đã bấm "Đã xem", và dải
activity đang mở hay gập. Mọi lần đọc và ghi đi qua một helper lưu trữ cục bộ bọc try/catch,
vì trình duyệt có thể từ chối hẳn (cửa sổ riêng tư, chặn dữ liệu trang, đầy quota): khi đó
không gì được lưu và trang chạy tiếp trên bản trong bộ nhớ của nó cho tới lần tải lại. Lần
dùng đầu coi mọi cuộc có từ trước là đã đọc, dấu đã xem của các tab cùng một trình duyệt
được gộp chứ không ghi đè nhau, và bản nháp của một cuộc bị xoá đi cùng cuộc đó. Trình duyệt
khác, hay máy khác, bắt đầu lại từ đầu — đó là cái giá của việc không bắt server nhớ một
điều chỉ đúng với một màn hình.

Danh sách cuộc trò chuyện xếp theo `updated_at`, và chấm chưa đọc so với chính mốc đó, nên
mốc chỉ được đẩy khi cuộc trò chuyện thật sự đổi: một tin nhắn, một lượt, một lần người dùng
sửa nó. Việc ghi sổ chạy nền — bản tóm tắt phiên, tiêu đề do model đặt, và chi phí của
chúng — ghi vào cuộc trò chuyện mà không đẩy mốc `updated_at`. Nếu không, một bản tóm tắt
viết xong sau khi người dùng đã rời đi sẽ đưa một cuộc cũ lên đầu danh sách và gắn chấm chưa
đọc cho thứ không ai viết thêm.

Về thị giác, mọi giá trị đi qua một bộ token trong `web/src/styles/tokens.css`: thang chữ,
khoảng cách, bo góc, bóng, bề mặt và các màu trạng thái, mỗi màu có bản sáng và tối. Chế độ
tối theo hệ điều hành, không có công tắc riêng. Font Inter đóng gói kèm bundle, gồm cả bộ
ký tự tiếng Việt, không tải từ CDN. Icon là một bộ nét SVG vẽ tay trong
`components/ui/icon.tsx` thay cho emoji, vì emoji mỗi nền tảng vẽ một kiểu và theme không
đổi được màu của nó. Mỗi agent có một avatar là chữ cái đầu trên nền màu riêng, băm từ id
nên ở đâu cũng cùng một màu. Logo trên sidebar cũng là favicon và icon khi cài app:
`npm run icons` vẽ các PNG từ `web/public/favicon.svg`. Thẻ **Cần bạn xử lý** xám khi cả
màn quản lý không còn gì chờ và chỉ chuyển màu cảnh báo khi có việc; trong lịch sử duyệt, yêu cầu hết hạn mang
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
