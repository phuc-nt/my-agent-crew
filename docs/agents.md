# Agent

**Phiên bản**: 0.6.0 · **Cập nhật**: 2026-09-25

Một **agent** là một thư mục dưới `MY_AGENT_HOME/agents/<id>/` gồm một `agent.yaml` và
vài tệp Markdown. Mọi agent chạy cùng một vòng lặp; profile chỉ
thay đổi đầu vào của nó: persona, trí nhớ, workspace, skill, tuyến model, ngân sách và lịch.
Kênh Telegram thuộc về riêng master.

## Bố cục thư mục

```
MY_AGENT_HOME/                      ~/.my-agent-crew by default
├── config.yaml                     global, non-secret keys (see below)
├── agent.sqlite3                   conversations, messages, runs, job state
├── agent.yaml                      the master's profile, incl. its `telegram` block (optional)
├── workspace/                      sandbox of the master; `inbox/` takes Telegram attachments
├── skills/                         skills of the master
├── telegram.offset                 poll offset of the master's bot, with the bot's id
├── users/owner/                    what the crew knows about the person (see memory.md)
│   ├── USER.md                     read by every agent, every turn
│   └── facts/<name>.md  INDEX.md   one fact each, plus the generated index
├── .agents/                        a kit (also `.claude/`, `.opencode/`), see Kits below
│   ├── agents/<id>.md              one crew member per file, front matter + persona
│   ├── commands/**/*.md            slash commands, `commands/mk/plan.md` is `/mk:plan`
│   ├── skills/                     skills for every agent
│   └── settings.json               `hooks.PreToolUse` / `PostToolUse` command hooks
└── agents/
    └── <id>/
        ├── agent.yaml              the profile (fixed key set, no secrets)
        ├── AGENTS.md  SOUL.md      persona files, read every turn
        ├── IDENTITY.md  USER.md
        ├── MEMORY.md               durable memory, read every turn
        ├── memory/YYYY-MM-DD.md    daily notes, today + yesterday read every turn
        ├── workspace/              default tool sandbox (overridable)
        ├── skills/                 always on the skill path
        └── .agents/                this agent's own kit (optional)
```

Thư mục agent, workspace và `memory/` được tạo lúc khởi động, nên chỉ cần một
profile cộng các tệp persona là đủ. Id của agent là tên thư mục; `default` được
dành riêng cho cài đặt cấp cao nhất (xem bên dưới).

## `agent.yaml`

Chỉ những khoá này được chấp nhận; khoá nào khác sẽ ném `ValueError` lúc khởi động, nên một lỗi gõ
không bao giờ âm thầm vô hiệu một cài đặt.

| Khoá | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| `name` | chuỗi | id | tên hiển thị; cũng là tiền tố `[Name]` trên bản tin gửi tới Telegram |
| `description` | chuỗi | `""` | hiện trên card của agent trong tab **Đội** và trong roster của master |
| `mode` | `assistant` hoặc `work` | `assistant` | `work` thêm các tool lập trình và đổi ba mặc định, xem [Chế độ work](#chế-độ-work) |
| `routes` | danh sách hoặc chuỗi phân cách bằng dấu phẩy dạng `provider:model` | `routes` toàn cục | thử theo thứ tự; tuyến nào hỏng trước khi sinh ra output thì rơi xuống tuyến kế tiếp |
| `reasoning` | `minimal`, `low`, `medium` hoặc `high` | trống | model nghĩ kỹ đến đâu, gửi lên OpenRouter thành `reasoning.effort` cho mọi tuyến của agent (kể cả tuyến dự phòng); trống thì để provider tự quyết. Model đang nghĩ thì web hiện "Agent đang suy nghĩ…", số token dùng để nghĩ lưu ở cột `reasoning_tokens` của `messages`, còn nội dung suy nghĩ không lưu. Ollama bỏ qua khoá này |
| `workspace` | đường dẫn | `workspace` | sandbox cho `workspace_*` và `shell_run`; đường dẫn tương đối tính từ thư mục agent, `~` được mở rộng |
| `persona_files` | danh sách tên tệp | `AGENTS.md, SOUL.md, IDENTITY.md, USER.md` | đọc từ thư mục agent vào system prompt mỗi lượt; tệp thiếu thì bỏ qua |
| `persona_names` | chỉ đọc | — | danh sách tên tệp persona thực sự có mặt (trả về bởi `GET /api/agents/{id}` và `GET /api/agents/{id}/prompt`) |
| `skills_dirs` | danh sách đường dẫn | `[]` | thư mục skill bổ sung; `<agent dir>/skills` luôn đứng đầu |
| `cost_cap_usd` | số ≥ 0 | toàn cục | ngân sách mỗi cuộc trò chuyện, `0` = không giới hạn |
| `max_steps` | int ≥ 1 | toàn cục | số lần gọi model mỗi lượt trước khi `halted` |
| `autonomous` | bool | `autonomous_default` toàn cục | cuộc trò chuyện mới bỏ qua cổng duyệt tool |
| `shell_ask_patterns` | danh sách chuỗi | toàn cục | lệnh shell vẫn hỏi ngay cả khi autonomous, xem [tools.md](tools.md#shell); khai báo nó sẽ thay thế mặc định, `[]` tắt hàng rào |
| `shell_allow_patterns` | danh sách chuỗi | toàn cục (rỗng) | lệnh shell đủ thường lệ để chạy không cần hỏi ngay cả khi *không* autonomous, xem [tools.md](tools.md#shell). Danh sách hỏi được kiểm tra trước, nên lệnh nằm trong cả hai thì vẫn hỏi |
| `tool_output_chars` | int ≥ 1 | toàn cục | số ký tự của một kết quả tool mà model thấy trước khi bị cắt; tăng lên cho agent có script in báo cáo dài |
| `shell_network` | bool | `true` | `false` chạy mọi lệnh `shell_run` trong một profile `sandbox-exec` của macOS: không mạng theo mọi hướng, không có các helper kiểu `open`/`launchctl`, chỉ ghi được dưới `shell_write_paths` và thư mục tạm (quy tắc ghi này cũng áp dụng khi còn mạng mà `shell_write_paths` được đặt), xem [tools.md](tools.md#shell). Chỉ đặt theo từng agent; `"false"` trong dấu nháy là lỗi khởi động |
| `shell_write_paths` | danh sách | `[]` | đường dẫn bên trong workspace mà lệnh `shell_run` được ghi. Đặt danh sách này là bật sandbox kể cả khi còn mạng: lệnh chỉ ghi được ở đây và thư mục tạm, không gọi được `open`/`launchctl`/`osascript`, nên agent lấy và ghi dữ liệu được nhưng không sửa được code, script hay cấu hình quanh nó. Với `shell_network: false` mà danh sách rỗng thì workspace chỉ đọc với shell; đường dẫn ra ngoài workspace là lỗi khởi động |
| `shell_deny_patterns` | danh sách | `[]` | mảnh lệnh (chuỗi con, không phân biệt hoa thường) mà `shell_run` từ chối thẳng, không hỏi duyệt, kèm lời dặn dừng lại và báo cần gì để người dùng quyết. Dùng để giữ agent làm việc trong repo người khác khỏi DDL, SQL ghi tay, `python3 -c`. Rào mềm như `shell_ask_patterns` |
| `write_paths` | danh sách | `[]` | đường dẫn bên trong workspace mà `workspace_write` và `workspace_edit` được ghi; ghi chỗ khác bị từ chối với lỗi nêu danh sách này, và không thư mục nào được tạo. Rỗng thì ghi được mọi nơi trong workspace. Dùng cho agent autonomous có workspace là một repo, nơi tệp lạc chỗ có thể bị commit lên; đường dẫn ra ngoài workspace là lỗi khởi động. Không ảnh hưởng `shell_run`, xem `shell_write_paths` |
| `schedules` | danh sách | `[]` | job, xem [Lịch](#lịch) |
| `memory_consolidate` | chuỗi cron | không có | theo lịch này, viết lại `MEMORY.md` từ ghi chú ngày rồi biên dịch wiki vault từ chính các ghi chú đó, xem [memory.md](memory.md) |
| `telegram` | map | không có | `token_env` + `chat_id`; chỉ đọc trên `agent.yaml` của master, ở nơi khác bị bỏ qua kèm cảnh báo, xem [channels.md](channels.md) |
| `delegates` | danh sách id agent | `[]` | agent mà agent này được giao việc cho; id không trỏ tới agent nào là lỗi khởi động. Rỗng trên master nghĩa là mọi agent khác, xem [Agent master](#agent-master) |
| `tools` | danh sách tên tool | `[]` | khi đặt, là những tool duy nhất agent này có; rỗng nghĩa là mọi thứ mode của nó mang lại. Tên lạ là cảnh báo, nên profile viết cho phiên bản mới hơn vẫn khởi động được |

Mọi giá trị không đặt sẽ rơi về cài đặt toàn cục, lấy từ biến môi trường
và `config.yaml`:

| Biến môi trường | Khoá `config.yaml` | Mặc định |
|---|---|---|
| `MY_AGENT_HOME` | — | `~/.my-agent-crew` |
| `MY_AGENT_ROUTES` | `routes` | `openrouter:deepseek/deepseek-v4-flash` |
| `MY_AGENT_COST_CAP_USD` | `cost_cap_usd` | `0.5` |
| `MY_AGENT_MAX_STEPS` | `max_steps` | `12` |
| `MY_AGENT_AUTONOMOUS` | `autonomous_default` | tắt (`1`, `true`, `yes`, `on` bật lên) |
| `MY_AGENT_APPROVAL_TTL_SECONDS` | `approval_ttl_seconds` | `600`; phải ≥ 1. Yêu cầu duyệt không ai trả lời trong khoảng này bị từ chối và lượt đi tiếp |
| `MY_AGENT_SHELL_ASK_PATTERNS` | `shell_ask_patterns` | danh sách trong [tools.md](tools.md#shell); giá trị env phân cách bằng `;` và giá trị rỗng tắt hàng rào |
| `MY_AGENT_SHELL_ALLOW_PATTERNS` | `shell_allow_patterns` | rỗng; phân cách bằng `;` như danh sách hỏi. Mẫu dưới hai ký tự, hoặc mẫu chỉ trông như ký tự đại diện, bị loại thay vì được chấp nhận |
| `MY_AGENT_TOOL_OUTPUT_CHARS` | `tool_output_chars` | `8000`; phải ≥ 1 |
| `MY_AGENT_LANGUAGE` | `language` | `vi` (ngôn ngữ khung prompt; `en` là lựa chọn còn lại) |
| `MY_AGENT_TIMEZONE` | `timezone` | múi giờ của máy; một tên IANA (`Asia/Ho_Chi_Minh`) đặt múi giờ mà lịch, "hôm nay" trong prompt và ghi chú trí nhớ, `/status` và thống kê được đọc theo. Tên lạ thì hỏng lúc khởi động |
| `MY_AGENT_OPENROUTER_PROVIDERS` | `openrouter_providers` | rỗng; danh sách (hoặc chuỗi phân cách bằng dấu phẩy) tên provider phía sau OpenRouter (`DeepSeek`, `OpenInference`…) thử theo thứ tự, gửi đi dưới `provider.order`. Ghim một provider để cache prompt không mất mỗi khi OpenRouter đổi bên phục vụ |
| `MY_AGENT_OPENROUTER_PROVIDER_FALLBACKS` | `openrouter_provider_fallbacks` | bật; `false` cấm OpenRouter rơi sang provider ngoài danh sách trên. Không có tác dụng khi danh sách rỗng |
| `MY_AGENT_VISION_ROUTES` | `vision_routes` | `openrouter:google/gemini-2.5-flash-lite, openrouter:qwen/qwen3-vl-8b-instruct`; chuỗi tuyến mà `image_read` gửi ảnh tới, xem [tools.md](tools.md#ảnh). Giá trị rỗng tắt đọc ảnh |
| `OLLAMA_BASE_URL` | — | `http://127.0.0.1:11434/v1`; nơi ollama cục bộ lắng nghe. Nó không cần khoá, nên provider này luôn được dựng, xem [tools.md](tools.md#provider-không-cần-khoá) |
| `OPENROUTER_API_KEY` | — | bật provider OpenRouter |
| `BRAVE_API_KEY` / `TAVILY_API_KEY` | — | bật `web_search` |
| tên trong `telegram.token_env` | — | token của bot; không đặt = kênh đó bị tắt |

Env thắng `config.yaml`; `config.yaml` chỉ chấp nhận các khoá ở trên. `routes` cũng được
sửa từ Quản lý → Kết nối, chỗ đó ghi lại đúng khoá này và giữ chú thích của tệp;
khi `MY_AGENT_ROUTES` đang đặt thì trang hiện tuyến ở dạng chỉ đọc. Bí mật không bao giờ
đi vào YAML: profile mang **tên** biến môi trường, và ngăn cài đặt chỉ hiện khoá có hay không,
không bao giờ hiện giá trị.

## Chế độ work

`mode: assistant` là hình dạng bình thường của sản phẩm: một agent trò chuyện, hỏi trước khi
chạm vào bất cứ thứ gì, và làm việc trong ngân sách cỡ một cuộc chat. `mode: work` là cùng vòng lặp đó
hướng vào một repository. Nó thêm `workspace_edit`, `workspace_grep` và `workspace_glob`
(xem [tools.md](tools.md#các-tool)) và đổi ba mặc định:

| Khoá | Assistant | Work | Vì sao |
|---|---|---|---|
| `autonomous` | mặc định toàn cục (tắt) | `true` | agent lập trình mà dừng chờ duyệt ở mỗi lần đọc tệp thì không bao giờ xong việc |
| `cost_cap_usd` | `0.5` | `20.0` | một việc thật chạy hàng chục bước; trần của chat sẽ chặn nó giữa chừng |
| `max_steps` | `12` | `120` | đọc, sửa, chạy test, đọc lỗi, sửa lại — thế đã hơn 12 rồi |

Bất cứ thứ gì profile tự khai vẫn thắng, nên `mode: work` với `autonomous: false`
là một agent work biết hỏi. Đây là mặc định, không phải một gói khoá cứng.

Tự chủ là chuyện duyệt, không phải chuyện im lặng. Một agent autonomous gặp ngã rẽ thật sự
vẫn dừng lại và hỏi qua `ask_user` (xem
[tools.md](tools.md#hỏi-người-dùng)), vì một câu hỏi tự duyệt cho chính nó thì
sẽ không ai trả lời. Thứ tự chủ bỏ đi là khoảng dừng trước mỗi tool, không phải khả năng
lên tiếng của agent.

## Template

Ba profile đi kèm gói phần mềm để một đội chạy được là một bản sao chứ không phải các tệp
viết tay. Template là dữ liệu thuần — một `agent.yaml` và các tệp persona bên cạnh
nó — nên bất cứ thứ gì nó diễn đạt được, một profile viết tay cũng làm được.

```bash
python -m my_agent_crew agent list-templates        # id, mode and description of each
python -m my_agent_crew agent add researcher        # one role, at the master's disposal
python -m my_agent_crew agent add fullstack-developer  # the developer and the two peers it names
python -m my_agent_crew agent add kongming --id advisor  # same template under a different id
python -m my_agent_crew agent add fullstack-developer --workspace ~/src/app  # pinned to one repository
```

Thêm một template sẽ kéo theo các đồng đội nó giao việc cho, vì server từ chối khởi động
khi một mục `delegates` trỏ tới agent không có mặt — nên `agent add fullstack-developer`
kéo theo cả kongming và researcher, còn `agent add researcher` chỉ cho một agent. Đồng đội đã
tồn tại thì giữ nguyên. Mọi manifest trỏ `workspace` tới `../../workspace`, workspace
dùng chung của home, nên bản cài mới chạy được mà không cần sửa; `--workspace` ghi một
đường dẫn tuyệt đối vào template và mọi đồng đội nó kéo theo.

Cùng thao tác cài này chạy qua HTTP, và đó là thứ tab **Đội** trong web UI gọi:

```
POST /api/agents/install {"template": "researcher", "agent_id"?: "…", "workspace"?: "…", "force"?: false}
→ 201 {"installed": ["researcher"], "live": ["researcher"], "needs_restart": false}
```

`installed` là những gì đã được ghi, `live` là những gì server đang chạy nạp ngay tại chỗ (master
có thể giao việc cho nó ngay), và `needs_restart` là true khi một agent vừa cài có
`schedules`: job chỉ khởi động lúc boot. 404 cho template
lạ, 409 khi id đã có người dùng (`force` ghi đè).

| id | mode | Dùng để làm gì |
|---|---|---|
| `fullstack-developer` | work | nhận một việc phần mềm từ đầu đến cuối — scout, lập kế hoạch, code, test, tự review, commit — theo các skill dùng chung; không có danh sách tool cho phép, chỉ giao việc cho hai agent còn lại, để xin tư vấn hoặc nghiên cứu, không bao giờ để đẩy code sang |
| `kongming` | work | chỉ tư vấn: đọc code và web, trả lời bằng một khuyến nghị có cấu trúc, không bao giờ hỏi ngược lại; không có tool ghi và không có `delegate`; ghim model mạnh nhất trong `routes`, trần ở `cost_cap_usd: 3.0` |
| `researcher` | assistant | nghiên cứu bất kỳ chủ đề nào trên web hoặc trong PDF và viết một khuyến nghị xếp hạng kèm nguồn; không bao giờ chạm vào code |

Một đội phần mềm là một developer chứ không phải một dây chuyền vai trò: mỗi lần chuyển giao tốn một
ngữ cảnh mới chỉ biết những gì brief đã nói, và với một đội cá nhân chủ yếu
code bên lề, ngữ cảnh mất đi tốn nhiều hơn cái song song mua được.

Mỗi manifest trỏ `skills_dirs` tới `../../skills`, nên sáu skill dùng chung được
cài một lần ở đầu thư mục home và mọi vai trò đọc cùng một bản.
Thêm một template hai lần sẽ bị từ chối thay vì ghi đè, vì đến lúc đó profile có thể
là bản sửa của bạn chứ không phải của chúng tôi; `--force` nói rằng bạn cố ý. Agent thêm bằng CLI được đọc
ở lần khởi động kế tiếp; agent thêm qua API cài hoặc tab **Đội** gia nhập đội đang
chạy ngay lập tức.

Danh sách cho phép trong template chính là ý nghĩa của vai trò, và nó cũng chặn cả `delegate`: một
agent work khai tên tool của mình mà không khai `delegate` thì không thể chuyển việc đi, đó là
thứ ngăn một đội mọc thêm tầng thứ hai sau lưng người dẫn đầu.

## Sửa agent từ web/API

Một đội chỉ đổi được bằng cách sửa tệp và khởi động lại là một đội hầu hết mọi người
không bao giờ đổi. Các endpoint này ghi cùng một `agent.yaml` mà một người sẽ viết tay,
và đưa kết quả vào server đang chạy.

```
POST   /api/agents           {"agent_id": "coder", "profile": {…}}
PATCH  /api/agents/{id}      {"profile": {…}}   → {"profile": {…}, "restart_required": […]}
DELETE /api/agents/{id}                         → {"removed": "coder", "kept_at": "…"}
PUT    /api/agents/{id}/files/{name}  {"content": "…"}
GET    /api/agents/{id}/prompt                  → system prompt assembled this turn
POST   /api/agents/reload                       → {"added": ["…"]}
```

**Một patch chỉ nêu những gì nó thay đổi.** Khoá bỏ ngoài giữ nguyên giá trị; muốn xoá một khoá thì
phải nói rõ bằng `null`. Điều này quan trọng vì web gửi từng mục một —
một form gửi cả model của nó sẽ xoá sạch mọi khoá mà form không có ô nhập.

**Tệp giữ nguyên hình dạng.** Ghi là round-trip (ruamel), nên chú thích, thứ tự khoá và
những khoá mà phiên bản server này không biết đều sống sót qua một lần sửa từ
trình duyệt. Manifest được ghi qua tệp tạm rồi chuyển vào chỗ, nên sập
giữa lúc ghi không thể để lại một profile không còn parse được.

**Kiểm tra hợp lệ là cùng đoạn code đọc tệp viết tay**, chạy
*trước* khi ghi bất cứ gì. Profile mà server sẽ từ chối khởi động là 422 và
không đổi gì — không đổi tệp, không đổi agent đang chạy. `delegates` được đối chiếu với
đội như nó sẽ là sau lần sửa, nên bạn không thể trỏ tới một agent không có mặt.

Thứ tự là kiểm tra, rồi nối, rồi ghi. Dựng agent là bước cuối có thể
hỏng trên một profile đã parse sạch, và một tệp ghi trước điểm đó sẽ tuyên bố một
thay đổi mà câu trả lời đã từ chối — rồi áp dụng nó ở lần khởi động lại kế tiếp. Ghi đến sau cùng để
lời từ chối là toàn bộ câu chuyện. Lần ghi hỏng sau khi nối thành công để đội
đi trước tệp trong chốc lát; tệp là thứ boot đọc, nên hướng đó tự sửa lấy.

**Đường dẫn trong một lần sửa phải nằm dưới home của đội.** `workspace`, `skills_dirs` và
`persona_files` được kiểm tra sau khi phân giải, nên `~`, đường dẫn tuyệt đối hoặc đủ `..` để
ra khỏi home là 422. Tệp persona được đọc vào system prompt và đi tới
model ở lượt kế tiếp, còn workspace là phạm vi của mọi tool tệp — không cái nào
nên là thứ mà một request có thể nhắm tới bất cứ đâu trên máy. Kiểm tra này chỉ áp cho
đường sửa này: kit gọi tên markdown của nó bằng đường dẫn tuyệt đối, và `agent add --workspace`
cố ý trỏ một agent tới repo ở nơi khác, cả hai vẫn hoạt động.

**Cả hai danh sách mẫu shell phải là danh sách.** Một chuỗi trần thì duyệt qua được, nên
`shell_ask_patterns: "rm"` nếu không sẽ thành các mẫu `r` và `m` và hàng rào
hỏi trước lệnh phá hoại sẽ âm thầm mất hết ý nghĩa; cùng chuỗi đó
trong `shell_allow_patterns` sẽ cho qua mọi lệnh có chứa chữ `r`. Danh sách rỗng
vẫn tắt danh sách đó, như ghi trong [tools.md](tools.md#shell) — đó là lựa chọn
ai đó có thể đưa ra, còn âm thầm xé nát danh sách thì không.

**Manifest không còn parse được thì được báo, không bị ghi đè** (422, nêu lỗi
parse). Một patch chỉ nêu vài khoá; ghi nó đè lên tệp đã hỏng sẽ làm rơi mọi thứ
khác mà người đó vẫn còn trong đó.

**Xoá vẫn giữ tệp.** `DELETE` chuyển `agents/<id>` sang `agents/.trash/<id>-<stamp>`
và báo nó đã đi đâu; không gì bị xoá. Các cuộc trò chuyện agent đó từng giữ vẫn ở nguyên và
rơi về master. Nó từ chối (409) với master, và với agent mà một agent khác
vẫn nêu tên trong `delegates` — xoá nó sẽ để profile kia không hợp lệ và server
không khởi động được lần sau.

**`restart_required` chỉ bao giờ nói về lịch và Telegram.** Tuyến, tool, persona,
tên, ngân sách và giao việc đều được dựng lại trực tiếp. Đồng hồ và kênh được dựng một lần
lúc boot, nên đổi `schedules`, `memory_consolidate` hoặc `telegram` cần khởi động lại và
nói ra như vậy. Không gì khác cần, và đó là thứ giữ cho thông báo này đáng đọc.

**Agent từ kit là chỉ đọc ở đây** (409, nêu tên tệp markdown chúng đến từ):
profile của chúng sống trong một dự án do người khác bảo trì, và ghi một `agent.yaml` bên cạnh
sẽ che kit chứ không sửa nó.

`PUT …/files/{name}` ghi tệp persona theo tên, và tên được đối chiếu với
`AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md` — đường dẫn không bao giờ đến từ request.

## Agent master

Agent `default` luôn tồn tại và là cài đặt cấp cao nhất: dir = `MY_AGENT_HOME`,
workspace = `MY_AGENT_HOME/workspace`, skills = `MY_AGENT_HOME/skills`, tệp persona và trí nhớ
đọc từ chính `MY_AGENT_HOME`. Vì thế một home mới không cần profile nào cả.
Nó được nạp trước, rồi tới `agents/<id>/agent.yaml` xếp theo id.

Nó cũng là *master*: agent duy nhất mà người dùng nói chuyện — trong web UI và trên
Telegram — và là agent chuyển việc cho những agent còn lại. Một `MY_AGENT_HOME/agent.yaml` tuỳ chọn định hình nó bằng cùng các khoá như mọi
profile (`name`, `description`, `autonomous`, `cost_cap_usd`, `max_steps`, `routes`,
`delegates`, `telegram`, …); không có tệp thì nó là agent default thuần, và
`PATCH /api/agents/default` ghi tệp đó, tạo mới ở lần sửa đầu tiên. Nó không thể
bị xoá. Hai điều khiến nó khác một người dẫn đầu work:

- **Nó với tới mọi người.** Với `delegates` rỗng, master được giao việc cho mọi
  agent khác trong home, theo thứ tự id. Cài
  một agent là đủ để đặt nó dưới quyền master; nêu một danh sách `delegates` thu hẹp
  về các id đã cho. Bất kỳ agent nào khác chỉ với tới những gì nó liệt kê.
- **Nó luôn có `delegate`.** Tool này được nối cho master, cho agent work, và cho
  bất kỳ profile nào có danh sách `delegates`; danh sách cho phép `tools` vẫn chặn được nó.
- **Câu trả lời của con đi thẳng khi lượt chỉ là một lần giao việc.** Nếu master (hay bất kỳ
  agent nào giao việc) chỉ gọi `delegate` một lần trong lượt, không gọi tool nào khác, và agent
  con làm xong, câu trả lời của con — kèm biểu đồ, tệp nó gửi — trở thành câu trả lời của lượt,
  không qua một lần gọi model nữa để kể lại. Tin nhắn chuyển tiếp không ghi provider/model và
  không tính là bước model. Đặt `relay: false` trên lệnh gọi khi còn phải làm tiếp với kết quả;
  con dừng giữa chừng, trả lời rỗng hoặc báo `BLOCKED` thì vẫn về tay agent giao việc.
- **Con được nhắc kết luận trước khi hết bước.** Từ lần gọi model thứ 25 (hoặc một lần trước
  `max_steps` của chính nó, nếu thấp hơn) agent con nhận ghi chú kết luận và không còn tool, để
  thứ trả về là một câu trả lời chứ không phải một mảnh bị trần bước cắt. Ghi chú nằm trong cuộc
  trò chuyện của con. Lượt do người dùng mở giữ tool tới trần cứng như trước.

Mỗi lượt, system prompt của master mang một mục roster: một
dòng cho mỗi agent nó với tới được, gồm id, tên, mode, mô tả và workspace, theo sau là hướng dẫn
khi nào tự làm và khi nào chuyển đi. Agent không với tới ai thì
không có roster. Lượt con mở bởi `delegate` không bao giờ thấy roster, vì nó không thể giao việc.

Các agent assistant của home ví dụ (`pong`, `health-coach`) được với tới cùng một cách
từ điện thoại như từ trình duyệt: bot của master nhận tin và master
giao việc. Lịch của chúng chạy như trước và bản tin của chúng vẫn về chat, dưới
tên của chúng ([channels.md](channels.md#giao-theo-lịch)).

## Tệp persona

Tệp persona là Markdown thuần; vòng lặp nối mỗi tệp thành một mục `## <tên tệp>`
của system prompt, sau khung cố định và trước
các skill. Quy ước đã dùng tốt:

| Tệp | Đặt gì ở đây |
|---|---|
| `AGENTS.md` | cách làm việc: làm gì ở đầu lượt, chạy script nào, viết trí nhớ ra sao |
| `SOUL.md` | giọng điệu, giá trị, những gì agent từ chối |
| `IDENTITY.md` | tên, vai trò, một dòng tự mô tả |
| `USER.md` | góc nhìn riêng của agent này về người dùng: *nó* cần biết gì để làm việc của mình |

`users/owner/USER.md` dùng chung ([memory.md](memory.md)) là tệp mọi agent đều đọc và
là chỗ cho một sự thật chung về người dùng. `USER.md` riêng của agent là tệp
persona: giữ nó ở những gì chỉ agent đó quan tâm, và trỏ tới tệp dùng chung thay vì
sao chép, nếu không hai bản sẽ lệch nhau.

Mỗi mục bị cắt ở 24 000 ký tự; tệp dài hơn bị cắt
kèm dấu `…` ở cuối, nên hãy giữ ngắn và chuyển lịch sử sang [memory](memory.md).
Tệp persona là dữ liệu cá nhân và sống trong `MY_AGENT_HOME`, không bao giờ trong repo này.

## Kit (`.agents/`, `.claude/`, `.opencode/`)

**Kit** là thư mục mà các harness khác giữ cấu hình của chúng: `.claude/` của Claude Code,
`.opencode/` của opencode, `.agents/` liên harness mà Codex và các harness khác đọc.
my-agent-crew đọc cả ba, theo thứ tự đó, nên người
đã có sẵn một kit có thể chép vào và giữ nguyên agent, command, skill và hook của mình:

```
cp -r ~/.claude ~/.my-agent-crew/.agents      # or leave it named .claude, both are read
```

Hai chỗ được tìm, và kit sau che kit trước theo tên:

| Kit | Ở đâu | Mang gì |
|---|---|---|
| home | `MY_AGENT_HOME/.agents` (`.claude`, `.opencode`) | agent, skill, command, hook — cho cả đội |
| agent | `MY_AGENT_HOME/agents/<id>/.agents` | như trên, chỉ cho agent đó |

Kit nằm trong **workspace** của agent không bao giờ được đọc, và `AGENTS.md` ở gốc
workspace cũng vậy. Repository mà agent làm việc trong đó (một cơ sở dữ liệu sức khoẻ, một sổ cái, một codebase) là nguồn
dữ liệu: agent chạy script và đọc tệp của nó, nhưng `.claude/` ở đó thuộc về
người phát triển repository đó, và hook cùng subagent của nó được viết cho một
harness khác. Thứ định hình một agent của đội chỉ là những gì nằm trong `MY_AGENT_HOME`.

Mỗi phần ánh xạ sang gì:

| Trong kit | Ở đây |
|---|---|
| `agents/<id>.md` — front matter `name`, `description`, `tools`, `model`, cộng `mode`, `delegates`, `workspace` của chúng tôi; phần thân là persona | một thành viên đội với id đó (slug của `name`, nếu không thì tên tệp bỏ đuôi). Trí nhớ và workspace của nó sống dưới `MY_AGENT_HOME/agents/<id>/` như mọi agent khác; chỉ persona được đọc từ kit. `model` viết dạng `provider:model` thành `routes` của nó; alias của harness (`sonnet`, `inherit`) nghĩa là tuyến của đội. `agents/<id>/agent.yaml` cùng id sẽ thắng, nên kit không bao giờ thay thế agent cấu hình bằng tay |
| `tools:` trong front matter đó | ánh xạ theo tên: `Bash`→`shell_run`, `Read`→`workspace_read`, `Write`, `Edit`/`MultiEdit`→`workspace_edit`, `Glob`, `Grep`, `LS`→`workspace_list`, `WebFetch`→`fetch_url`, `WebSearch`→`web_search`, `Task`/`Agent`→`delegate`; tên riêng của chúng tôi đi thẳng qua, tên chỉ có ở harness (`TaskCreate`, `NotebookEdit`) bị bỏ. Memory, `skill_read` và `image_read` luôn được giữ. Agent được phép sửa là `mode: work` trừ khi front matter nói khác |
| `commands/**/*.md` (front matter `description`, thân là prompt) | một slash command `/name`, lồng thư mục thành `/dir:name`. `$ARGUMENTS` và `$1`…`$9` được điền từ tin nhắn, nếu không thì đối số được nối vào cuối. Chạy trong web chat và trên Telegram, nơi các lệnh có sẵn (`/new`, `/status`, …) giữ nguyên tên; prompt của master liệt kê chúng |
| `skills/` (hoặc `skill/` của opencode) | thêm một thư mục skill sau thư mục riêng của agent |
| `settings.json` → `hooks.PreToolUse` / `hooks.PostToolUse`, các mục `type: command` | hook tool, xem bên dưới. Các loại hook và sự kiện khác bị bỏ qua |

**Hook** chạy lệnh với cùng JSON trên stdin mà các harness gửi:
`hook_event_name`, `tool_name`, `tool_alias` (tên bên harness, `Bash` cho `shell_run`),
`tool_input`, `agent_id`, `cwd`, và `tool_response` sau lời gọi. Matcher là regex
trên cả hai tên, nên hook viết cho `Bash` sẽ kích hoạt với `shell_run`. Mã thoát 2, hoặc JSON
với `decision: block` / `permissionDecision: deny`, chặn lời gọi và model thấy
lý do; `additionalContext` được nối vào kết quả; mọi thứ khác — thoát 1, hết giờ
(`timeout` giây, mặc định 30), thiếu binary — cho qua, vì hàng rào mà hỏng
thì không được tước tay chân của agent. Lệnh chạy từ thư mục cha của kit với
`CLAUDE_PROJECT_DIR` và `MY_AGENT_PROJECT_DIR` đặt về đó. Job `command` theo lịch đi
qua scheduler, không qua sổ đăng ký tool, nên hook không thấy chúng.

Thẻ đội hiện, theo từng agent, nó mang bao nhiêu command và hook và chúng đến từ gốc kit
nào; `GET /api/agents` trả về `commands`, `hooks` và `kits`.

## Skill

Skill là một tệp Markdown có front matter (`name`, tuỳ chọn `description`, `always`,
`requires`, `cliHelp`), hoặc là `name.md` hoặc là thư mục `name/SKILL.md` mà các tệp anh em
(script, tài liệu tham khảo) được model với tới qua đường dẫn tuyệt đối ghi trong dòng `SKILL_LOCATION`.
Skill nạp từ thư mục builtin (`cite-sources`), rồi `<agent dir>/skills`, rồi
từng mục `skills_dirs`; skill sau cùng tên ghi đè skill trước.
Skill là chỉ dẫn cho model, [tool](tools.md) là hàm nó gọi được.

### Front matter

| Khoá | Ý nghĩa |
|---|---|
| `name` | tên dùng ở mọi nơi; mặc định là tên tệp hoặc thư mục |
| `description` | một dòng hiện trong chỉ mục, để model biết có nên đọc phần thân không |
| `always` | `true` đưa toàn bộ phần thân vào mọi prompt |
| `requires.bins` | chương trình dòng lệnh mà skill điều khiển, `[gws, jq]` hoặc một `jq` đơn |
| `cliHelp` | một lệnh in ra cú pháp thật, ví dụ `gws --help` |

`requires.bins` được đối chiếu với máy lúc nạp. Skill thiếu chương trình
được **giữ**, không bị bỏ: dòng chỉ mục mang `[thiếu: gws]` và phần thân mở đầu bằng một
cảnh báo, nên agent không làm được việc biết vì sao thay vì hỏng giữa chừng.
`cliHelp` được nối vào dòng chỉ mục, và system prompt mang một quy tắc thường trực:
đọc `--help` của lệnh một lần thay vì thử cú pháp thứ ba. Cả hai tồn tại vì một
lần chạy thật đã đốt mười sáu bước đoán cờ cho một chương trình nó chưa từng thấy.

```yaml
---
name: gws-shared
description: Đọc lịch và thư qua CLI gws
requires:
  bins: [gws]
cliHelp: gws --help
---
```

Skill đến được prompt theo một trong ba đường:

- `always: true` — toàn văn của nó đi kèm mọi prompt.
- gắn vào cuộc trò chuyện, từ ngăn cài đặt hoặc danh sách `skills:` của một lịch —
  lại là toàn văn, cho cuộc trò chuyện job mở ra.
- không cái nào — chỉ tên và mô tả hiện dưới `## Kỹ năng có sẵn`, và model
  gọi `skill_read` để kéo phần còn lại khi nó quyết định việc cần đến. Trên 40 skill
  trong chỉ mục thì mô tả bị bỏ để chỉ mục còn lướt được.

Job theo lịch cần skill nên nêu tên skill trong lịch. Nếu không, có một
fallback: prompt viết rõ tên có gạch nối của skill (`gws-shared`) vẫn được gắn
skill đó. Chỉ tên có gạch nối được tính, vì tên một chữ như
`ledger` xuất hiện trong những prompt chẳng liên quan gì đến skill.

### Mẫu hoàn chỉnh: `gws`

`docs/examples/skills/gws/` là một gói CLI trọn vẹn để chép vào một `skills_dirs` rồi điền
vào. Nó bao Gmail, Calendar, Tasks, Sheets, Drive và Docs trong **một** skill thay vì
mười lăm, vì mười lăm dòng chỉ mục đều nói "Google Workspace" bắt model
chọn một thứ nó không chọn tốt được, còn một phần thân đọc một lần mang sẵn cú pháp nó sắp
phải đoán.

Hai thứ trong đó đáng chép lại kể cả cho một chương trình khác.

**Mọi thứ đi qua một wrapper**, `scripts/gws-run.sh`, và không gì gọi binary
trực tiếp. Wrapper làm hai việc và không hơn. Nó từ chối những lời gọi sẽ làm hỏng
thông tin đăng nhập dùng chung của mọi người — `auth login`, mở trình duyệt mà không ai ở đó để
bấm nên treo tới khi run hết giờ, và mọi cố gắng trỏ CLI tới tệp
thông tin đăng nhập khác, triệu chứng của nó là một 401 ở nơi hoàn toàn khác. Rồi nó biến mã thoát khác không
thành một dòng JSON nêu cách sửa, vì model chỉ thấy "exit 1" sẽ thử lại
đúng lệnh đó tới khi hết bước. Dòng đó đi ra **stderr**: stdout của lệnh đọc
được các script dữ liệu pipe vào `jq`, và một object JSON nối vào cuối bảng sự kiện
lịch là lỗi parse, không phải chẩn đoán.

**Hàng rào ghi là `shell_ask_patterns`, không phải văn bản skill.** Phần thân nói "hỏi trước"
là gợi ý model có thể bỏ khi bị ép; danh sách mẫu là cưỡng chế. Các mẫu
khớp hình dạng của một lần ghi — `+send`, `+reply`, `+insert`, `+append`, `+upload`, `+write`,
`tasks insert` — và không bao giờ khớp tên chương trình, vì so khớp là chuỗi con và một `gws` trần
sẽ chặn luôn cả các script bản tin chỉ đọc. Thư đã gửi đáng để ngắt ngay cả khi
agent là `autonomous: true`, và đó chính là trường hợp danh sách này tồn tại.

Mẫu mang `<EMAIL>`, `<SPREADSHEET_ID>` và `<DRIVE_FOLDER_ID>` thay vì giá trị
thật, và một test từ chối gói nếu có một địa chỉ hay một id dài lẫn ký tự
xuất hiện trong đó. Id tài khoản thuộc về bản sao dưới thư mục home của riêng bạn.

### Mẫu thứ hai: `goodreads`

`docs/examples/skills/goodreads/` là cùng hình dạng gói nhưng với một dịch vụ không có API.
Nó thêm hai thứ mà mẫu `gws` không có lý do để cho thấy.

**Gói mang cấu hình của riêng nó.** Script đọc lấy id tài khoản từ
`scripts/goodreads.json` nằm cạnh nó, không từ đối số và không từ môi trường
của agent, nên `shelf --shelf currently-reading` là toàn bộ lệnh và không có id nào
để model ghi sai hay lặp vào log. Gói đi kèm
`goodreads.json.example` và gitignore tệp thật. Skill điều khiển một tài khoản
dễ chép hơn khi tài khoản nằm trong một tệp người chép sửa một lần.

**Lời gọi trả về rỗng là thất bại, không phải câu trả lời rỗng.** Goodreads trả lời
request trang bị chặn bằng 202 và thân rỗng thay vì mã lỗi, nên HTTP
client không ném gì và parser biến sự im lặng đó thành một bản ghi toàn null đọc
y hệt câu trả lời thật. Script kiểm tra thân rỗng và ném lỗi thay vào đó, và
phần thân skill bảo agent báo bị chặn thay vì lách qua. Điều này
đáng chép cho mọi nguồn scrape: thất bại nguy hiểm không phải cái ném lỗi,
mà là cái trả về một object đúng dạng nhưng rỗng ruột.

Nửa ghi đi qua một wrapper, nên khác với `gws`, **chính tên** của wrapper là
hình dạng của một lần ghi và `goodreads-write` là một mục `shell_ask_patterns` đủ dùng. Điều đó
chỉ đúng vì script đọc có tên khác. Kiểm tra nó theo cách kiểm tra hình dạng
của bất kỳ danh sách mẫu nào — chạy các lệnh đọc thật và các lệnh ghi thật
qua `ask_reason` rồi đếm.

## Lịch

Mỗi mục trong `schedules` thành một job `<agent id>/<schedule id>` trong scheduler
(tick 20 s, trường cron đọc theo `timezone` của `config.yaml`, mặc định là múi giờ của máy).

| Khoá | Ý nghĩa |
|---|---|
| `id` | mặc định `job-<index>`; dùng trong tên job và trong `POST /api/jobs/{agent}/{id}/run` |
| `name` | mặc định là id; hiện trong UI |
| `cron` **hoặc** `every` | đúng một trong hai: cron năm trường, hoặc `30m` / `2h` / `1d` |
| `prompt` **hoặc** `command` | đúng một trong hai: prompt mở một cuộc trò chuyện autonomous mới và chạy một lượt; command chạy qua `shell_run` trong workspace và chỉ ghi lại bước đó |
| `enabled` | mặc định `true`. Lịch đang bật có thể tạm dừng và tiếp tục từ thẻ job (`PATCH /api/jobs/{agent}/{id}/state`); công tắc đó lưu trong bảng `job_state` và sống qua khởi động lại. Lịch tắt ở đây chỉ bật lại được bằng cách sửa yaml |
| `skills` | danh sách tên skill gắn toàn văn vào cuộc trò chuyện mà job prompt mở ra; mặc định rỗng, và tên không skill nào cung cấp được ghi log cảnh báo lúc khởi động. Tên skill có gạch nối viết trong `prompt` cũng được gắn |

### Một script mỗi job

Job prompt gom dữ liệu từ nhiều nơi nên gọi **một** script trả về
một khối JSON, chứ không để model điều khiển từng lệnh. Job tự điều phối
tiêu phần lớn ngân sách bước vào cú pháp shell và có thể chạm `max_steps` trước khi viết một
chữ của câu trả lời; script chỉ tốn một bước. Giữ script ngoài repo khi nó
mang id tài khoản hoặc đường dẫn. `docs/examples/job-data-script.sh` là hình mẫu: mọi
lệnh đều được rào để một thất bại ghi lại lỗi và phần dữ liệu còn lại vẫn về.

Cùng lý do, phần chuyên môn của một job prompt (câu truy vấn, tên cột, cách chọn biểu đồ, bố cục
bản tin) nên nằm trong một tài liệu ở workspace mà prompt chỉ trỏ tới và bảo agent đọc bằng
`workspace_read`. Profile nạp một lần lúc khởi động, còn tệp trong workspace được đọc lại mỗi lần
job chạy: sửa tài liệu thì sáng hôm sau có hiệu lực, không cần khởi động lại, và nội dung đi cùng
schema mà nó mô tả thay vì lệch dần với nó. Trong `agent.yaml` chỉ còn cron, lệnh script và vài
dòng prompt.

Cron `memory_consolidate` thành một job cùng hình dạng, `<agent id>/memory-consolidate`,
không có prompt hay command riêng. Nó làm hai việc liên tiếp: viết lại `MEMORY.md`, rồi
biên dịch wiki vault từ chính các ghi chú đó. Việc biên dịch không có cron riêng vì cả hai
nửa đọc cùng ghi chú và vault nên lắng từ cùng một đêm đọc. Mỗi nửa
có run riêng trong Activity, và biên dịch hỏng không làm job hỏng — lúc đó bản viết lại
đã xong rồi, và báo cả job thất bại sẽ khiến ai đó đi tìm
hư hại không có ở đó. Xem [memory.md](memory.md#compile).

Sau một job prompt, scheduler đẩy câu trả lời cuối tới
chat Telegram của master khi có, dưới tên của agent (bản tin sáng về
Telegram; xem [channels.md](channels.md)). Gửi thất bại được ghi log, không bao giờ thử lại.

## Ví dụ

```yaml
name: HLV sức khoẻ
description: Đọc dữ liệu Garmin, gửi bản tin sáng
routes: [openrouter:z-ai/glm-5.3-flash, openrouter:z-ai/glm-5]
workspace: ~/workspace/my-health-coach
skills_dirs: [~/workspace/shared-skills]
autonomous: true
cost_cap_usd: 0.3
telegram:
  token_env: TELEGRAM_BOT_TOKEN
  chat_id: 123456789
schedules:
  - id: morning-brief
    name: Bản tin sáng
    cron: "0 7 * * *"
    prompt: |
      Chạy scripts/health-sync.py --json rồi viết bản tin 4-6 dòng.
      Kèm ảnh bằng dòng `MEDIA: data/charts/sleep.png`.
  - id: backup
    cron: "20 2 * * *"
    command: ./scripts/backup-to-drive.sh
memory_consolidate: "30 3 * * 1"
```

## So với openclaw

openclaw giữ agent trong một tệp cấu hình JSON với override theo từng agent; ở đây mỗi agent là một
thư mục, nên chép một agent là chép một thư mục. Các tệp workspace của openclaw
(`AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md`, `MEMORY.md`, `memory/`) có cùng
tên và vai trò, và đó là cố ý: một workspace openclaw có thể thả vào
`agents/<id>/` và dùng ngay. Không mang sang: tham số model theo từng agent ngoài
danh sách tuyến, các chế độ sandbox, và định danh nhiều người dùng.
