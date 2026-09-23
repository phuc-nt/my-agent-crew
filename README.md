# my-agent-crew

Một đội agent chạy local, có web UI thân thiện và một chỗ chat duy nhất. Agent đọc/ghi tệp
trong thư mục làm việc, chạy shell, tải trang web, tìm kiếm, đọc ảnh và PDF, ghi nhớ lâu dài —
và **hỏi bạn trước** mọi thao tác thay đổi dữ liệu, trừ những lệnh bạn đã nói là quen thuộc.

Bạn chỉ nói chuyện với một agent chính; nó tự làm việc nhỏ và giao việc lớn cho đúng người
trong đội. Việc đang chạy hiện thành timeline từng bước, nên lúc nào cũng thấy agent đang làm gì.

Đây là bản viết lại tinh gọn của [my-crew](https://github.com/phuc-nt/my-crew): bỏ router và DAG,
giữ agent + công cụ + kỹ năng + trí nhớ, đặt web UI làm mặt tiền chính.

## Chạy

```bash
uv sync
OPENROUTER_API_KEY=... uv run python -m my_agent_crew
# mở http://127.0.0.1:8765
```

Không có khoá? Chạy thử với provider echo (không gọi model thật):

```bash
MY_AGENT_ROUTES=fake:echo uv run python -m my_agent_crew
```

Trong chế độ echo, gõ `/tool <tên> {json}` để gọi công cụ trực tiếp, ví dụ
`/tool workspace_list {"path":"."}`.

## Cấu hình

Bí mật **chỉ** đọc từ biến môi trường; `config.yaml` chỉ chứa các khoá không nhạy cảm.

| Biến môi trường | Ý nghĩa | Mặc định |
|---|---|---|
| `MY_AGENT_HOME` | thư mục dữ liệu (db, workspace/, skills/, config.yaml) | `~/.my-agent-crew` |
| `MY_AGENT_ROUTES` | chuỗi tuyến `provider:model`, cách nhau bởi dấu phẩy, thử theo thứ tự | `openrouter:deepseek/deepseek-v4-flash` |
| `MY_AGENT_COST_CAP_USD` | ngân sách mặc định mỗi cuộc trò chuyện (0 = không giới hạn) | `0.5` |
| `MY_AGENT_MAX_STEPS` | số lượt gọi model tối đa trong một lượt | `12` |
| `MY_AGENT_AUTONOMOUS` | `1` để công cụ ghi/thay đổi chạy không cần duyệt | tắt |
| `MY_AGENT_APPROVAL_TTL_SECONDS` | yêu cầu duyệt không ai trả lời trong khoảng này thì tự từ chối, lượt chạy tiếp | `600` |
| `MY_AGENT_TIMEZONE` | múi giờ của bạn (tên IANA, vd `Asia/Ho_Chi_Minh`) cho lịch, "hôm nay" trong prompt và thống kê; DB vẫn lưu UTC | múi giờ máy |
| `OLLAMA_BASE_URL` | nơi ollama local lắng nghe; không cần khoá nên provider này luôn sẵn sàng | `http://127.0.0.1:11434/v1` |
| `OPENROUTER_API_KEY` | bật provider OpenRouter | — |
| `TAVILY_API_KEY` / `BRAVE_API_KEY` | nguồn tìm kiếm trả phí; không đặt thì `web_search` vẫn chạy bằng DuckDuckGo | — |
| `FIRECRAWL_BASE_URL` | host firecrawl cho tìm kiếm và đọc trang dạng markdown | — |
| `FIRECRAWL_API_KEY` | chỉ cần với firecrawl cloud | — |
| tên do `telegram.token_env` chỉ định (vd `TELEGRAM_BOT_TOKEN`) | token bot Telegram của master; thiếu thì kênh tắt | — |

`config.yaml` trong `MY_AGENT_HOME` nhận đúng các khoá: `routes`, `vision_routes`,
`cost_cap_usd`, `max_steps`, `language`, `timezone`, `autonomous_default`,
`approval_ttl_seconds`, `tool_output_chars`, `shell_ask_patterns`, `shell_allow_patterns`.
Khoá lạ làm server báo lỗi lúc khởi động, để một chữ gõ sai không âm thầm vô hiệu hoá thiết lập.
Chi tiết từng khoá: [docs/agents.md](docs/agents.md#agentyaml).
Kỹ năng tự viết: thêm tệp `.md` có frontmatter `name` vào `skills/`.
Kỹ năng không gắn sẵn chỉ hiện tên + mô tả trong prompt; model gọi `skill_read` để đọc đủ.
Kỹ năng gọi chương trình ngoài thì khai `requires.bins: [gws]` và `cliHelp: gws --help`:
thiếu chương trình thì kỹ năng vẫn được giữ nhưng mở đầu bằng cảnh báo, còn `cliHelp` nhắc
model đọc `--help` một lần thay vì đoán cú pháp lần thứ ba.
Mẫu chép được: [docs/examples/skills/](docs/examples/skills/) — chép vào `skills/` rồi điền chỗ trống.

## Nhiều agent có tên riêng

Mỗi thư mục `MY_AGENT_HOME/agents/<id>/` chứa `agent.yaml` cùng các tệp nhân cách
(`AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md`) và trí nhớ (`MEMORY.md`, `memory/YYYY-MM-DD.md`)
được nạp vào system prompt mỗi lượt. Ví dụ một huấn luyện viên sức khoẻ:

```yaml
name: HLV sức khoẻ
description: Đọc dữ liệu Garmin, gửi bản tin sáng
routes: [openrouter:z-ai/glm-5.3-flash, openrouter:z-ai/glm-5]
workspace: ~/workspace/my-health-coach   # sandbox cho công cụ tệp + shell_run
skills_dirs: [~/workspace/shared-skills]  # kỹ năng dùng chung ngoài home
autonomous: true                          # job chạy không cần duyệt
schedules:
  - id: morning-brief
    name: Bản tin sáng
    cron: "0 7 * * *"                     # giờ máy, 5 trường
    skills: [garmin]                      # gắn sẵn kỹ năng cho lượt chạy này
    prompt: |
      Chạy scripts/health-sync.py --json rồi viết bản tin 4-6 dòng…
      Kèm ảnh bằng dòng `MEDIA: data/charts/sleep.png`,
      kèm tệp bằng dòng `FILE: data/tuan-nay.csv`.
  - id: backup
    name: Sao lưu Drive
    cron: "20 2 * * *"
    command: ./scripts/backup-to-drive.sh
memory_consolidate: "30 3 * * 1"            # mỗi thứ Hai, viết lại MEMORY.md từ nhật ký
```

Agent giữ dữ liệu không được rời máy (ví dụ sổ cái) đặt `shell_network: false`: mọi `shell_run`
chạy trong `sandbox-exec` không mạng, chỉ ghi được dưới `shell_write_paths` — xem [agents.md](docs/agents.md).

Job `prompt` mở một cuộc trò chuyện mới và chạy như người dùng nhắn; job `command` chỉ chạy shell.
Kết quả job `prompt` được gửi vào chat Telegram (nếu có bot, xem dưới) với dòng đầu `[Tên agent]`;
dòng `MEDIA:` thành ảnh lấy từ workspace của agent đó, dòng `FILE:` thành tệp đính kèm
(`pdf`, `csv`, `md`, `txt`, `xlsx`, `json`, `zip`, tối đa 20 MB) — ảnh bị nén lại nên biểu đồ
gửi bằng `MEDIA:`, còn bảng số liệu phải gửi bằng `FILE:` mới giữ nguyên bytes.

## Mang kit `.claude/` / `.opencode/` sang

Đã có sẵn subagent, lệnh, kỹ năng và hook từ Claude Code hay opencode? Chép nguyên thư mục vào
home là dùng được, không cần viết lại:

```
cp -r ~/.claude ~/.my-agent-crew/.agents     # hoặc giữ tên .claude / .opencode, đọc như nhau
```

- `agents/<id>.md` (front matter `name`, `description`, `tools`, `model` + thân là nhân cách)
  → một thành viên đội; `agent.yaml` cùng id luôn thắng.
- `commands/**/*.md` → lệnh `/tên` (`commands/mk/plan.md` là `/mk:plan`), nhận `$ARGUMENTS`,
  `$1`…`$9`; dùng được trên web lẫn Telegram.
- `skills/` → thêm vào đường kỹ năng; `settings.json` `hooks.PreToolUse/PostToolUse` → hook chạy
  trước/sau mỗi công cụ với JSON quen thuộc trên stdin (`Bash` khớp `shell_run`, exit 2 chặn).
- Chỉ đọc kit ở home và ở thư mục agent. Repo mà agent làm việc trong đó (workspace) là nguồn
  dữ liệu: `.claude/` và `AGENTS.md` của repo dành cho người phát triển repo, không ảnh hưởng
  tới agent của đội.

Chi tiết: [docs/agents.md](docs/agents.md#kits-agents-claude-opencode).

## Đọc ảnh và PDF

Ảnh gửi qua Telegram được lưu vào `workspace/inbox/`; mọi agent có công cụ `image_read`
(đường dẫn + câu hỏi) gửi ảnh cho tuyến `vision_routes` (mặc định hai model vision rẻ trên
OpenRouter) và nhận câu trả lời dạng chữ. Master xem qua một lần để biết giao cho ai, agent nhận
việc tự xem lại với câu hỏi của mình. Đặt `vision_routes: []` để tắt.

`pdf_read` đọc tài liệu theo cùng đường dẫn đó. Trang đã typeset thì lấy chữ ra miễn phí;
trang chụp ảnh mới được render rồi gửi qua `vision_routes`, mỗi trang một lần — nên tài liệu
trộn hai loại chỉ tốn tiền đúng những trang scan. Không cấu hình `vision_routes` thì PDF
typeset vẫn đọc được.

## Hỏi lại thay vì đoán

Gặp ngã ba thật sự, agent gọi `ask_user` để hỏi thay vì tự chọn — kể cả khi `autonomous` đang
bật, vì tự duyệt một câu hỏi thì chẳng ai trả lời. Câu hỏi hiện thành thẻ có sẵn lựa chọn trên
web, và trên Telegram thì trả lời theo số hoặc bằng lời. Hết giờ chờ không phải là từ chối:
agent nhận `default` đã khai rồi đi tiếp và nói rõ trong câu trả lời là nó tự quyết, nên một
job chạy lúc không ai xem vẫn nên luôn kèm `default`.

## Một trợ lý điều động cả đội

Web UI lẫn Telegram chỉ có **một** chỗ chat: với agent chính (`default`, gọi là *master*). Nó
tự làm việc nhỏ và giao việc lớn cho đúng người bằng công cụ `delegate`, rồi tổng hợp lại — bạn
không phải chọn agent. Mọi agent khác trong home (kể cả Pong hay HLV sức khoẻ) mặc định đều là
người master giao được; tab **Đội** trong khu quản lý liệt kê cả đội và cài thêm vai mới từ mẫu bằng
một cú bấm. Tuỳ chỉnh master bằng `~/.my-agent-crew/agent.yaml` (tên, mô tả, `autonomous`,
`cost_cap_usd`, `max_steps`, hoặc `delegates` để thu hẹp đội).

**Telegram** là cùng cơ chế trên điện thoại. Khai bot trong `agent.yaml` của master:

```yaml
telegram:
  token_env: TELEGRAM_BOT_TOKEN   # TÊN biến môi trường giữ token, không phải token
  chat_id: 123456789              # chat duy nhất được trả lời
```

Server poll bot đó: tin nhắn từ `chat_id` thành lượt chat của master theo ngày, master giao
việc cho Pong/HLV khi cần và trả lời lại chat; ảnh hay tệp bạn gửi được lưu vào `inbox/` của
workspace master và master chuyển đường dẫn cho agent cần đọc. Lệnh gạch chéo (`/new`, `/help`,
`/status`, `/tools`, `/approve`, `/deny`) do kênh tự trả lời, không tốn lượt model. Khối
`telegram` đặt ở agent khác bị bỏ qua kèm cảnh báo.

Three templates available: `fullstack-developer` takes a software task end to end (scout, plan,
code, test, self-review, commit) and may consult the other two; `kongming` is a read-only adviser
for hard design or debugging calls — pin your strongest model in its `routes`; `researcher`
researches any topic on the web and returns a ranked recommendation with sources. Templates use
the home's shared workspace; `--workspace` pins that role (and the peers it brings) to one
repository. Install via CLI or the **Đội** tab in the manage screen — web installs join the
running crew immediately; CLI installs need a server restart.

```bash
python -m my_agent_crew agent list-templates                                  # see the three templates
python -m my_agent_crew agent add fullstack-developer --workspace ~/src/app   # plus kongming and researcher
python -m my_agent_crew agent add researcher                                  # just the researcher
```

Edit an agent's profile (name, description, routes, tools, budget, schedules) from the **Đội** tab.
Tools across the whole crew, and who uses which, are in **Công cụ**. Connections (API keys,
Telegram, vision routes) are in **Kết nối**.

Giao việc như nói với người: *"Nhờ fullstack-developer thêm lệnh `--version` in phiên bản từ
pyproject, có test."* Master giao việc, fullstack-developer tự khảo sát, viết, test và soát, hỏi
kongming khi bế tắc — mỗi lần giao là một cuộc con hiện ngay trong manage screen, kèm chi phí và
số bước.
Uỷ quyền chỉ sâu một tầng: agent con không giao tiếp cho ai nữa.

Mọi nền tảng đi qua **một cổng backend**: web, Telegram và `POST /api/inbound` (JSON, trả lời
đồng bộ) đều đưa tin nhắn vào cùng chỗ, nên nâng cấp backend là mọi nền tảng theo ngay, và
test một tính năng chỉ cần gửi request:

```bash
curl -s http://127.0.0.1:8765/api/inbound -H 'content-type: application/json' \
  -d '{"text":"Nhờ kongming liệt kê thư mục làm việc rồi tóm tắt 2 câu."}'
# → {"conversation_id":…,"agent_id":"default","text":"…","status":"done","steps":2}
```

## Trí nhớ

Trí nhớ là Markdown trên đĩa, chia hai phạm vi: **chung về bạn** (`users/owner/USER.md` cùng
các tệp sự kiện trong `facts/`) — mọi agent đều đọc, nên nói với một agent là cả đội biết — và
**riêng của từng agent** (`MEMORY.md` + nhật ký `memory/YYYY-MM-DD.md`) cho việc nó tự làm.

Writes the person is present for land immediately; writes from unattended jobs become
proposals and wait for approval. Set `memory_consolidate` to have an agent periodically rewrite
its `MEMORY.md` from recent notes — also a proposal, keeping the old text for undo. The **Ghi nhớ**
tab in the manage screen edits everything: `USER.md`, facts, agent `MEMORY.md`, daily notes,
search both scopes, approve/deny proposals, and trigger consolidation immediately.

Cùng lúc đó, agent gom nhật ký hằng ngày thành một **vault wiki** (`memory/wiki/`): mỗi chủ đề
một trang Markdown, xếp vào `entities` / `concepts` / `syntheses` và liên kết nhau bằng
`[[tên trang]]` — thay cho tìm kiếm vector. Nhật ký trả lời "hôm đó xảy ra gì", wiki trả lời
"ta biết gì về chủ đề này". `wiki_apply` từ chối trang không khai `sources`, nên không trang
nào tự bịa ra mà lọt được; lint còn điểm mặt những trang đã mất nguồn. Mỗi lần dựng lại chỉ
phần máy viết được thay, phần người viết giữ nguyên. Xem, sửa và dựng lại ở tab **Wiki**
trong **Ghi nhớ**. Chi tiết:
[docs/memory.md](docs/memory.md).

Chi tiết cấu hình agent, công cụ, trí nhớ và kênh: [docs/agents.md](docs/agents.md),
[docs/tools.md](docs/tools.md), [docs/memory.md](docs/memory.md),
[docs/channels.md](docs/channels.md). Thư mục `agents/` là dữ liệu cá nhân, không nằm trong
repo này.

## Theo dõi hoạt động

Web UI split into two: chat with the master on the left, and a **manage screen** on the right
accessible via `#/manage/<section>`. The manage screen shows:

The UI is in Vietnamese, so the tabs are named below as they appear on screen:

- **Hoạt động** (activity): live runs with steps (model call, tool call, result, time, cost), an
  attention centre for runs waiting for approval or that failed, and a link to a run's own timeline.
- **Duyệt** (approvals): decided tool requests with their outcome (approved, denied, expired).
- **Đội** (crew), **Công cụ** (tools), **Lịch chạy** (jobs — next/last run, run-now button,
  pause/resume), **Ghi nhớ** (memory — chia tiếp thành **Về bạn**, **Của agent**, **Wiki**,
  **Tìm** và **Đề xuất**), **Chi phí** (costs, by agent / model / day),
  **Kết nối** (connections), **Cài đặt** (settings).

Inside the chat, `ConversationActivity` shows only that conversation's own runs, step by step.
The master's avatar in the header opens the crew tab; a chip `Crew: N` opens the manage screen
at the crew section. A line `MEDIA: <path in workspace>` in the reply is rendered as an image,
and `FILE: <path>` as a download link. Khi agent chuẩn bị làm một việc dài, nó gọi
`progress_note` để nói một câu ngắn đang làm gì, và câu đó hiện ngay trên timeline nên người
xem thấy tiến trình thay vì một vòng xoay.

## Phát triển

```bash
./scripts/gates.sh               # cả chín cổng CI, dừng ở cổng đỏ đầu tiên (~22 giây)
```

Hoặc chạy lẻ từng cổng:

```bash
uv run ruff check .              # lint
uv run ruff format --check .     # định dạng — cổng riêng, `ruff check` xanh không thay được
uv run pytest -q                 # backend
cd web && npm ci
npm run typecheck && npm test    # frontend unit
npm run e2e                      # Playwright (mock /api trong trình duyệt)
npm run bundle                   # dựng lại bundle vào my_agent_crew/server/static (đã commit)
```

Mỗi cổng làm gì và vì sao: [docs/code-standards.md §4](docs/code-standards.md#4-cổng-phải-chạy-trước-khi-commit).
Thay đổi từng bản: [CHANGELOG.md](CHANGELOG.md). Cách phát hành một phiên bản:
[docs/deployment-guide.md §6b](docs/deployment-guide.md#6b-phát-hành-một-phiên-bản).

Đọc [docs/design.md](docs/design.md) để hiểu các quyết định thiết kế,
[docs/testing.md](docs/testing.md) để biết tính năng nào được test ở tầng nào, và bộ tài liệu
tham chiếu [agents](docs/agents.md) · [tools](docs/tools.md) · [memory](docs/memory.md) ·
[channels](docs/channels.md).
