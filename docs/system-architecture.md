---
layout: default
title: Kiến trúc hệ thống — giải phẫu một agent harness
---

# Kiến trúc hệ thống: giải phẫu một agent harness

**Phiên bản**: 0.6.0 · **Cập nhật**: 2026-09-25

Tài liệu này dành cho người chưa từng xây agent harness. Nó trả lời ba câu hỏi: harness gồm những gì, mỗi phần làm việc gì, và chúng khớp với nhau ra sao khi một tin nhắn đi qua. Mọi ví dụ lấy từ một bộ cài thật của my-agent-crew: một master "Trợ lý", ba agent việc cá nhân (Pong, HLV sức khoẻ, sổ cái) và ba agent kỹ thuật (lập trình, cố vấn, nghiên cứu), tất cả chạy trong một tiến trình trên máy cá nhân, nói chuyện qua web UI và một bot Telegram.

Năm sơ đồ trong tài liệu là **bản động**: nhúng thẳng vào trang, có animation và thanh chuyển view — bấm tên view để xem từng lớp. Nếu trang được đọc ở nơi không chạy được HTML nhúng (GitHub, trình đọc markdown), dùng link "Mở riêng" hoặc ảnh tĩnh SVG ngay dưới mỗi sơ đồ. Gallery cả năm: [diagrams/index.html](diagrams/index.html); cách publish ở [deployment-guide.md §9](deployment-guide.md#9-publish-bộ-doc-để-sơ-đồ-archify-chuyển-động).

## 1. Harness là gì

Model ngôn ngữ chỉ làm một việc: nhận một danh sách message, trả về một message. Nó không nhớ gì giữa hai lần gọi, không chạm được vào đĩa, không gọi được API, không biết hôm nay là ngày nào. Mọi thứ còn lại — nhớ, làm, hỏi lại, dừng đúng lúc — là việc của phần mềm bao quanh model. Phần mềm đó gọi là **harness**.

Một harness tối thiểu có bốn việc:

| Việc | Câu hỏi nó trả lời | Ở my-agent-crew |
|---|---|---|
| Lắp ngữ cảnh | Model cần biết gì trước khi đọc tin nhắn? | system prompt lắp lại từ tệp trong home mỗi vòng |
| Vòng lặp tool | Model muốn làm gì, ai làm, kết quả về đâu? | một vòng lặp lượt + một sổ đăng ký tool |
| Lưu và tiếp tục | Lượt sau biết gì về lượt trước? | SQLite + `MEMORY.md` + ghi chú ngày |
| Kiểm soát | Khi nào dừng, khi nào hỏi người? | approval, `cost_cap_usd`, `max_steps` |

my-agent-crew thêm hai tầng lên trên: **nhiều agent** (mỗi agent là một thư mục tệp) và **nhiều kênh** (web, Telegram, lịch cron), tất cả đổ vào cùng một vòng lặp.

## 2. Giải phẫu harness

<iframe src="diagrams/crew-architecture.html" title="Giải phẫu harness my-agent-crew" loading="lazy" style="width:100%;height:1140px;border:1px solid #d0d7de;border-radius:8px;background:#fff"></iframe>

*Bốn view: Một cổng vào, Vòng lặp agent, Ngữ cảnh từ đĩa, Quan sát và lưu. [Mở riêng](diagrams/crew-architecture.html) · [ảnh tĩnh](diagrams/crew-architecture.svg).*

Sơ đồ chia làm ba vùng. Đọc từ trái sang phải: người dùng đi vào qua **kênh giao tiếp**, mọi việc xảy ra trong **runtime** (một tiến trình Python), và mọi thứ tồn tại lâu dài nằm trong **home** trên đĩa.

### 2.1 Kênh giao tiếp

- **Web UI** (`web/`, React, được đóng gói vào `my_agent_crew/server/static`): chat, xem run, duyệt tool, sửa trí nhớ, xem job, quản lý kết nối (khoá API, Telegram, host). Nói chuyện với server qua REST + SSE. Mọi path đi qua một hàng rào cục bộ: `Host` phải là IP, `localhost` hoặc tên trong `MY_AGENT_ALLOWED_HOSTS`, `Origin` (nếu có) phải khớp đúng host:port; 403 nêu tên host bị từ chối. Server không có đăng nhập.
- **Telegram** (`channels/`): một poller `getUpdates` cho bot của master. Tin nhắn, ảnh, album được đưa về cùng cổng `/api/inbound` như web. Người dùng chỉ chat với master; đội trả lời qua master. Khi bot dừng (đổi token, tắt server), lượt đang chạy được chờ tới 30 s; quá hạn thì bị cắt và chat được báo để người gửi lại.
- **Activity hub** (`activity/`): không phải kênh vào mà là kênh ra. Mỗi lượt là một *run* gồm các *step* (model call, tool call, approval…); hub phát chúng qua SSE `/api/activity/stream` để web hiển thị đúng lúc.

### 2.2 Inbound: một cổng vào

Inbound là cổng duy nhất cho tin nhắn từ người. Nó làm ba việc nhỏ nhưng quan trọng:

1. Tìm hoặc tạo cuộc trò chuyện theo kênh và ngày (một cuộc trò chuyện mỗi ngày mỗi kênh cho master).
2. Từ chối (HTTP 409) nếu lượt trước còn đang chạy hoặc đang chờ duyệt — không xếp hàng, không chạy song song trên cùng cuộc trò chuyện.
3. Chạy lượt và đăng ký run với activity hub.

Job lịch không đi qua Inbound: scheduler chạy thẳng một lượt với nguồn `job` trên cuộc trò chuyện riêng của job. Hai đường, một vòng lặp.

### 2.3 Vòng lặp agent

Gói `agent/` là trái tim. Một lượt:

```
messages = lịch sử cuộc trò chuyện + tin mới
lặp tối đa max_steps:
    system = lắp system prompt từ tệp của agent   # lắp lại mỗi vòng
    reply  = model(system, messages, mô tả tool)
    nếu reply không gọi tool: kết thúc, lưu, trả lời
    với mỗi tool_call:
        nếu tool cần duyệt và cuộc trò chuyện không autonomous:
            tạo approval, phát ApprovalRequired, dừng lượt (tiếp tục sau khi duyệt)
        result = chạy tool                          # cắt còn tool_output_chars
    messages += reply + results
```

Điểm cần nhớ với người mới: **model không "chạy" gì cả**. Nó chỉ trả về JSON nói "tôi muốn gọi `workspace_read` với path này". Harness quyết định có chạy không, chạy rồi đưa kết quả vào message tiếp theo. Mọi cổng kiểm soát nằm ở chỗ này.

### 2.4 Sổ đăng ký tool: tay chân của agent

Gói `tools/` giữ danh sách tool mà agent được dùng (`tools:` trong `agent.yaml`). Mỗi tool có phần mô tả (tên, mô tả, tham số JSON — đưa cho model) và phần chạy (hàm Python thật). Bộ tool có sẵn:

| Nhóm | Tool | Cần duyệt |
|---|---|---|
| Workspace | `workspace_list`, `workspace_read`, `workspace_glob`, `workspace_grep` | không |
| Workspace | `workspace_write`, `workspace_edit` | có |
| Shell | `shell_run` (cwd = workspace, có `shell_ask_patterns` và `shell_deny_patterns`; `shell_network: false` hoặc `shell_write_paths` thì chạy trong `sandbox-exec`, chỉ ghi dưới các đường dẫn đó, không mạng nếu `shell_network: false`) | có |
| Web | `fetch_url`, `web_search` | không |
| Trí nhớ | `memory_save`, `memory_search`, `user_memory_save`, `user_memory_forget`, `wiki_get`, `wiki_search`, `wiki_apply` | không |
| Đội | `delegate` | không |
| Với người | `ask_user` (dừng lượt, chờ câu trả lời), `progress_note` (một câu "đang làm gì" lên timeline) | không |
| Khác | `image_read`, `pdf_read`, `skill_read` | không |

Chi tiết từng tool ở [tools.md](tools.md).

### 2.5 Provider: model là dịch vụ ngoài

Gói `llm/` nói chuyện với OpenRouter (và Ollama) và bọc thành một chuỗi tuyến: một danh sách model theo thứ tự (`routes:` trong `agent.yaml`), model đầu lỗi hoặc quá tải thì thử model tiếp và phát `RouteFallback` để người dùng thấy. Provider giả (`MY_AGENT_ROUTES=fake:echo`) để chạy test và thử harness không tốn tiền.

### 2.6 Scheduler

`scheduler/` đọc `schedules:` của mọi agent, mỗi phút kiểm tra cron, đến hạn thì tạo một job run: một cuộc trò chuyện autonomous với prompt (hoặc lệnh kit) định sẵn. Trạng thái job lưu ở bảng `job_state`, xem ở `/api/jobs`.

### 2.7 Home: agent là tệp

Mọi thứ làm nên một agent là tệp văn bản trong `~/.my-agent-crew/agents/<id>/`:

| Tệp | Vai trò | Khi nào được đọc |
|---|---|---|
| `agent.yaml` | model, tool, giới hạn, lịch, delegates, Telegram | khi nạp roster |
| `AGENTS.md` | vai trò và cách làm việc | mỗi lượt, đầu system prompt |
| `SOUL.md` | giọng và tính cách | mỗi lượt |
| `MEMORY.md` | điều agent tự đúc kết | mỗi lượt |
| `memory/YYYY-MM-DD.md` | ghi chú ngày | hôm qua + hôm nay mỗi lượt; 7 ngày khi consolidate |
| `skills/*.md` | kỹ năng | chỉ mục mỗi lượt, nội dung khi `skill_read` |
| `.agents/` | kit lệnh/agent/hook kiểu Claude Code | lệnh vào roster; hook chạy quanh tool |
| `workspace/` | nơi tool đọc/ghi | khi tool chạy |

Dùng chung cho mọi agent: `config.yaml`, `agent.sqlite3`, `users/owner/` (USER.md + facts), `skills/` và `.agents/` cấp home. Bố cục đầy đủ ở [agents.md](agents.md).

## 3. Một lượt chat: từ Telegram đến câu trả lời

<iframe src="diagrams/turn-sequence.html" title="Một lượt chat qua Telegram" loading="lazy" style="width:100%;height:1390px;border:1px solid #d0d7de;border-radius:8px;background:#fff"></iframe>

*Bốn view: Nhận tin, Lượt của master, Giao việc cho HLV, Trả lời. [Mở riêng](diagrams/turn-sequence.html) · [ảnh tĩnh](diagrams/turn-sequence.svg).*

Ví dụ thật: người dùng nhắn bot "hôm nay ăn thế nào cho hợp lịch tập?".

1. **Poller Telegram** nhận update, chuyển thành `POST /api/inbound {text}`. Ảnh (nếu có) được tải về `workspace/inbox/` và đưa vào tin nhắn dưới dạng đường dẫn.
2. **Inbound** tìm cuộc trò chuyện `telegram:<chat>` của hôm nay, thấy rảnh, chạy một lượt cho master.
3. **Master** lắp system prompt: persona của "Trợ lý", `USER.md` + facts, `MEMORY.md`, tóm tắt cuộc hôm qua, roster (sáu agent, mỗi agent một dòng mô tả), lệnh kit, ghi chú ngày. Model thấy trong roster có "HLV sức khoẻ" và gọi tool `delegate(agent="health-coach", task=…)`.
4. **Delegate** chạy một lượt con: agent con có persona riêng, tool riêng, workspace riêng, và *chỉ nhận brief* — không thấy lịch sử chat của master. Lượt con là cuộc trò chuyện autonomous nên tool cần duyệt không dừng.
5. Kết quả lượt con quay về master dưới dạng tool result. Master viết câu trả lời cuối, harness lưu message, phát `Done`, poller gửi về Telegram.

Trên web UI, toàn bộ chuỗi này hiện thành một run với các step lồng nhau, kể cả run con của HLV.

## 4. Master giao việc cho đội

<iframe src="diagrams/delegation-workflow.html" title="Master giao việc cho đội" loading="lazy" style="width:100%;height:1090px;border:1px solid #d0d7de;border-radius:8px;background:#fff"></iframe>

*Ba view: Từ yêu cầu đến trả lời, Ai làm gì, Cổng và giới hạn. [Mở riêng](diagrams/delegation-workflow.html) · [ảnh tĩnh](diagrams/delegation-workflow.svg).*

Trong bộ cài thật, master "Trợ lý" để trống `delegates:`, nghĩa là giao được cho cả sáu agent còn lại:

| Agent | Vai trò | Nguồn |
|---|---|---|
| pong | thư ký cá nhân: bản tin sáng, mail, lịch, tasks, Goodreads | viết tay, chuyển từ openclaw |
| ledger | sổ cái tài chính, nhắc hạn, giá vàng; không tool mạng, không ghi trí nhớ dùng chung | viết tay, tách khỏi pong |
| health-coach | HLV sức khoẻ: ăn, tập, Garmin, sách | viết tay, chuyển từ openclaw |
| fullstack-developer, kongming, researcher | làm phần mềm trọn gói · cố vấn chỉ đọc · tra cứu mọi chủ đề | `agent add <template>` |

Cách quyết định giao hay tự làm nằm ở model của master, nhưng harness bảo đảm ba điều:

- **Roster là sự thật trên đĩa.** Model chỉ thấy agent có trong `delegates:`; không có "gọi bừa".
- **Lượt con bị cô lập.** Brief đi xuống, kết quả đi lên; lịch sử, trí nhớ riêng, workspace không trộn. Facts về người dùng (`users/owner/facts/`) là thứ duy nhất mọi agent cùng thấy.
- **Giới hạn cộng dồn.** Lượt con có `max_steps` riêng, nhưng trần chi phí của nó là phần còn lại của master (`cost_cap_usd` trừ đã tiêu); chi phí lượt con được cộng ngược vào master để một lần fan-out không tiêu gấp đôi và `/api/stats` nói thật.

Web UI ghim kết quả delegate vào thread của master để người đọc thấy ai đã trả lời gì.

## 5. Cổng duyệt tool

<iframe src="diagrams/approval-lifecycle.html" title="Vòng đời một yêu cầu duyệt tool" loading="lazy" style="width:100%;height:1120px;border:1px solid #d0d7de;border-radius:8px;background:#fff"></iframe>

*Ba view: Cổng duyệt, Đường tắt, Kết thúc. [Mở riêng](diagrams/approval-lifecycle.html) · [ảnh tĩnh](diagrams/approval-lifecycle.svg).*

Đây là cơ chế khiến harness khác một script gọi API. Khi model gọi `shell_run`, `workspace_write` hoặc `workspace_edit`:

1. Harness tạo một dòng trong bảng `approvals`, phát `ApprovalRequired`, và **dừng lượt**. Không có gì chạy.
2. Người dùng thấy thanh duyệt trên web UI. `POST /api/approvals/{id}` với `approve`, `deny`, hoặc `approve + always`.
3. Duyệt: harness chạy tool, kết quả về model, lượt tiếp tục như chưa từng dừng. `always` ghi tên tool vào `auto_approve` của cuộc trò chuyện đó.
4. Từ chối: model nhận tool result `DENIED_TOOL` và tự quyết bước tiếp — lượt không hỏng.
5. Hết hạn: scheduler quét định kỳ; approval quá `approval_ttl_seconds` (600 s) bị đánh dấu expired và xử lý như từ chối. Fail-closed: không ai trả lời thì không chạy.

Hai đường tắt có chủ đích:

- Cuộc trò chuyện **autonomous** (job lịch, lượt delegate, hoặc agent có `autonomous: true`) bỏ qua cổng. Trong bộ cài thật, cả Pong lẫn HLV đều `autonomous: true` vì chúng chạy chủ yếu theo lịch.
- `shell_ask_patterns` buộc hỏi cả khi autonomous cho lệnh khớp mẫu nguy hiểm.

Khi một approval đang chờ, `/api/inbound` trả 409 để người dùng không vô tình mở lượt thứ hai trên cùng cuộc trò chuyện.

## 6. Ngữ cảnh đi vào, trí nhớ đi ra

<iframe src="diagrams/context-dataflow.html" title="Ngữ cảnh đi vào model và trí nhớ đi ra đĩa" loading="lazy" style="width:100%;height:1230px;border:1px solid #d0d7de;border-radius:8px;background:#fff"></iframe>

*Bốn view: Vào system prompt, Theo yêu cầu, Ra đĩa, Cô đọng. [Mở riêng](diagrams/context-dataflow.html) · [ảnh tĩnh](diagrams/context-dataflow.svg).*

Quy tắc duy nhất: **model không có trạng thái ẩn**. Điều gì cần nhớ sang lượt sau phải là tệp hoặc dòng trong SQLite. Vì vậy có hai chiều:

**Vào** — system prompt lắp lại mỗi lượt, theo thứ tự cố định:

1. persona: `AGENTS.md`, `SOUL.md`
2. người dùng: `users/owner/USER.md` + `facts/*.md`
3. `MEMORY.md` của agent
4. "Cuộc trước (lần cuối 24/9 23:30)": tóm tắt cuộc trò chuyện gần nhất (bảng `conversations`). Mỗi dòng transcript đưa đi tóm tắt mở đầu bằng ngày giờ theo múi giờ người dùng, và bản tóm tắt ghi ngày cụ thể thay cho "hôm nay", "hôm qua": nó được đọc vào một ngày khác
5. roster và lệnh kit (`.agents/commands/*.md`, ví dụ `/tongket` trong bộ cài thật)
6. ghi chú `memory/<hôm qua>.md` và `memory/<hôm nay>.md`

Skill không vào toàn văn: chỉ chỉ mục tên + mô tả; agent gọi `skill_read` khi cần. Skill có `always: true` thì vào toàn văn.

**Ra** — trong lượt:

- `messages`, `runs`, `usage`: SQLite, tự động.
- `memory_save`: ghi vào `memory/YYYY-MM-DD.md` của riêng agent.
- `user_memory_save` / `user_memory_forget`: sửa `users/owner/facts/<name>.md`, mọi agent cùng thấy.
- tool workspace: tệp trong `workspace/`.

**Cô đọng** — job `memory_consolidate` (cron trong `agent.yaml`; bộ cài thật đặt một lần mỗi tuần) đọc 7 ngày ghi chú, nhờ model viết lại `MEMORY.md`, và tạo một *đề xuất* (`memory_proposals`). Agent autonomous áp ngay; agent khác chờ người duyệt ở `/api/memory/proposals`. Bản cũ giữ lại để lùi.

Chi tiết ở [memory.md](memory.md).

## 7. Minh hoạ bằng bộ cài thật

Bộ cài dùng để viết tài liệu này (đã bỏ số liệu và định danh cá nhân):

```
~/.my-agent-crew/
├── config.yaml            # timezone
├── env                    # OPENROUTER_API_KEY, TELEGRAM_BOT_TOKEN (chmod 600, ngoài repo)
├── agent.yaml             # master "Trợ lý": autonomous, cost_cap_usd, max_steps, telegram
├── agent.sqlite3
├── run-server.zsh         # source env → uv run python -m my_agent_crew
├── logs/server.log
├── skills/                # code-review, debug, delegation, git, scout, test
├── .agents/commands/tongket.md
├── users/owner/{USER.md, facts/}
├── workspace/inbox/       # ảnh gửi qua Telegram
└── agents/
    ├── pong/              # AGENTS.md, SOUL.md, MEMORY.md, memory/, agent.yaml
    ├── health-coach/      # như trên
    ├── ledger/            # như trên, workspace = repo sổ cái
    └── fullstack-developer, kongming, researcher
```

Bốn agent đáng xem kỹ:

**Master "Trợ lý"** — không có persona dày; việc của nó là hiểu người dùng và chọn người làm. `routes` một model rẻ, `max_steps` cao hơn mặc định để đủ chỗ cho vài lần delegate trong một lượt. Là agent duy nhất có `telegram:`.

**Pong** — thư ký, chỉ Google Workspace và Goodreads. `routes` hai model rẻ theo thứ tự fallback. Ba lịch: bản tin sáng, tổng kết tuần, `memory_consolidate` hàng tuần. Lệnh ghi (gửi mail, ghi sheet, ghi Goodreads) nằm trong `shell_ask_patterns` nên luôn hỏi.

**Ledger** — sổ cái tài chính, tách khỏi Pong để agent cầm dữ liệu tiền bạc không có đường nào đưa nó ra ngoài: `tools` bỏ `web_search`, `fetch_url`, `delegate`, `user_memory_save`, `wiki_*`; `shell_network: false` nên mọi `shell_run` chạy trong sandbox của macOS: không mạng, không `open`/`osascript`, chỉ ghi được dưới `shell_write_paths` và thư mục temp; `shell_ask_patterns` chỉ còn là lớp phụ. Ba lịch: bảo trì đêm (lệnh), nhắc hạn (prompt), giá vàng (lệnh). Gọi script của repo sổ cái bằng `shell_run` — harness chỉ biết cwd và lệnh.

**HLV sức khoẻ** — `routes` ba model, tăng dần từ rẻ đến mạnh. Ba lịch: bảo trì đêm, sao lưu, bản tin sáng có gắn skill Garmin. Đọc ảnh bữa ăn qua `image_read` (tuyến `vision_routes`). Là ví dụ điển hình của agent "một người dùng, một lĩnh vực, nhớ dài".

Ba agent còn lại đến từ `agent add <template>`: fullstack-developer làm trọn việc phần mềm, hỏi kongming (cố vấn chỉ đọc, model mạnh nhất) khi bế tắc và researcher khi cần tra ngoài. Không có lịch, chỉ được gọi qua delegate.

Kit `.agents/` cấp home cho master lệnh `/tongket` — ví dụ về việc harness nạp lệnh kiểu Claude Code làm "prompt có tên" mà không cần code thêm.

## 8. Những hiểu lầm hay gặp

| Hiểu lầm | Thực tế trong harness này |
|---|---|
| "Agent nhớ chuyện hôm qua" | Chỉ nhớ nếu có trong `MEMORY.md`, ghi chú ngày, facts, hay tóm tắt cuộc trước. Không có tệp, không có ký ức. |
| "Model chạy lệnh shell" | Model chỉ xin. Harness chạy, và chỉ khi có duyệt hoặc autonomous. |
| "Agent con thấy cả cuộc chat" | Không. Nó chỉ thấy brief trong `delegate`. Muốn nó biết gì, master phải viết vào brief. |
| "Tăng `max_steps` là agent thông minh hơn" | Chỉ cho nó nhiều vòng hơn. Vòng lặp vô tận tốn tiền nhanh; `cost_cap_usd` là phanh thứ hai. |
| "Fallback model là im lặng" | `RouteFallback` là event nhìn thấy trên web; run ghi model nào thực sự trả lời. |
| "Skill là plugin" | Skill là tệp markdown. Nó thay đổi *lời khuyên* cho model, không thêm khả năng mới. Khả năng mới là tool. |
| "Xoá cuộc trò chuyện là agent quên" | Cuộc trò chuyện là log; trí nhớ dài nằm ở tệp. Hai thứ tách nhau có chủ đích. |

## 9. Mở rộng harness

Năm điểm cắm, theo [design.md](design.md) "Extension points":

| Muốn thêm | Làm gì | Ở đâu |
|---|---|---|
| Model/provider mới | một provider biết stream; lắp vào chỗ server dựng provider cho từng agent | `llm/`, `server/` |
| Tool mới | mô tả cho model + hàm chạy; lắp vào chỗ server dựng bộ tool cho từng agent | `tools/`, `server/` |
| Kỹ năng | tệp `.md` có front matter `name`, `description`, `always` | `skills/` của home hoặc agent |
| Agent mới | một thư mục có `agent.yaml` + persona | `agents/<id>/`, hoặc `agent add` |
| Kênh mới | start / stop / deliver; dựng từ khối trên hồ sơ master | `channels/` |

Không có điểm cắm cho "thay vòng lặp": vòng lặp lượt là bất biến có chủ ý, để mọi kênh, mọi agent, mọi job đi qua cùng một cổng kiểm soát.

## Tham chiếu

- [design.md](design.md) — nguyên tắc thiết kế và runtime shape
- [agents.md](agents.md) — `agent.yaml`, persona, bố cục home, kit
- [tools.md](tools.md) — từng tool và cổng duyệt
- [memory.md](memory.md) — ghi chú ngày, facts, consolidate
- [channels.md](channels.md) — Telegram
- [testing.md](testing.md) — chạy test
- [codebase-summary.md](codebase-summary.md) — bản đồ mã nguồn
- [diagrams/README.md](diagrams/README.md) — tái tạo sơ đồ

## Câu hỏi mở

- Master hiện là agent duy nhất có Telegram; nếu sau này muốn một bot cho mỗi agent, sơ đồ §2 cần thêm một poller cho mỗi agent và Inbound cần khoá theo `(agent, chat, ngày)`.
- Lượt con của delegate không có TTL riêng; một agent con treo ở model chậm sẽ giữ master treo theo tới `max_steps` của chính nó.
