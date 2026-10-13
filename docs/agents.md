# Agent

**Phiên bản**: 0.18.0 · **Cập nhật**: 2026-10-14

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
├── browser/<id>/                   an agent's browser profile (cookies, logins); closed to every file tool
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
        ├── memory/YYYY-MM-DD.md    daily notes, today + yesterday read beside a turn's first message
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
| `description` | chuỗi | `""` | hiện trên card của agent trong tab **Đội** và trong roster của master; nói vai trò và lĩnh vực, còn dịch vụ, kỹ năng, lịch, công cụ và model thì roster [tự kể](#master-được-kể-mỗi-agent-đang-có-gì) |
| `mode` | `assistant` hoặc `work` | `assistant` | `work` thêm các tool lập trình và đổi ba mặc định, xem [Chế độ work](#chế-độ-work) |
| `routes` | danh sách hoặc chuỗi phân cách bằng dấu phẩy dạng `provider:model` | `routes` toàn cục | thử theo thứ tự; tuyến nào hỏng trước khi sinh ra output thì rơi xuống tuyến kế tiếp |
| `escalation_route` | một `provider:model` | trống: tắt | tuyến mà một lượt **bị kẹt** chuyển sang: khi lượt sắp bị dừng vì gọi y hệt một lệnh nhiều lần liên tiếp, hoặc khi mọi tuyến trong `routes` đều hỏng trước khi hiện chữ nào. Phần còn lại của lượt đó chạy trên tuyến này (cùng `reasoning` của agent), lượt sau quay về `routes`. Chỉ đặt cho từng agent: không có khoá toàn cục, không có biến môi trường và không agent nào thừa hưởng của agent khác. Tuyến trùng một tuyến trong `routes`, hay của provider chưa có khoá, không dùng được: lúc khởi động nó bị bỏ qua kèm một dòng cảnh báo trong log, còn lưu từ màn sửa agent thì bị từ chối (422). Sửa có hiệu lực từ lượt kế tiếp, không cần khởi động lại. Xem [Vòng lặp agent](system-architecture.md#23-vòng-lặp-agent) |
| `reasoning` | `minimal`, `low`, `medium` hoặc `high` | trống | model nghĩ kỹ đến đâu, gửi lên OpenRouter thành `reasoning.effort` cho mọi tuyến của agent (kể cả tuyến dự phòng); trống thì để provider tự quyết. Model đang nghĩ thì web hiện "Agent đang suy nghĩ…", số token dùng để nghĩ lưu ở cột `reasoning_tokens` của `messages`, còn nội dung suy nghĩ không lưu. Ollama bỏ qua khoá này |
| `workspace` | đường dẫn | `workspace` | sandbox cho `workspace_*` và `shell_run`; đường dẫn tương đối tính từ thư mục agent, `~` được mở rộng |
| `persona_files` | danh sách tên tệp | `AGENTS.md, SOUL.md, IDENTITY.md, USER.md` | đọc từ thư mục agent vào system prompt mỗi lượt; tệp thiếu thì bỏ qua. Tệp mở đầu bằng front matter thì chỉ phần thân vào prompt; khối mở đầu không đọc được thì cả tệp được đọc nguyên văn (khối có dòng mang dấu hai chấm thứ hai vẫn đọc được, xem [Kit](#kit-agents-claude-opencode)) |
| `persona_names` | chỉ đọc | — | danh sách tên tệp persona thực sự có mặt (trả về bởi `GET /api/agents/{id}` và `GET /api/agents/{id}/prompt`) |
| `skills_dirs` | danh sách đường dẫn | `[]` | thư mục skill bổ sung; `<agent dir>/skills` luôn đứng đầu |
| `cost_cap_usd` | số ≥ 0 | toàn cục | ngân sách mỗi cuộc trò chuyện, `0` = không giới hạn |
| `max_steps` | int ≥ 1 | toàn cục | số lần gọi model tối đa mỗi lượt; lần cuối còn xin gọi tool thì lượt `halted` |
| `autonomous` | bool | `autonomous_default` toàn cục | cuộc trò chuyện mới bỏ qua cổng duyệt tool |
| `shell_ask_patterns` | danh sách chuỗi | toàn cục | lệnh shell vẫn hỏi ngay cả khi autonomous, xem [tools.md](tools.md#shell); khai báo nó sẽ thay thế mặc định, `[]` tắt hàng rào |
| `shell_allow_patterns` | danh sách chuỗi | toàn cục (rỗng) | lệnh shell đủ thường lệ để chạy không cần hỏi ngay cả khi *không* autonomous, xem [tools.md](tools.md#shell). Danh sách hỏi được kiểm tra trước, nên lệnh nằm trong cả hai thì vẫn hỏi |
| `tool_output_chars` | int ≥ 1 | toàn cục | số ký tự của một kết quả tool mà model thấy trước khi bị cắt; tăng lên cho agent có script in báo cáo dài |
| `shell_network` | bool | `true` | `false` chạy mọi lệnh `shell_run` trong một profile `sandbox-exec` của macOS: không mạng theo mọi hướng, không có các helper kiểu `open`/`launchctl`, chỉ ghi được dưới `shell_write_paths` và thư mục tạm (quy tắc ghi này cũng áp dụng khi còn mạng mà `shell_write_paths` được đặt), xem [tools.md](tools.md#shell). Chỉ đặt theo từng agent; `"false"` trong dấu nháy là lỗi khởi động. Viết tay `no`, `off`, `yes`, `on` trần thì bộ đọc lúc khởi động hiểu là đúng/sai: agent lên được, và lần lưu khoá khác từ web giữ nguyên chữ đó ([Sửa agent từ web/API](#sửa-agent-từ-webapi)) |
| `shell_write_paths` | danh sách | `[]` | đường dẫn bên trong workspace mà lệnh `shell_run` được ghi. Đặt danh sách này là bật sandbox kể cả khi còn mạng: lệnh chỉ ghi được ở đây và thư mục tạm, không gọi được `open`/`launchctl`/`osascript` và không kết nối được tới cổng của chính server (API của đội không hỏi đăng nhập), nên agent lấy và ghi dữ liệu được nhưng không sửa được code, script hay cấu hình quanh nó, kể cả hồ sơ của chính nó. Với `shell_network: false` mà danh sách rỗng thì workspace chỉ đọc với shell; đường dẫn ra ngoài workspace là lỗi khởi động |
| `shell_deny_patterns` | danh sách | `[]` | mảnh lệnh (chuỗi con, không phân biệt hoa thường) mà `shell_run` từ chối thẳng, không hỏi duyệt, kèm lời dặn dừng lại và báo cần gì để người dùng quyết. Dùng để giữ agent làm việc trong repo người khác khỏi DDL, SQL ghi tay, `python3 -c`. Rào mềm như `shell_ask_patterns` |
| `write_paths` | danh sách | `[]` | đường dẫn bên trong workspace mà `workspace_write`, `workspace_edit` và `artifact_export` (xuất một canvas ra tệp) được ghi; ghi chỗ khác bị từ chối với lỗi nêu danh sách này, và không thư mục nào được tạo. Rỗng thì ghi được mọi nơi trong workspace. Dùng cho agent autonomous có workspace là một repo, nơi tệp lạc chỗ có thể bị commit lên; đường dẫn ra ngoài workspace là lỗi khởi động. Không ảnh hưởng `shell_run`, xem `shell_write_paths` |
| `script_calls` | `none`, `read_only` hoặc `gated` | `read_only` | agent có được trao `tool_script` không, và script của nó gọi được những tool nào. `none`: agent không được trao `tool_script`, dù nó giữ tool đọc nào và dù một máy chủ MCP có tool cho script gọi; nó không viết script nào trong lượt của mình. Lịch có khoá `script` của nó vẫn chạy, chỉ đọc, vì script đó do chủ viết trong tệp chứ không do agent viết ([Job chạy script](#job-chạy-script)). `read_only`: chỉ tool chỉ đọc. `gated`: thêm cả tool có ghi mà agent đang giữ (`workspace_write`, `shell_run`, tool MCP không nằm trong `read_only`, …); mỗi lời gọi như vậy được cổng duyệt xét **trước khi chạy**, theo đúng luật của một lời gọi trực tiếp, và lời gọi nào cổng phải hỏi người thì script dừng ở đó chứ không chờ ai. Hai tool luôn phải hỏi (`ask_user`, `schedule_create`) vẫn ở ngoài. Agent `gated` còn giữ `delegate` thì script của nó giao việc được cho agent khác (`tools.delegate`), chỉ trong lượt của chính nó: không khi đang làm việc được giao, không trong job. Xem [tools.md](tools.md#gọi-tool-từ-script). Chỉ đọc từ `agent.yaml` của chính agent: không có khoá toàn cục, không có biến môi trường, không agent nào thừa hưởng của agent khác, kể cả của master. Giá trị nào khác ba chữ đó (`Gated`, `"true"`, để trống) là lỗi khởi động, còn lưu qua API thì bị từ chối (422). Một giá trị đúng/sai của YAML cũng vậy, và lỗi nói luôn chữ phải viết: `off`, `no`, `false`, `on`, `yes`, `true` viết trần được YAML đọc thành đúng/sai chứ không thành chữ, nên muốn tắt thì ghi `none` ("script_calls must be none, read_only or gated, not a boolean …: write none to hand the agent no tool_script, or the one of the three meant"). Về mức mặc định bằng cách bỏ khoá hoặc ghi `read_only`. Sửa qua API có hiệu lực không cần khởi động lại, kể cả việc lấy lại và trao lại `tool_script`: từ lượt kế tiếp của agent và từ lần chạy kế tiếp của một lịch, còn lượt hay job đang chạy lúc lưu thì kết thúc như lúc nó bắt đầu ([Sửa agent từ web/API](#sửa-agent-từ-webapi)); sửa tay cần khởi động lại |
| `script_llm` | bool | `true` | script của agent có được tự hỏi model bằng `llm.classify` / `llm.summarise` không ([tools.md](tools.md#gọi-tool-từ-script), bullet "Script tự hỏi model"). `false`: script không hỏi được model nào, trong lượt của agent lẫn trong job `script` của nó; mô tả của `tool_script` không nhắc tới `llm` nữa, và script vẫn gọi `llm.` thì nhận một lỗi bắt được ("không hỏi model được ở đây."), không model nào được gọi và không đồng nào bị tính. Dùng cho agent mà chủ muốn script chỉ là code: lọc, đếm, gọi tool, không có khoản tiền nào nằm ngoài lượt của model. Chỉ đọc từ `agent.yaml` của chính agent, như `script_calls`: không có khoá toàn cục, không có biến môi trường, không thừa hưởng của master. Phải là đúng/sai thật của YAML; `"false"` trong dấu nháy, `0` hay để trống là lỗi khởi động ("script_llm must be true or false"), còn lưu qua API thì bị từ chối (422). Viết tay `off`, `no`, `on`, `yes` trần thì bộ đọc lúc khởi động hiểu là đúng/sai: agent lên được, và lần lưu khoá khác từ web giữ nguyên chữ đó ([Sửa agent từ web/API](#sửa-agent-từ-webapi)); lần lưu tự gửi một chữ (`"off"`) thì vẫn là 422. Sửa qua API có hiệu lực không cần khởi động lại, từ lượt kế tiếp của agent và từ lần chạy kế tiếp của một lịch; lượt hay job đang chạy lúc lưu thì kết thúc như lúc nó bắt đầu. Sửa tay cần khởi động lại |
| `browser` | `off`, `read` hoặc `act` | `off` | agent có được trao tool trình duyệt không ([tools.md](tools.md#trình-duyệt)). `read`: năm tool mở và đọc trang (`browser_navigate`, `browser_snapshot`, `browser_text`, `browser_tabs`, `browser_screenshot`). `act`: thêm `browser_act`, tool bấm và gõ vào trang. Khoá này chỉ có tác dụng trên máy đã bật `browser_enabled` và đã cài trình duyệt (bảng cài đặt toàn cục bên dưới); trên máy chưa bật, agent vẫn khởi động, vẫn trả `browser` như tệp viết, và không được trao tool nào trong số đó. Danh sách `tools` không đem tool nào trong số này tới và cũng không lấy đi tool nào. Chỉ đọc từ `agent.yaml` của chính agent: không có khoá toàn cục cho mức này, không có biến môi trường, không agent nào thừa hưởng của master, nên trình duyệt chỉ bật ở agent mà có người đã ghi như vậy. `off`, `no`, `false` viết trần và khoá để trống đều đọc là `off`. `on`, `yes`, `true` viết trần là lỗi khởi động, vì YAML đọc chúng thành đúng/sai và không nói được là `read` hay `act` ("browser must be off, read or act, not a bare on, yes or true: write read to let it open and read pages, or act to let it click and type as well"); chữ nào khác ba chữ đó cũng là lỗi khởi động, còn lưu qua API thì bị từ chối (422). Sửa qua API có hiệu lực từ lượt kế tiếp của agent, không cần khởi động lại; lần lưu để agent ở `off` còn dừng luôn trình duyệt nó đang chạy, và lượt đang chạy của agent không mở lại được nó (tool `browser_*` của lượt ấy trả một lỗi nói agent đã bị tắt trình duyệt). Sửa tay cần khởi động lại |
| `browser_hosts` | danh sách tên host | `[]` | những host agent tới mà không ai bị hỏi. Mỗi dòng là `shop.example` (đúng host đó) hoặc `*.shop.example` (host đó và mọi host bên dưới nó): chữ thường, không có `https://`, cổng hay đường dẫn; tên có dấu viết ở dạng punycode. Khi danh sách có dòng: `browser_navigate` tới một host trong danh sách chạy không hỏi, kể cả trong cuộc trò chuyện có giám sát, còn tới host ngoài danh sách thì hỏi người, kể cả ở agent tự chủ; `browser_act` trên một trang ngoài danh sách cũng hỏi. Danh sách rỗng thì hai tool hỏi như mọi tool đổi trạng thái: hỏi trong cuộc trò chuyện có giám sát, chạy ở agent tự chủ. Danh sách chặn lời gọi trực tiếp, không chặn nơi trang tự chuyển tới sau một lần bấm ([tools.md](tools.md#trình-duyệt), "Giới hạn đã biết"). Chỉ đọc từ `agent.yaml` của chính agent, như `browser`. Một dòng sai dạng là lỗi khởi động ("browser_hosts must be a list of host names such as shop.example or *.shop.example, in lowercase, with no scheme, port or path"), còn lưu qua API thì bị từ chối (422); `null` hay `[]` xoá danh sách. Sửa qua API có hiệu lực từ lượt kế tiếp; sửa tay cần khởi động lại |
| `schedules` | danh sách | `[]` | job, xem [Lịch](#lịch) |
| `memory_consolidate` | chuỗi cron | không có | theo lịch này, viết lại `MEMORY.md` từ ghi chú ngày rồi biên dịch wiki vault từ chính các ghi chú đó, xem [memory.md](memory.md) |
| `telegram` | map | không có | `token_env` + `chat_id`, tuỳ chọn `approval_ttl_seconds` (60–43200) cho cuộc trò chuyện mở từ chat đó; chỉ đọc trên `agent.yaml` của master, ở nơi khác bị bỏ qua kèm cảnh báo, xem [channels.md](channels.md) |
| `delegates` | danh sách id agent | `[]` | agent mà agent này được giao việc cho; id không trỏ tới agent nào là lỗi khởi động. Rỗng trên master nghĩa là mọi agent khác, xem [Agent master](#agent-master) |
| `tools` | danh sách tên tool | `[]` | khi đặt, là những tool duy nhất agent này có; rỗng nghĩa là mọi thứ mode của nó mang lại. Tên không tool nào mang là một dòng cảnh báo lúc khởi động (`tools lists unknown tool …`), không phải lỗi, nên profile viết cho phiên bản mới hơn vẫn khởi động được. Tên của một tool có thật mà danh sách không đem lại thì cảnh báo nói lý do thay vì gọi nó là lạ: `tool_script`, `tool_search` và tool MCP (`mcp__…`) không do danh sách quyết, chúng đến theo tool agent đang giữ và máy chủ khai ở `mcp`, có tên trong danh sách hay không cũng vậy; `workspace_edit`, `workspace_grep`, `workspace_glob` chỉ agent `mode: work` có; `delegate` ở một agent không giao việc cho ai (không phải master, không phải agent work, không khai `delegates`) thì không được trao. `delegate` ở agent có giao việc không sinh cảnh báo nào: khai tên nó là cách giữ quyền giao việc dưới một danh sách tự chọn. `image_read` trên máy chưa có tuyến đọc ảnh cũng không cảnh báo. Những tên danh sách đem lại được cho agent như nó đang chạy thì server kể ở `listable_tools` ([bảng profile trả về](#sửa-agent-từ-webapi)), xét bằng cùng một chỗ với cảnh báo này, nên trình sửa trên web mời đúng những tên ấy và không tự giữ luật nào. Tool canvas cũng theo danh sách này: agent có `tools:` chỉ dùng được những tool canvas nó liệt kê ([canvas.md](canvas.md#6-bảy-tool-của-agent)) |
| `mcp` | danh sách tên máy chủ MCP | `[]` | những máy chủ khai ở `mcp_servers` của `config.yaml` mà agent này dùng tool. Tool của chúng đến theo danh sách này, không theo `tools` hay `mode`, và hỏi trước khi chạy trừ khi chủ ghi là chỉ đọc. Sửa từ web có hiệu lực ngay; tên không có trong `config.yaml` bị từ chối khi sửa, và chỉ là cảnh báo khi viết tay. Xem [Máy chủ MCP](tools.md#máy-chủ-mcp) |

Mọi giá trị không đặt sẽ rơi về cài đặt toàn cục, lấy từ biến môi trường
và `config.yaml`:

| Biến môi trường | Khoá `config.yaml` | Mặc định |
|---|---|---|
| `MY_AGENT_HOME` | — | `~/.my-agent-crew` |
| `MY_AGENT_ROUTES` | `routes` | `openrouter:deepseek/deepseek-v4-flash` |
| `MY_AGENT_COST_CAP_USD` | `cost_cap_usd` | `0.5` |
| `MY_AGENT_MAX_STEPS` | `max_steps` | `12` |
| `MY_AGENT_AUTONOMOUS` | `autonomous_default` | tắt (`1`, `true`, `yes`, `on` bật lên) |
| `MY_AGENT_APPROVAL_TTL_SECONDS` | `approval_ttl_seconds` | `600`; phải ≥ 1. Yêu cầu duyệt không ai trả lời trong khoảng này bị từ chối và lượt đi tiếp. Một lịch hay khối `telegram` đặt được hạn riêng cho cuộc trò chuyện nó mở (xem [Lịch](#lịch)) |
| `MY_AGENT_SHELL_ASK_PATTERNS` | `shell_ask_patterns` | danh sách trong [tools.md](tools.md#shell); giá trị env phân cách bằng `;` và giá trị rỗng tắt hàng rào |
| `MY_AGENT_SHELL_ALLOW_PATTERNS` | `shell_allow_patterns` | rỗng; phân cách bằng `;` như danh sách hỏi. Mẫu dưới hai ký tự, hoặc mẫu chỉ trông như ký tự đại diện, bị loại thay vì được chấp nhận |
| `MY_AGENT_TOOL_OUTPUT_CHARS` | `tool_output_chars` | `8000`; phải ≥ 1 |
| `MY_AGENT_LANGUAGE` | `language` | `vi` (ngôn ngữ khung prompt; `en` là lựa chọn còn lại) |
| `MY_AGENT_WEB_URL` | `web_url` | rỗng; địa chỉ người dùng mở web (`http://127.0.0.1:8765`), để tin gửi ra kênh viết được link về web. Chỉ nhận `http`/`https`, host, cổng và path trơn; giá trị khác thì hỏng lúc khởi động, xem [deployment-guide.md](deployment-guide.md) |
| `MY_AGENT_TIMEZONE` | `timezone` | múi giờ của máy; một tên IANA (`Asia/Ho_Chi_Minh`) đặt múi giờ mà lịch, "hôm nay" trong prompt và ghi chú trí nhớ, `/status` và thống kê được đọc theo. Tên lạ thì hỏng lúc khởi động |
| `MY_AGENT_OPENROUTER_PROVIDERS` | `openrouter_providers` | rỗng; danh sách (hoặc chuỗi phân cách bằng dấu phẩy) tên provider phía sau OpenRouter (`DeepSeek`, `OpenInference`…) thử theo thứ tự, gửi đi dưới `provider.order`. Ghim một provider để cache prompt không mất mỗi khi OpenRouter đổi bên phục vụ |
| `MY_AGENT_OPENROUTER_PROVIDER_FALLBACKS` | `openrouter_provider_fallbacks` | bật; `false` cấm OpenRouter rơi sang provider ngoài danh sách trên. Không có tác dụng khi danh sách rỗng |
| `MY_AGENT_VISION_ROUTES` | `vision_routes` | `openrouter:google/gemini-2.5-flash-lite, openrouter:qwen/qwen3-vl-8b-instruct`; chuỗi tuyến mà `image_read` gửi ảnh tới, xem [tools.md](tools.md#ảnh). Giá trị rỗng tắt đọc ảnh |
| `MY_AGENT_AUDIO_ROUTES` | `audio_routes` | `openrouter:google/gemini-2.5-flash-lite`; chuỗi tuyến mà voice note trên Telegram được gửi tới để chép lời, xem [channels.md](channels.md). Giá trị rỗng tắt chép lời — kênh sẽ báo cách bật thay vì tải voice về |
| `MY_AGENT_BROWSER_ENABLED` | `browser_enabled` | tắt (`1`, `true`, `yes`, `on` bật lên). Công tắc của cả máy cho tool trình duyệt: khi tắt, không agent nào được trao tool `browser_*`, dù tệp của nó ghi `browser` gì. Bật thôi chưa đủ, mỗi agent còn phải ghi `browser: read` hoặc `act` trong tệp của mình ([agent.yaml](#agentyaml)). Đọc lúc khởi động; xem [tools.md](tools.md#trình-duyệt) |
| `MY_AGENT_BROWSER_CHANNEL` | `browser_channel` | `chromium`, bản Chromium mà gói Playwright ghim và `uv run playwright install chromium` tải về; `chrome` dùng Chrome đã cài sẵn trên máy. Giá trị khác là lỗi khởi động |
| `MY_AGENT_BROWSER_IDLE_MINUTES` | `browser_idle_minutes` | `10`; phải ≥ 1. Trình duyệt của một agent không được gọi tới trong khoảng này thì bị dừng; lần gọi kế tiếp mở lại, vẫn đăng nhập như trước |
| `MY_AGENT_BROWSER_MAX_TABS` | `browser_max_tabs` | `5`; phải ≥ 1. Số tab một agent giữ được cùng lúc, tính trên mọi cuộc trò chuyện của nó |
| `MY_AGENT_BROWSER_ASK_PATTERNS` | `browser_ask_patterns` | danh sách trong [tools.md](tools.md#trình-duyệt) ("mua", "thanh toán", "pay", "delete"…): những từ mà khi nằm trong tên của phần tử sắp bấm thì `browser_act` dừng lại hỏi người, kể cả ở agent tự chủ. Giá trị env phân cách bằng `;`; giá trị rỗng (hay danh sách rỗng trong `config.yaml`) tắt hàng rào này, chỉ khoá vắng hẳn mới rơi về danh sách mặc định |
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

`installed` là những gì đã được ghi, `live` là những gì server đang chạy nạp ngay tại chỗ: master
có thể giao việc cho nó ngay, và lịch khai trong `agent.yaml` của nó lên đồng hồ cùng lúc, không
cần khởi động lại. `needs_restart` chỉ là true khi có một agent đã ghi mà không vào `live`, tức là
khi `force` ghi đè lên tệp của một agent đang chạy: agent đang chạy không được dựng lại ở đây, nên
tệp mới chờ lần khởi động sau. 404 cho template
lạ, 409 khi id đã có người dùng (`force` ghi đè).

**Lần cài bị từ chối để home y như cũ.** Mọi thứ lời gọi nêu đều được kiểm, và home được
đọc như lúc boot, trước khi ghi một tệp nào:

- `template` phải là tên trần của một mẫu đi kèm, còn `agent_id` phải là một mã agent (chữ
  thường, số, gạch ngang). Tên có đường dẫn (`../x`, `a/b`) là 404 với mẫu và 422 với mã;
  `agent add` trên dòng lệnh từ chối y như thế và in lý do.
- Mã của master (`default`) và mã của một agent chạy mà không có `agent.yaml` riêng (agent
  do kit đem tới) là 409 dù có `force`: `force` chỉ ghi đè tệp của chính agent đó.
- Home không đọc được thành một đội (một `agent.yaml` hỏng cú pháp, sai kiểu, hai lịch
  trùng mã, giao việc cho người không có) là 422 nêu đúng tệp.
- `workspace` không thể là một thư mục (trùng một tệp, nằm dưới một tệp) là 422. Workspace
  chưa có thì được tạo; đường dẫn tương đối được tính từ thư mục server đang chạy, nên hãy
  viết tuyệt đối.

Nếu ghi xong mà agent vẫn không vào đội được, thư mục lần cài vừa tạo bị gỡ và mỗi tệp nó
ghi đè trở lại nội dung cũ. Còn lại hai thứ: thư mục `workspace` vừa được tạo cho lời gọi,
và thư mục con rỗng nếu có.

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
GET    /api/agents/{id}/prompt                  → system prompt assembled this turn, and `opening`: the notes read beside a first message
POST   /api/agents/reload                       → {"added": ["…"]}
```

`reload` nhận mọi thư mục vừa chép vào hoặc không nhận ai: một `agent.yaml` hỏng cú pháp hay
sai kiểu, hoặc một workspace không thể là thư mục, là 422 nêu đúng tệp hay đường dẫn, và đội
đang chạy giữ nguyên. Agent được nhận mang theo lịch khai trong tệp của nó: các job ấy lên đồng
hồ ngay, tính từ lúc nhận. Agent đang chạy thì `reload` không đọc lại, nên tệp của nó sửa bằng
tay chưa có hiệu lực ở đây (xem [Lịch](#lịch)).

**Một patch chỉ nêu những gì nó thay đổi.** Khoá bỏ ngoài giữ nguyên giá trị; muốn xoá một khoá thì
phải nói rõ bằng `null`. Điều này quan trọng vì web gửi từng mục một —
một form gửi cả model của nó sẽ xoá sạch mọi khoá mà form không có ô nhập.

**Profile trả về nói hai điều khác nhau về cùng một khoá, và trình sửa chỉ ghi lại điều thứ hai.**
`GET /api/agents`, `GET /api/agents/{id}` và câu trả lời của một lần lưu mô tả agent như nó đang
chạy, kèm khối `declared` là những gì tệp viết:

| Trường | Là gì | `declared.<trường>` |
|---|---|---|
| `tools` | những tool agent đang giữ, không bao giờ rỗng, kể cả những tool không danh sách nào trao (`delegate`, `tool_search`, `tool_script`, tool MCP): là tên trong danh sách đội và trong câu trả lời của một lần lưu, là mô tả đầy đủ từng tool ở `GET /api/agents/{id}` | danh sách cho phép như tệp viết; rỗng khi agent không liệt kê gì |
| `listable_tools` | những tên mà một danh sách `tools:` đem lại được cho agent này như nó đang chạy, xếp theo tên: mọi tool được dựng cho nó trước khi danh sách lọc (theo `mode`; `image_read` chỉ khi máy có tuyến đọc ảnh dùng được), cùng `delegate` khi agent có giao việc (master, agent work, agent khai `delegates`). Không bao giờ có `tool_script`, `tool_search` hay tool MCP, dù agent đang giữ chúng. Không co lại theo danh sách agent đang khai, và đổi ngay trong câu trả lời của lần lưu đổi `mode` hay `delegates`. Tên nằm ở đây thì danh sách nêu nó không nhận dòng cảnh báo nào lúc khởi động; tên không nằm ở đây thì nhận một dòng, trừ `image_read` trên máy chưa có tuyến đọc ảnh (không được kể, cũng không bị cảnh báo) | không có: đây không phải khoá của tệp |
| `delegates` | những agent nó giao việc được lúc này (master không khai ai thì là cả đội) | danh sách tệp viết |
| `browser`, `browser_hosts` | mức trình duyệt và danh sách host của agent, đúng như tệp viết (`off` và `[]` khi tệp không ghi). `browser` là điều agent xin, không phải điều nó đang có: agent ghi `act` trên máy chưa bật `browser_enabled` vẫn trả `act`, còn tool nó thật sự giữ thì đọc ở `tools`, và trình duyệt của nó đang ra sao thì đọc ở `GET /api/agents/{id}/browser` ([tools.md](tools.md#trình-duyệt)) | không có trong `declared`: giá trị ở cột bên đã là điều tệp viết, form đọc thẳng từ đó |
| `schedules` | job đang chạy, kể cả job củng cố bộ nhớ sinh từ `memory_consolidate` | lịch tệp viết, không có job sinh ra |

Form của trình sửa mở từ `declared`. Ghi ngược phần "đang chạy" vào tệp sẽ biến một agent không
có danh sách cho phép thành agent bị chốt ở bộ tool của hôm nay, biến master giao việc cho cả đội
thành master chỉ giao cho đội của hôm nay, và lên lịch job củng cố hai lần.

**Tệp giữ nguyên hình dạng, trừ bên trong khoá mà lần lưu nêu.** Ghi là round-trip (ruamel),
nên thứ tự khoá, những khoá mà phiên bản server này không biết, và chú thích nằm ngoài các khoá
lần lưu nêu đều sống sót qua một lần sửa từ trình duyệt. Khoá được nêu thì được viết lại cả giá
trị: khoá một giá trị (`cost_cap_usd`) giữ chú thích cuối dòng của nó, còn với một danh sách
hay một khối (`schedules`, `tools`, `delegates`), chú thích nằm bên trong
nó mất theo giá trị cũ (chú thích cuối dòng của một khoá con, dòng chú thích đứng trước các
dòng từ thứ hai trở đi, chú thích giữa các khoá), dấu ngoặc người viết tay đặt quanh một chuỗi
cũng vậy, và dòng chú thích đứng ngay sau khối, tức là dòng mở đầu cho khoá kế tiếp, mất theo.
Dòng chú thích đứng trước dòng đầu tiên của danh sách thì còn. Trình sửa trên web gửi lại cả
danh sách `schedules` mỗi khi một dòng lịch đổi, nên tệp có chú thích trong các lịch thì nên
sửa tay. Manifest được ghi qua tệp tạm rồi chuyển vào chỗ, nên sập
giữa lúc ghi không thể để lại một profile không còn parse được. Chuỗi nhiều dòng mà một lần lưu
mang tới (prompt hay script của một lịch) được viết thành khối (`prompt: |`), mỗi dòng một dòng
trong tệp. Chuỗi có ký tự mà khối không chở nguyên vẹn được (tab, `\r`, ký tự không in ra) vẫn
được viết trong ngoặc kép; viết kiểu nào thì lần khởi động sau cũng đọc lại đúng chuỗi đã lưu.
Không dòng nào của tệp bị ngắt cho vừa bề rộng: chuỗi dài nằm trọn trên một dòng, dài bao nhiêu
cũng vậy (một dòng dài mà người viết tay đã tự ngắt sẽ được viết lại liền một dòng ở lần lưu
đầu tiên có khoá đó). Chuỗi một dòng mà bộ đọc lúc khởi động hiểu thành thứ khác (`No`, `on` là
đúng/sai; `1:30` là một số) được viết trong ngoặc kép.

**Tệp sắp ghi được đọc lại trước khi ghi.** Lần lưu viết tệp bằng một thư viện YAML (ruamel),
còn lúc khởi động server đọc bằng thư viện khác (PyYAML), hai bên theo hai phiên bản YAML. Trước
khi ghi hay đổi gì ở agent đang chạy, server đọc tệp sắp ghi bằng đúng bộ đọc của lúc khởi động
và so với tệp hiện có, cũng đọc bằng bộ đó, sau khi đặt các khoá vừa sửa. Khoá nào đọc lại ra
khác thì lần lưu là 422 nêu tên các khoá đó ("Chưa lưu: tệp ghi ra sẽ được đọc lại khác với nội
dung vừa sửa (…)."), tệp và agent đang chạy giữ nguyên. Tệp hiện có mà bộ đọc lúc khởi động không
đọc nổi cũng là 422, kèm lỗi của bộ đọc: sửa thẳng tệp rồi lưu lại. Vì cả hai vế đều do một bộ
đọc đọc, thứ người viết tay mà hai thư viện hiểu khác nhau (`enabled: no`, `max_steps: 010`)
không chặn lần lưu nào; nó vẫn được đọc theo cách của lúc khởi động như trước giờ.

Bản đọc đó cũng là thứ được kiểm tra hợp lệ và nối vào đội đang chạy, chứ không phải bản đọc của thư
viện ghi tệp. Một công tắc người viết tay theo kiểu YAML 1.1 (`script_llm: off`, `shell_network:
no`, cả `on` và `yes`) là đúng/sai với bộ đọc lúc khởi động, nên agent lên được và mọi lần lưu khoá
khác đều đi qua; dòng viết tay giữ nguyên chữ `off` hay `no`. Agent chạy sau một lần lưu là đúng
agent mà lần khởi động sau dựng lên: `max_steps: 010` vẫn là 8, dòng lịch `enabled: no` vẫn tắt, và
một lịch không ai đụng tới giữ nguyên mốc chạy của nó trên đồng hồ. Lần lưu tự gửi một chữ cho
công tắc (`"script_llm": "off"`) thì vẫn là 422: chữ đó sẽ được viết trong ngoặc kép, lần khởi động
sau đọc ra một chuỗi, và một chuỗi không phải là đúng/sai.


**Kiểm tra hợp lệ bắt đầu bằng cùng đoạn code đọc tệp viết tay**, chạy trên bản đọc đó,
*trước* khi ghi bất cứ gì. Profile mà server sẽ từ chối khởi động là 422 và
không đổi gì — không đổi tệp, không đổi agent đang chạy. `delegates` được đối chiếu với
đội như nó sẽ là sau lần sửa, nên bạn không thể trỏ tới một agent không có mặt.

Thứ tự là kiểm tra, rồi dựng, rồi ghi, rồi nối. Dựng agent là bước cuối có thể
hỏng trên một profile đã parse sạch, và một tệp ghi trước điểm đó sẽ tuyên bố một
thay đổi mà câu trả lời đã từ chối — rồi áp dụng nó ở lần khởi động lại kế tiếp. Tệp được ghi
khi agent đã dựng xong và trước khi đội đổi: lần ghi hỏng (đĩa đầy, tệp không thay được) là 422
mang lý do của hệ điều hành, và đội, đồng hồ lẫn công tắc tạm dừng của từng job vẫn như trước
lần lưu. Agent tạo mới mà tệp không ghi được thì không vào đội. Nối trước rồi mới ghi thì một
lần ghi hỏng để lại đội đi trước tệp, và một dòng lịch đã bị bỏ sẽ trở lại ở lần khởi động sau
mà không còn công tắc tạm dừng của nó.

**Với lịch, đường sửa đòi hỏi nhiều hơn lúc boot.** Mỗi lịch mà lần sửa thêm vào hay thay
đổi phải có `cron`/`every` mà đồng hồ đọc được, nếu không là 422. Boot không kiểm
tra điều này: tệp viết tay có `cron` gõ sai vẫn khởi động bình thường, rồi danh sách job
trả 500 và, chừng nào lịch đó còn bật, tick nào của đồng hồ cũng hỏng, kéo theo mọi job khác.
Lịch mà lần sửa không đụng tới thì
không bị kiểm tra lại, nên một tệp viết tay như thế không chặn việc đổi tên, tuyến hay tool.

**Mỗi lịch của một agent đi bằng một mã riêng, lúc boot cũng như lúc sửa.** Hai lịch cùng mã
— viết hai lần, một dòng không ghi `id` (đi bằng chỗ của nó, `job-1`) bên một dòng ghi đúng
mã ấy, hay một dòng lấy tên `memory-consolidate` khi `memory_consolidate` đang bật — thì tệp
bị từ chối bằng một câu nêu tên agent và mã bị trùng: server không khởi động, còn lần lưu từ
web và `POST /api/agents/reload` là 422 với đúng câu đó, kể cả khi lần lưu không đụng tới
lịch. Tệp như thế từng khởi động được, lịch sau âm thầm thay lịch trước; nay phải sửa tệp cho
mỗi lịch một mã rồi mới khởi động. Mã được so như chữ (`7` và `"7"` là một, `Sang` và `sang`
là hai). Hai agent khác nhau cùng một mã lịch thì không sao: đồng hồ gọi job là `<agent>/<mã>`.

**Đường dẫn một lần sửa đưa vào phải nằm dưới home của đội.** `workspace`, `skills_dirs` và
`persona_files` được kiểm tra sau khi phân giải, nên `~`, đường dẫn tuyệt đối hoặc đủ `..` để
ra khỏi home là 422. Tệp persona được đọc vào system prompt và đi tới
model ở lượt kế tiếp, còn workspace là phạm vi của mọi tool tệp — không cái nào
nên là thứ mà một request có thể nhắm tới bất cứ đâu trên máy. Kiểm tra này chỉ áp cho
đường sửa này: kit gọi tên markdown của nó bằng đường dẫn tuyệt đối, và `agent add --workspace`
cố ý trỏ một agent tới repo ở nơi khác, cả hai vẫn hoạt động.

Đường dẫn ngoài home mà agent **đang chạy với** thì không phải của lần sửa: tệp viết tay đã trỏ
tới đó, và một lần lưu để nguyên nó không cho người gọi thêm được gì. Agent như vậy vẫn sửa được
mọi khoá khác qua web và API, và gửi lại đúng đường dẫn ấy cũng được nhận, miễn là viết theo một
trong hai cách nêu ở đoạn dưới. Phép so đi theo từng loại, loại nào so với loại nấy: `workspace`
với workspace đang chạy, từng mục `skills_dirs` với các thư mục skill đang chạy, từng tệp
persona với các tệp persona đang chạy. Một workspace ngoài home không làm thư mục ấy thành thư
mục skill được nhận, cũng không làm tệp nằm dưới nó thành tệp persona được nhận. Đổi một
workspace ngoài home sang chỗ khác ngoài home (kể cả thư mục cha hay thư mục con của nó) là 422;
đổi vào trong home thì được, và sau đó không đổi ngược ra được nữa. Agent mới tạo chưa chạy với
gì, nên mọi đường dẫn của nó phải nằm dưới home, kể cả khi một agent khác đang làm việc ở chính
chỗ đó. Phép so lấy agent đang chạy, không lấy tệp: đường dẫn ngoài home vừa viết tay vào tệp mà
chưa khởi động lại thì chưa được tính, lần lưu qua web lúc đó bị từ chối kèm đường dẫn ấy.

**Đường dẫn ngoài home được viết như tệp đang viết, hoặc viết chính đường dẫn thật.** Tệp giữ nguyên
chuỗi mà lần sửa gửi lên, và mỗi lần khởi động lại đi theo chuỗi ấy từ đầu. Một chuỗi tới được cây
của agent qua một liên kết (symlink), hoặc bằng cách vào một thư mục rồi lùi ra bằng `..`, chỉ dẫn
tới đó chừng nào liên kết hay thư mục ấy còn nằm yên, mà agent có shell thì dời được cả hai: lần
khởi động sau sẽ theo chuỗi đã lưu tới một chỗ chưa lần sửa nào được xét. Vì vậy với một đường dẫn
ngoài home, lần sửa chỉ gửi được một trong hai cách viết: đúng chuỗi tệp đang ghi cho cùng loại
đường dẫn (chữ của chủ, lần lưu không ghi gì mới), hoặc chính đường dẫn thật, không còn liên kết hay
`..` nào để theo. Cách viết khác là 422, và câu lỗi nêu đường dẫn nên ghi ("Đường dẫn … đi qua liên
kết hoặc ..; hãy ghi đường dẫn thật: …"); server không tự viết lại hộ, tệp và agent đang chạy giữ
nguyên. Tệp viết tay đã ghi sẵn một cách viết vòng thì vẫn lưu được mọi khoá khác, gửi lại đúng
chuỗi ấy cũng được, và đổi nó sang đường dẫn thật cũng được. Loại nào xét theo loại nấy, như ở đoạn
trên: chuỗi tệp ghi cho workspace không bảo lãnh cho một thư mục skill viết y như thế. Bỏ hẳn một
khoá cũng được xét như vậy, theo cái tên mà lúc khởi động đọc thay vào (`workspace` cho workspace,
`AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md` cho tệp persona): tên ấy là một liên kết ra ngoài
home thì lần bỏ khoá là 422. Ghi chính cái tên ấy vào tệp thì được, vì lúc khởi động đằng nào cũng
theo nó; thư mục `skills` của agent cũng thế, nó được đọc dù tệp ghi gì. Đường dẫn nằm trong home
thì xét như trước, viết cách nào cũng được.

**Nằm trong home là xét cả chuỗi lẫn chỗ nó dẫn tới.** Một đường dẫn chỉ được coi là trong home
khi cả hai đều nằm trong home: chuỗi đã gửi, đọc mà không theo liên kết nào (`~` thành thư mục
của người dùng, chuỗi tương đối nối vào thư mục agent, `.` và `..` gộp theo chữ), và đường dẫn
thật nó dẫn tới. Chỉ xét chỗ dẫn tới thì chưa đủ: một liên kết nằm trong một cây ngoài home mà
hôm nay dẫn vào home thì ai làm việc trong cây ấy cũng trỏ nó đi chỗ khác được, và agent theo nó
tới đó (tệp persona được đọc lại mỗi lượt, không cần khởi động lại). Chuỗi như vậy đi qua đúng
luật của đường dẫn ngoài home ở đoạn trên: 422 nêu đường dẫn thật trong home nên ghi, trừ khi
tệp đã ghi sẵn chuỗi ấy cho cùng loại đường dẫn. Home ở đây là chỗ tên của nó dẫn tới lúc server
khởi động: `MY_AGENT_HOME` đặt qua một liên kết (`/tmp/…` trên macOS) thì chuỗi tuyệt đối đi qua
liên kết ấy cũng là 422 nêu đường dẫn thật, còn chuỗi tương đối từ thư mục agent thì không đổi.

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
và báo nó đã đi đâu; không tệp nào của agent bị xoá. Thứ nằm trong database thì khác: những gì
script của nó giữ lại, lịch nó được tạo từ chat và công tắc bật/tắt của từng job bị xoá hẳn
(hai đoạn dưới và [tools.md](tools.md)), và hộp xoá trên web nói điều đó trước khi người dùng
gõ id. Các cuộc trò chuyện agent đó từng giữ vẫn ở nguyên và rơi về master. Nó từ chối (409) với master, và với agent mà một agent khác
vẫn nêu tên trong `delegates` — xoá nó sẽ để profile kia không hợp lệ và server
không khởi động được lần sau.

**Lịch của agent bị xoá đi cùng nó, ngay lúc xoá.** Job khai trong `agent.yaml` của nó rời đồng
hồ, lịch nó được tạo từ chat (bảng `created_schedules`) và công tắc bật/tắt của từng job của nó
(bảng `job_state`) bị xoá khỏi database; lịch sử run giữ nguyên. Agent tạo sau này dưới cùng id
không nhận lại job nào trong đó. Job đến giờ mà agent của nó không còn trong đội thì bị bỏ qua
kèm một dòng log, các job khác của nhịp ấy vẫn chạy.

**`restart_required` luôn là danh sách rỗng.** Mọi thứ một lần lưu đổi đều vào đội đang chạy
ngay: tuyến, tool, persona, tên, ngân sách, giao việc và cả khối `telegram` được dựng lại trực
tiếp (bot được dựng lại ngay khi lưu), còn `schedules` và `memory_consolidate` được đồng hồ đọc
lại ngay trong lần lưu đó, theo các quy tắc ở [Lịch](#lịch). Lịch từng là thứ duy nhất chờ khởi
động lại, và nay không còn chờ nữa. Khoá này được giữ trong câu trả lời của `POST /api/agents`
và `PATCH /api/agents/{id}` cho những client vẫn đọc nó; nó không còn mang câu nào.

**Lần lưu có hiệu lực từ lượt kế tiếp.** Lần lưu không sửa agent đang chạy: nó đặt một agent dựng
lại vào chỗ agent cũ trong đội. Một lượt nhận agent của nó một lần, lúc bắt đầu, và đồng hồ nhận
agent mỗi lần một job chạy. Vì vậy điều vừa lưu (tool, tuyến, `script_calls`, `script_llm`, …) có
hiệu lực từ lượt kế tiếp của agent và từ lần chạy kế tiếp của một lịch, còn lượt hay job đang chạy
lúc lưu thì kết thúc như lúc nó bắt đầu: nó vẫn giữ `tool_script` mà lần lưu vừa lấy lại, và script
của nó vẫn hỏi được model mà lần lưu vừa tắt. Cổng duyệt không vì thế mà hở: mỗi lời gọi ghi của
lượt ấy vẫn được xét như trước lần lưu. Lượt đang dừng chờ duyệt hay chờ trả lời thì khác: nó nhận
lại agent lúc được tiếp tục, nên đi tiếp với agent như đã lưu.
Model nó hỏi tiếp và workspace nó ghi vào là của lần lưu, và một lời gọi đã xin duyệt mà lần lưu
vừa lấy lại tool của nó thì không chạy dù được đồng ý.

**Agent từ kit là chỉ đọc ở đây** (409, nêu tên tệp markdown chúng đến từ):
profile của chúng sống trong một dự án do người khác bảo trì, và ghi một `agent.yaml` bên cạnh
sẽ che kit chứ không sửa nó.

`PUT …/files/{name}` ghi tệp persona theo tên, và tên được đối chiếu với
`AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md` — đường dẫn không bao giờ đến từ request.

### Trình sửa trên web

Trình sửa agent trong màn quản lý (`#/manage/crew/<agent id>`) là một form trên các endpoint ở trên:
nó mở từ `declared`, gửi những khoá đã đổi, và hiện lời từ chối của server nguyên văn ở đầu form
("Không lưu được: …") mà không làm mất gì người sửa đã gõ. Dưới đây là những gì form tự làm thêm.

**Mục "Script"** nằm cuối phần Công cụ, sau các máy chủ MCP, và ghi hai khoá của `agent.yaml`:

- "Script gọi được gì" là `script_calls`, một trong ba: "Không dùng script" (`none`), "Chỉ công cụ
  đọc" (`read_only`), "Cả công cụ thay đổi dữ liệu" (`gated`). Dưới ô chọn là một dòng nói lựa chọn
  đang chọn dẫn tới gì.
- "Cho script hỏi mô hình" là `script_llm`. Ô này vẫn bật tắt được ở agent đặt "Không dùng script":
  script của một lịch vẫn chạy ở agent ấy.

Agent mà tệp không ghi hai khoá này mở ra ở giá trị nó đang chạy, "Chỉ công cụ đọc" và có đánh dấu.
Lưu một trong hai chỉ gửi đúng khoá đã đổi và không đòi khởi động lại; như mọi lần lưu, nó có hiệu
lực từ lượt kế tiếp (đoạn "Lần lưu có hiệu lực từ lượt kế tiếp" ở trên), và mục này nói điều đó ngay
dưới tiêu đề. Chọn rồi chọn lại như cũ thì không còn gì để lưu.

Khi form đang có cả "Cả công cụ thay đổi dữ liệu" lẫn ô "Tự chủ" được đánh dấu, dòng dưới ô chọn
được thay bằng lời cảnh báo "Agent này đang tự chủ nên script của nó thay đổi dữ liệu mà không ai
được hỏi. Chỉ lệnh khớp mục “Lệnh vẫn phải hỏi” mới làm script dừng lại.", và đúng câu ấy hiện thêm
ngay dưới ô "Tự chủ" ở phần Nhận dạng, đầu form: bật ô nào sau thì người sửa cũng đọc được nó ở chỗ
vừa bấm. Lời cảnh báo xét theo form đang hiện, chưa cần lưu, và hiện cả ở agent mà form không sửa
được (agent từ kit).

Cuối mục là liên kết "Xem những gì script của agent này giữ lại", mở màn "Script giữ lại" với đúng
agent đó ([tools.md](tools.md#gọi-tool-từ-script), bullet "Trên web").

**Mục "Trình duyệt"** đứng ngay sau mục Script và ghi hai khoá của `agent.yaml`; các tool và các rào
ở [tools.md](tools.md#trình-duyệt):

- "Mức dùng trình duyệt" là `browser`, một trong ba: "Tắt" (`off`), "Đọc" (`read`), "Thao tác"
  (`act`). Dưới ô chọn là một dòng nói mức đang chọn đem tới tool nào và lời gọi nào phải hỏi.
- "Máy chủ mở không cần hỏi" là `browser_hosts`, mỗi dòng một host (`shop.example`,
  `*.shop.example`). Ô này hiện khi mức khác "Tắt". Đặt về "Tắt" thì danh sách vẫn nằm trong form
  như cũ, nên chọn lại một mức là gặp lại nó.

Form đọc ô host theo từng dòng: bỏ khoảng trắng hai đầu, viết thường, bỏ dòng trống. Dòng không phải
tên host (một địa chỉ dán vào, có `https://`, cổng hay đường dẫn) được nêu tên ngay dưới ô, "«…»
không phải tên máy chủ: bỏ https://, cổng và đường dẫn.", và lần lưu bị giữ lại cho tới khi dòng ấy
được sửa. Form chỉ xét danh sách khi người sửa đã đổi nó, theo đúng luật của server; ô vẫn hiện
chừng nào còn một dòng bị nêu, dù mức đang là gì.

Chọn "Đọc" hay "Thao tác" trên máy không trao được trình duyệt thì dưới dòng gợi ý có thêm một lời
cảnh báo: máy đang tắt trình duyệt (`browser_enabled` trong `config.yaml`), hoặc máy chưa cài trình
duyệt (xem mục Kết nối). Công tắc của máy được nêu trước, vì khi nó tắt thì đã cài hay chưa không
đổi gì. Lời cảnh báo không giữ lần lưu: khoá vẫn được ghi và có tác dụng khi máy được bật.

Như mọi lần lưu, hai khoá có hiệu lực từ lượt kế tiếp, không cần khởi động lại; lần lưu đưa agent về
"Tắt" thì trình duyệt đang chạy của nó dừng ngay, và lượt đang chạy lúc đó không mở lại được.
Sáu tool `browser_*` không có ô chọn trong danh sách công cụ, và dưới danh sách có một dòng nói
vì sao: chúng đi kèm mục này, không kèm `tools:`.

**Thẻ "Trình duyệt"** nằm dưới phần Công cụ, ngoài form: nó không lưu gì mà tác động ngay lên trình
duyệt đang chạy. Thẻ hiện ở agent có mức khác "Tắt", và ở agent đã về "Tắt" mà trình duyệt cũ còn
chạy.

- Dòng trạng thái nói một trong bốn điều, theo thứ tự này: "Đang chạy · N tab" (kèm "đang làm việc"
  hay "rảnh N giây"), máy đang tắt trình duyệt, máy chưa cài trình duyệt, hoặc "Chưa chạy. Trình
  duyệt tự mở khi agent gọi một công cụ trình duyệt, và tự tắt sau một lúc không dùng."
- Mỗi tab là một dòng: nhãn agent đặt, tiêu đề trang (hoặc "(chưa có tiêu đề)"), host (hoặc "(trang
  trống)"), không bao giờ là địa chỉ đầy đủ; rồi "Mở cuộc trò chuyện" dẫn tới cuộc đã mở tab, hoặc
  "Việc theo lịch" ở tab của một lượt chạy theo lịch; rồi "đang dùng" hay "rảnh N giây".
- "Đóng tab" đóng một tab, "Dừng trình duyệt" tắt cả trình duyệt, kể cả khi một lời gọi đang dùng
  nó. Không nút nào hỏi lại: đăng nhập vẫn được giữ, và lời gọi kế tiếp của agent mở lại trình
  duyệt. Trong lúc một yêu cầu đang đi, mọi nút của thẻ chờ. Tab đã mất trước khi bấm thì thẻ nêu
  câu của server và đọc lại danh sách.
- Thẻ tự đọc lại mỗi 5 giây khi trang đang được xem, và đọc ngay khi trang được xem lại; trang bị
  che thì không hỏi gì.

**Danh sách công cụ đọc `listable_tools`.** Dưới "Chỉ dùng các công cụ được chọn", mỗi tên trong
`listable_tools` của agent là một dòng, kèm mô tả của tool khi bảng công cụ có nó; form không giữ
luật riêng nào về việc một danh sách `tools:` có tác dụng với tên nào. Vì vậy không có dòng cho tool
MCP, `tool_search`, `tool_script` hay các tool `browser_*`, còn `delegate` có dòng ở agent có giao
việc, kể cả lúc không agent nào còn giữ nó, để đánh dấu lại được.

- Agent không viết danh sách mở ở "Dùng tất cả công cụ hợp lệ". Bật danh sách lên thì nó bắt đầu từ
  những tool agent đang giữ trong số các dòng ấy, theo thứ tự các dòng; agent không giữ dòng nào thì
  bắt đầu từ mọi dòng. Ở agent đã viết danh sách, sang "Dùng tất cả công cụ hợp lệ" rồi quay lại thì
  danh sách trở về đúng như tệp viết.
- Tên mà danh sách của tệp có nhưng `listable_tools` không kể (tool của chế độ khác, tool máy không
  chạy được lúc này, tool được trao bất kể danh sách) có một dòng riêng đã đánh dấu, đứng sau các
  dòng kia, kèm câu "Hiện giờ danh sách không đem lại công cụ này cho agent. Bỏ chọn thì tên này rời
  khỏi danh sách." Tên ấy được ghi lại cùng danh sách cho tới khi người sửa bỏ chọn nó; đánh dấu một
  dòng khác không làm nó rơi. Tệp viết một tên hai lần thì có một dòng, bỏ chọn là cả hai cùng đi.
- Bỏ chọn một tool rồi đánh dấu lại thì tên về đúng chỗ danh sách của tệp đang viết nó, nên không
  còn gì để lưu. Tên mà danh sách của tệp chưa từng có được ghi sau các tên của tệp, theo thứ tự các
  dòng, bất kể dòng nào được đánh dấu trước.
- Các dòng theo agent như đã lưu. Khi form còn một thay đổi chưa lưu ở "Chế độ" hay "Có thể giao
  việc cho", dưới danh sách có dòng nhắc lưu thay đổi đó trước: câu trả lời của lần lưu ấy mang
  `listable_tools` mới.
- Lần lưu không đổi gì ở danh sách thì không gửi `tools`.
- Bỏ chọn một dòng mà dòng ấy đi luôn (một tên như ở gạch đầu dòng thứ hai, hay một máy chủ MCP mà
  `config.yaml` không còn khai) trong lúc bàn phím đang ở đó thì bàn phím sang dòng thế chỗ nó,
  không có thì sang dòng cuối còn lại, không còn dòng nào thì sang ô đang bật trong hai ô "Dùng tất
  cả công cụ hợp lệ" / "Chỉ dùng các công cụ được chọn".
- Server chưa trả `listable_tools` (bản trước, xem đoạn cuối phần này) thì các dòng là những tool mà
  bảng công cụ không đánh dấu là của một máy chủ MCP, là `tool_search` hay là `tool_script`. Danh
  sách bật lên vẫn bắt đầu từ danh sách của tệp, tệp không viết thì từ những tool agent đang giữ
  trong số các dòng ấy, không giữ dòng nào thì từ mọi dòng.

**Lịch: một dòng làm một trong ba việc.** Ở mỗi dòng lịch, "Làm gì" chọn một trong "Nhắc agent"
(`prompt`), "Lệnh shell" (`command`) và "Script" (`script`); dòng do "+ Thêm lịch" tạo bắt đầu là
một lời nhắc. Dòng script có thêm ô "Nhắc agent khi script in ra kết quả" (`then_prompt`), không bắt
buộc: để trống thì khoá không nằm trong tệp, và xoá trắng một ô đã có chữ thì khoá được lấy ra khỏi
tệp. Ô chọn kỹ năng hiện ở dòng mở ra một lượt: dòng nhắc agent, và dòng script đã có `then_prompt`
hoặc đã có `skills`.

Đổi "Làm gì" không mang chữ của việc này sang ô của việc kia. Chừng nào dòng còn trên trang, mỗi
việc giữ phần của nó (chữ đã gõ, `then_prompt`, `skills`) và nhận lại khi được chọn lại, nên bấm
nhầm thì bấm lại là xong; lúc lưu chỉ việc đang chọn được ghi. Dòng lệnh shell mà tệp có ghi
`skills` giữ đúng danh sách ấy qua các lần sửa, kể cả sau một vòng sang lời nhắc rồi quay lại.

Script được gõ trong một ô nhiều dòng, và form gửi nó đúng từng ký tự, không thêm dấu xuống dòng
cuối. Phím Tab chuyển sang ô kế tiếp nên thụt lề bằng dấu cách; dấu tab dán vào thì được giữ nguyên.
Form tự chặn hai điều trước khi gửi: script trống ("Nhập script cần chạy.", nêu ra khi đã thử lưu)
và script dài quá 20.000 ký tự (nêu ngay khi vượt, đếm theo ký tự như server đếm). Form **không** tự
xét cú pháp Python: server xét khi lưu, và lời từ chối 422 của nó hiện nguyên văn ở đầu form, những
gì đã gõ vẫn còn đó để sửa.

**Dòng script phải có mã.** Những gì script giữ bằng `store` nằm dưới `job:<schedule id>`, và dòng
không có `id` trong tệp được đánh số theo vị trí ở mỗi lần khởi động (`job-<index>`): thêm hay bớt
một lịch phía trên là job đọc sang chỗ của dòng khác. Vì vậy form không lưu một dòng script mà ô
"Mã" còn trống (chỉ có dấu cách cũng là trống), dù dòng ấy mới thêm hay vừa được đổi từ lời nhắc hay
lệnh sang. Lần lưu bị giữ lại, và khi đã thử lưu thì ô "Mã" nêu lý do: "Nhập mã cho lịch này: những
gì script giữ lại được lưu theo mã, còn mã bỏ trống thì đổi theo vị trí của lịch trong danh sách."
Dòng gợi ý dưới ô "Mã" của một dòng script cũng nói mã dùng để làm gì, thay cho "Bỏ trống để tự
đặt". Form không tự đặt mã hộ, và dòng của hai loại kia vẫn để trống mã được như trước.

Dòng script mà server đã đánh số (`job-2`) mở ra với mã ấy trong ô, nên mở agent không tính là có
thay đổi và không ai phải gõ gì. Lần lưu kế tiếp có gửi `schedules` gửi lại mã ấy, từ đó tệp ghi nó,
và dòng giữ mã dù các dòng phía trên bị xoá.

**Từ danh sách lịch tới đúng dòng.** Nút "Sửa lịch" của một job trong màn Lịch chạy mở trình sửa của
agent đó ở dòng của chính lịch ấy (ví dụ `#/manage/crew/coach/schedules?job=coach%2Fmorning-brief`):
dòng được cuộn vào tầm nhìn, ngay dưới thanh dính của trình sửa, và nhận bàn phím. Job không có dòng
nào trong form (job gom ghi nhớ `memory-consolidate`, sinh từ `memory_consolidate`) thì dừng ở tiêu
đề phần Lịch chạy. Liên kết quay lại khi đó ghi "← Lịch chạy" và trở về đúng dòng của job trong danh
sách.

**Giữa bundle mới và lần khởi động lại.** Server đọc bundle của web từ đĩa ở mỗi lần tải trang, nên
sau khi cập nhật mã mà chưa khởi động lại, trang mới nói chuyện với server của bản trước. Server
0.15.0 trả `script_calls` nhưng chưa trả `script_llm` và `listable_tools`. Trình sửa vẫn mở được
trên một server như thế: khoá nào vắng trong câu trả lời thì form đọc như mặc định (`script_calls`
là "Chỉ công cụ đọc", `script_llm` là có đánh dấu), và danh sách công cụ rơi về bảng công cụ như nêu
ở trên. Màn "Script giữ lại" trong khoảng ấy thì có giới hạn riêng
([tools.md](tools.md#gọi-tool-từ-script), bullet "Trên web").

Server trước 0.18.0 không trả khoá `browser` và sẽ từ chối một lần lưu có nó. Trên server như thế
web không vẽ gì của trình duyệt: trình sửa không có mục "Trình duyệt", không có thẻ, không có dòng
dưới danh sách công cụ, và lần lưu không gửi `browser` hay `browser_hosts`; mục Kết nối không có thẻ
"Trình duyệt"; bảng công cụ không có nhãn nào.

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
  không tính là bước model. Đặt `relay: false` trên lệnh gọi khi còn phải làm tiếp với kết quả.
  Chỉ việc đi tới `done` mới đi thẳng: con dừng giữa chừng, bị từ chối duyệt, trả lời rỗng hoặc
  khai `Status:` khác `DONE` (thiếu thông tin, bị chặn, xong mà còn lưu ý) thì kết quả, với dòng
  `outcome=` và lý do, về tay agent giao việc để nó kể lại cho đúng ([tools.md](tools.md#giao-việc)).
- **Con được nhắc kết luận trước khi hết bước.** Từ lần gọi model thứ 25 (hoặc một lần trước
  `max_steps` của chính nó, nếu thấp hơn) agent con nhận ghi chú kết luận và không còn tool, để
  thứ trả về là một câu trả lời chứ không phải một mảnh bị trần bước cắt. Ghi chú nằm trong cuộc
  trò chuyện của con. Lượt do người dùng mở giữ tool tới trần cứng như trước.

Mỗi lượt, system prompt của master mang một mục roster ("Đội của bạn"): hướng dẫn khi nào tự
làm và khi nào chuyển đi, rồi một dòng cho mỗi agent nó với tới được, gồm id, tên, mode và mô
tả. Agent không với tới ai thì không có roster. Lượt con mở bởi `delegate` không bao giờ thấy
roster, vì nó không thể giao việc.

### Master được kể mỗi agent đang có gì

Dòng mô tả là thứ chủ viết tay, nên nó chỉ đúng chừng nào còn có người nhớ sửa. Vì thế dưới
dòng của mỗi agent, roster có thêm các dòng thụt vào do hệ thống tự đọc từ đội đang chạy, mỗi
lần lắp system prompt (tức là trước mỗi lần gọi model, không lưu lại ở đâu):

```text
- pong — Pong (assistant): thư ký riêng, lo lịch, thư và sách
  · Dịch vụ ngoài (MCP): notion (đọc và ghi) — Sổ ghi chú của người dùng
  · Kỹ năng: như của bạn, thêm: goodreads (Tra sách trên Goodreads), gws (Lịch và thư Google)
  · Việc tự chạy theo lịch: Bản tin sáng, Tổng kết tuần
  · Công cụ: như của bạn, thêm: tool_search
  · Mô hình: deepseek-v4-flash; khi bí thì tự chuyển sang deepseek-v4-pro
```

| Dòng | Đọc từ đâu | Ghi chú |
|---|---|---|
| Dịch vụ ngoài (MCP) | khoá `mcp` của agent, đối chiếu với tool MCP nó đang cầm và trạng thái kết nối | xem bảng dưới |
| Kỹ năng | các skill agent nạp được | skill master không có thì kèm mô tả, cắt còn 80 ký tự; skill cần một lệnh máy này không có thì mang `[thiếu: …]` đứng trước mô tả, như trong mục lục skill của chính agent đó |
| Việc tự chạy theo lịch | job của agent trong bộ lập lịch, cả job khai trong `agent.yaml` lẫn job tạo từ chat | chỉ job đang bật; bỏ job gom trí nhớ, vì agent nào cũng có |
| Công cụ | tool trong hộp đồ của agent | bỏ `delegate` (lượt được giao việc không bao giờ cầm nó) và tool MCP (đã có dòng dịch vụ); `tool_search`, `tool_script` và các tool `browser_*` được kể như mọi tool khác, nên master biết agent nào mở được trang web; agent có `script_calls: gated` thì dòng có thêm một câu ở cuối, xem dưới |
| Mô hình | tuyến đầu trong `routes` | kèm model của `escalation_route` khi tuyến đó dùng được |

Một máy chủ MCP được kể theo đúng thứ agent với tới lúc đó. Trạng thái kết nối được xét trước,
rồi mới tới các tool agent đang cầm:

| Tình trạng | Roster nói |
|---|---|
| chờ đăng nhập OAuth, kể cả khi phiên đăng nhập hết hạn giữa chừng | `chưa dùng được: người dùng cần đăng nhập ở trang Máy chủ MCP` |
| không nối được: chưa nối lần nào, máy chủ rớt, hay khoá riêng bị từ chối | `chưa kết nối được lúc này` |
| nối được, agent cầm ít nhất một tool mà cả chủ lẫn máy chủ đều không nói là chỉ đọc | `đọc và ghi` |
| nối được, mọi tool agent cầm đều được chủ (`read_only`) hoặc máy chủ (`readOnlyHint`) nói là chỉ đọc | `chỉ đọc` |
| nối được nhưng mọi tool đều `hidden` | không kể, vì không có gì để giao việc |
| agent nêu tên một máy chủ không có trong `mcp_servers` | không kể |

Xét kết nối trước là vì một phiên đăng nhập hết hạn hay một khoá bị từ chối không lấy lại tool
khỏi hộp đồ của agent: agent vẫn cầm đủ tool mà không gọi được cái nào, và nếu chỉ nhìn tool thì
roster sẽ kể máy chủ ấy là `đọc và ghi` cho tới khi có người đăng nhập lại. Còn `readOnlyHint`
của máy chủ chỉ đổi câu kể, không đổi việc duyệt: tool nào chủ không đưa vào `read_only` thì vẫn
hỏi trước khi chạy.

Tên kỹ năng và tên công cụ được kể so với của chính master ("như của bạn", "thêm: …", "không có:
…") khi số tên khác nhau không quá một nửa số tên phải kể; khác nhiều hơn thì kể cả danh sách.
Loại nào agent không có thì không có dòng. `tool_script` có ở mọi agent giữ ít nhất một tool chỉ
đọc ([tools.md](tools.md#gọi-tool-từ-script)), nên thường nó nằm trong "như của bạn"; tên nó chỉ
hiện ra khi master và agent khác nhau ở đúng điểm đó, ví dụ một master chỉ còn tool ghi đọc thấy
`thêm: …, tool_script` ở agent còn đọc được, hoặc `như của bạn, không có: tool_script` ở agent
ghi `script_calls: none`, để master không giao cho nó việc phải gộp nhiều lời gọi vào một
script. Agent mà `agent.yaml` ghi `script_calls: gated` thì
dòng Công cụ của nó kết thúc bằng `; script gọi được cả công cụ ghi`, hoặc
`; script gọi được cả công cụ ghi, kể cả shell_run` khi nó giữ `shell_run`
(`· Công cụ: như của bạn; script gọi được cả công cụ ghi, kể cả shell_run`). Tên tool không nói
được điều này: hai agent giữ cùng một bộ tool, một agent làm được việc gồm hai chục lần ghi trong
một bước, agent kia phải gọi từng lần. Câu ấy chỉ có khi agent còn giữ `tool_script`, và chỉ theo
tệp của chính agent đó: master có `script_calls: gated` hay không thì dòng của agent khác không
đổi. Tên job và tên skill được gộp khoảng trắng về một dòng trước khi kể: tên job do một cuộc
chat đặt, và một tên có xuống dòng sẽ đọc như một dòng roster không ai viết. Khi có ít nhất một
dòng như thế, roster kết thúc bằng
một lời dặn: các dòng này là điều đang đúng, đáng tin hơn mô tả và hơn điều master từng nói trong
cuộc trò chuyện, và việc cần một dịch vụ, kỹ năng hay công cụ mà master không có thì giao cho
agent có nó chứ không trả lời là không làm được. Lời dặn cũng nói điều ngược lại cho hai tình
trạng đầu của bảng trên: máy chủ đang chờ đăng nhập hay không nối được thì agent ấy không gọi
được nó, nên master không giao việc cần máy chủ đó mà nói rõ tình trạng với người dùng, kèm việc
họ cần làm (đăng nhập ở trang Máy chủ MCP). Thiếu câu này, master giao việc cho một agent không
gọi được tool nào của máy chủ, rồi thuật lại lời agent ấy rằng "không có công cụ". Câu cuối của
lời dặn nói dòng Công cụ không tính tool của dịch vụ ngoài: agent nào gọi được dịch vụ nào thì
chỉ xem ở dòng Dịch vụ ngoài của chính agent đó. Câu này dành cho master tự cầm một máy chủ MCP,
kẻo nó đọc "như của bạn" ở dòng Công cụ thành "cũng cầm máy chủ của tôi".

Hệ quả: roster kể đúng thứ agent dùng được lúc đó và đổi cùng lúc với nó, không ai phải sửa mô
tả. Tới tay master ngay ở lần gọi model kế tiếp: một máy chủ MCP vừa nối hay vừa rớt, đăng nhập
OAuth vừa xong hay vừa hết hạn, job tạo từ chat, job bật hay tắt, và mọi sửa đổi một agent qua web
hay API (`mcp`, `tools`, `routes`, thêm hoặc xoá agent). Thứ chỉ có hiệu lực khi agent được dựng
lại thì roster cũng kể từ lúc đó, tức là cùng lúc chính agent ấy dùng được nó: một tệp skill mới
thả vào thư mục skill (cần sửa agent qua web hay API, hoặc khởi động lại), và `agent.yaml` sửa
tay, kể cả job khai trong đó (cần khởi động lại, hoặc một lần lưu khoá hay tuyến chung ở Kết
nối, vì lần lưu đó dựng lại mọi agent từ tệp của nó). Xem đúng thứ master đang đọc bằng
`GET /api/agents/default/prompt`.

Hai chỗ roster cố ý không nói khác đi. Một máy chủ vừa nối xong có thể vắng mặt trong chốc lát,
cho tới khi tool của nó được gắn vào agent: lúc đó agent chưa cầm tool nào, nên chưa có gì để
giao. Và job vẫn được kể trên một server chạy `--no-schedule` (bộ eval, bản chạy thử), để prompt
ở đó giống prompt của bản chạy thật.

Phần các dòng này không kể được là việc agent làm trong lĩnh vực của nó mà không lộ ra thành
tool, skill, job hay máy chủ: điều chỉ nằm trong persona, hay script trong workspace mà agent
chạy bằng `shell_run`. Phần đó vẫn do `description` nói, nên mô tả nên nói về vai trò và lĩnh
vực, không cần liệt kê lại dịch vụ hay công cụ.

Agent nào cầm một tool ghi canvas thì system prompt của nó có thể kết thúc bằng một mục
**Canvas**, tuỳ lượt đến từ đâu. Lượt từ Telegram và job (người đọc không ngồi ở web) được dặn
chỉ tạo canvas khi được yêu cầu hoặc khi tài liệu dài và còn sửa tiếp, và rằng một dòng
`FILE: artifact:<id>` gửi canvas đi như một tệp. Lượt từ kênh không ghi được canvas được dặn trả
lời thẳng trong tin nhắn. Lượt từ web chat không có mục này. Agent được giao việc không có kênh
riêng: nó theo kênh của cuộc trò chuyện gốc của chuỗi, nên cùng một agent con ghi được canvas
khi master nhận việc từ web chat và không ghi được khi việc đến qua `POST /api/inbound`. Bảng
kênh ở [canvas.md](canvas.md#7-phạm-vi-và-kênh).

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
| front matter có dòng mang dấu hai chấm thứ hai (`description: Use when: …`) | đọc được, mô tả đến nguyên văn; đoạn ngay dưới bảng nói dòng nào được đọc như thế |
| front matter không đọc được | chỉ mất đúng tệp đó: agent, lệnh hay skill trong tệp bị bỏ ra và log nêu đường dẫn cùng chỗ còn vướng, các tệp khác vẫn nạp |
| `settings.json` → `hooks.PreToolUse` / `hooks.PostToolUse`, các mục `type: command` | hook tool, xem bên dưới. Các loại hook và sự kiện khác bị bỏ qua |

**Front matter có dấu hai chấm thứ hai.** Kit viết cho harness khác hay có dòng
`description: Use when: the tests fail`. Dòng đó không phải YAML, vì dấu hai chấm thứ hai
mở một cặp khoá ngay giữa một giá trị. Front matter luôn được đọc bằng YAML trước, và khối
nào YAML đọc được thì kết quả đúng như YAML cho ra. Chỉ khi YAML từ chối, khối mới được đọc
lần thứ hai: mỗi dòng dạng `khoá: giá trị` viết từ cột đầu, có giá trị là chữ trần mang
`: ` ở giữa hay kết thúc bằng `:`, được lấy nguyên văn làm chữ cho đến hết dòng. Phần sau
dấu `#` trên dòng đó cũng thuộc về chữ, vì `issue #12` thường là một phần của câu chứ không
phải ghi chú; dòng mà dấu hai chấm chỉ nằm sau dấu `#` thì để nguyên, vì YAML vốn đọc được
dòng ấy. Lần đọc thứ hai không đụng đến giá trị mở đầu bằng dấu nháy hay một ký hiệu của
YAML (`[`, `{`, `|`, `>`, `&`, `*`, `!`, `%`, `@`, dấu huyền, hoặc `-` và `?` đứng trước
dấu cách), khoá lồng dưới một khoá khác, giá trị trải nhiều dòng và mục của danh sách.
Khối hỏng ở những chỗ đó vẫn bị từ chối, và lỗi trong log nêu chỗ còn vướng. Dòng mang một
ký tự mà YAML coi là hết dòng (dấu về đầu dòng đứng giữa dòng, U+0085, U+2028, U+2029) hay
một ký tự điều khiển cũng để nguyên, nên khối ấy bị từ chối như trước; dấu về đầu dòng ở cuối
dòng của tệp Windows thì chỉ bị cắt đi. Lần đọc thứ hai xét từng dòng và không theo dấu nháy
hay dấu ngoặc của YAML, nên nó lấy cả dòng có dạng trên nằm giữa một giá trị trải nhiều dòng
(trong nháy, trong `{…}` hay `[…]`). Vì vậy mỗi dòng đã lấy làm chữ phải là một cặp khoá riêng
ở tầng ngoài cùng của kết quả, mang đúng chữ ấy; có dòng không phải thế, hay hai dòng cùng
một khoá, thì cả khối bị từ chối bằng chính lỗi mà YAML đã nêu ở lần đọc đầu. Cách đọc này
dùng chung cho tệp agent, lệnh, skill và persona.

**Hook** chạy lệnh với cùng JSON trên stdin mà các harness gửi:
`hook_event_name`, `tool_name`, `tool_alias` (tên bên harness, `Bash` cho `shell_run`),
`tool_input`, `agent_id`, `cwd`, và `tool_response` sau lời gọi. Matcher là regex
trên cả hai tên, nên hook viết cho `Bash` sẽ kích hoạt với `shell_run`. Hai tool canvas chạm
tệp trong workspace được hỏi như tool tệp tương ứng: hook nêu `Read` hay `workspace_read` cũng
được hỏi về `artifact_import`, hook nêu `Write` hay `workspace_write` cũng được hỏi về
`artifact_export`; `tool_name` vẫn là tên thật, `tool_alias` là `Read` / `Write`, và
`tool_input.path` là đường dẫn tệp. Mã thoát 2, hoặc JSON
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

Một mô tả có dấu hai chấm thứ hai (`description: Use when: …`) đọc được dù không phải
YAML: dòng đó được lấy nguyên văn làm chữ, theo quy tắc ở mục
[Kit](#kit-agents-claude-opencode). Front matter không đọc được thì skill đó bị bỏ ra và
log nêu đường dẫn tệp, các skill khác vẫn nạp. Front matter đọc được mà không phải các cặp
khoá (một dòng chữ, một danh sách) thì coi như không khai gì.

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

### Giữ lại script đã chạy tốt

Một script agent viết cho `tool_script` chạy đúng rồi trôi đi cùng lượt: lần sau gặp lại việc đó
nó viết lại từ đầu, tốn thêm một lần nghĩ và có thể viết sai. Giữ nó lại không cần tính năng nào
riêng: một skill dạng thư mục của chính agent, mang một thư mục `scripts/`, là đủ.

```text
<agent dir>/workspace/skills/saved-scripts/
├── SKILL.md
└── scripts/
    ├── deadlines-due.py
    └── inbox-by-sender.py
```

```yaml
skills_dirs: [workspace/skills]   # trong agent.yaml; tính từ thư mục của agent
```

`SKILL.md` là mục lục: mỗi script một dòng nói nó làm việc gì và phải sửa gì trước khi chạy.

```markdown
---
name: saved-scripts
description: Script tool_script đã chạy đúng; đọc trước khi viết script mới
---
Mỗi tệp trong `scripts/` là một script đã chạy đúng. Có tệp làm đúng việc đang cần thì đọc tệp
đó, sửa mấy hằng số ở đầu, rồi đưa cả đoạn làm tham số `script` của `tool_script`.

- `scripts/deadlines-due.py`: việc sắp tới hạn trong `data/deadlines.json`; sửa `DAYS`.
- `scripts/inbox-by-sender.py`: đếm thư theo người gửi; sửa `SINCE`.
```

Mỗi tệp là nguyên văn một script, với những thứ hay đổi gom lên đầu:

```python
# Việc còn dưới DAYS ngày trong data/deadlines.json. Sửa DAYS rồi đưa cả đoạn cho tool_script.
DAYS = 3

rows = json.loads(tools.workspace_read(path="data/deadlines.json"))
for row in rows:
    if row["days_left"] <= DAYS:
        print(row["title"], "- còn", row["days_left"], "ngày")
```

- **Persona bảo agent đọc trước.** Skill không gắn sẵn chỉ hiện một dòng trong chỉ mục, và model
  tự quyết có đọc hay không. Muốn chắc thì viết thành một quy tắc có điều kiện trong `AGENTS.md`
  của agent, ví dụ: "Trước khi viết một script mới cho `tool_script`, gọi `skill_read` với
  `saved-scripts`; có script làm đúng việc thì đọc tệp đó và dùng lại, chỉ sửa tham số."
- **Agent đọc bằng gì.** `skill_read` chỉ trả về phần thân của `SKILL.md`, mở đầu bằng dòng "Thư
  mục kỹ năng (script, tài liệu kèm theo): …" ghi đường dẫn tuyệt đối của thư mục; các tệp trong
  `scripts/` agent tự đọc qua đường dẫn đó. `workspace_read` chỉ nhận đường dẫn nằm trong
  workspace, nên thư mục skill đặt trong workspace như trên thì đọc được bằng `workspace_read`.
  Đặt dưới `<agent dir>/skills` (ngoài workspace mặc định) thì chỉ `shell_run` đọc tới, tức là
  phải qua cổng duyệt ở cuộc trò chuyện không autonomous. Script không tự chạy từ tệp: agent đọc
  tệp rồi chép cả đoạn vào tham số `script`.
- **Chủ lưu bằng tay.** Crew không tự lưu script nào. Thấy một script đáng giữ thì mở thẻ
  `tool_script` trong khung chat, bấm "Xem đầy đủ" để lấy nguyên văn, lưu thành một tệp trong
  `scripts/` và thêm một dòng vào `SKILL.md`. Tệp trong `scripts/` có hiệu lực ngay vì nó được
  đọc lúc cần; dòng mới trong `SKILL.md` chỉ tới agent khi agent được dựng lại (một lần sửa agent
  qua web hay API, hoặc khởi động lại).
- **Vì nằm trong workspace nên agent cũng ghi được vào đó.** `workspace_write` và
  `workspace_edit` của agent với tới thư mục này như mọi tệp khác của workspace, qua cổng duyệt
  như mọi lần ghi. Muốn chỉ chủ sửa được thì đặt `write_paths` không bao gồm thư mục skill (và
  `shell_write_paths` nếu agent có `shell_run`).
- **Một script đã lưu vẫn là một script.** Nó chạy trong đúng các giới hạn của `tool_script` và
  chỉ gọi được những tool mà `script_calls` của agent cho phép lúc chạy
  ([tools.md](tools.md#gọi-tool-từ-script)); tool đổi tên hay đổi tham số thì script cũ hỏng
  với câu lỗi như một script mới viết sai.

## Lịch

Mỗi mục trong `schedules` thành một job `<agent id>/<schedule id>` trong scheduler
(tick 20 s, trường cron đọc theo `timezone` của `config.yaml`, mặc định là múi giờ của máy).

Có hai nguồn lịch. Lịch viết tay dưới đây sống trong `agent.yaml` của agent, lên đồng hồ ngay
khi agent được lưu qua web hay API (xem [Lịch trong tệp lên đồng hồ ngay khi
lưu](#lịch-trong-tệp-lên-đồng-hồ-ngay-khi-lưu)), và job của nó mang `origin: "profile"`. Lịch agent tự đề xuất qua tool
`schedule_create` (xem [tools.md](tools.md#đề-xuất-lịch-chạy)) sống trong bảng
`created_schedules` của database thay vì file, chạy ngay không cần khởi động lại, sống qua
lần khởi động lại kế tiếp, và job của nó mang `origin: "chat"`. Tab Lịch chạy gắn nhãn "tạo từ
chat" cho loại thứ hai và cho xoá tại chỗ (`DELETE /api/jobs/{id:path}`, xoá dòng
`created_schedules` và `job_state`, giữ nguyên lịch sử run); lịch viết tay không có nút xoá vì
xoá nó nghĩa là sửa yaml, còn lịch từ chat không có nút sửa lịch vì trình sửa agent chỉ chứa
lịch trong yaml: muốn đổi thì xoá rồi để agent đề xuất lại. Lịch từ chat chỉ tạo được loại job
prompt — không có job command, script hay consolidate qua chat — và luôn cần người duyệt nguyên
văn prompt trước khi chạy lần đầu, dù cuộc trò chuyện có autonomous hay không.

| Khoá | Ý nghĩa |
|---|---|
| `id` | mặc định `job-<index>`; dùng trong tên job và trong `POST /api/jobs/{agent}/{id}/run` |
| `name` | mặc định là id; hiện trong UI |
| `cron` **hoặc** `every` | đúng một trong hai: cron năm trường, hoặc `30m` / `2h` / `1d` |
| `prompt`, `command` **hoặc** `script` | đúng một trong ba: prompt mở một cuộc trò chuyện autonomous mới và chạy một lượt; command chạy qua `shell_run` trong workspace và chỉ ghi lại bước đó; script chạy một script như của `tool_script` mà không mở lượt nào của agent, xem [Job chạy script](#job-chạy-script). Không có cái nào, hay có hai, thì crew không khởi động và `PATCH /api/agents/{id}` trả 422 |
| `then_prompt` | chỉ đứng cạnh `script`: prompt của lượt được mở khi script chạy xong và có in ra gì đó. Không đặt thì job script không bao giờ mở lượt nào, và model chỉ được gọi nếu chính script hỏi nó bằng `llm.classify` / `llm.summarise`. Đặt thì phải là chuỗi có chữ; đặt cạnh `prompt` hay `command` thì bị từ chối như trên |
| `enabled` | mặc định `true`. Lịch đang bật có thể tạm dừng và tiếp tục từ thẻ job (`PATCH /api/jobs/{agent}/{id}/state`); công tắc đó lưu trong bảng `job_state` và sống qua khởi động lại. Lịch tắt ở đây chỉ bật lại được bằng cách sửa yaml |
| `skills` | danh sách tên skill gắn toàn văn vào cuộc trò chuyện mà job prompt mở ra; mặc định rỗng, và tên không skill nào cung cấp được ghi log cảnh báo lúc khởi động. Tên skill có gạch nối viết trong `prompt` cũng được gắn. Với job script, đó là cuộc trò chuyện mở cho `then_prompt`, và tên skill viết trong `then_prompt` cũng được gắn |
| `approval_ttl_seconds` | số giây một yêu cầu duyệt trong cuộc trò chuyện job prompt mở ra chờ người trả lời: số nguyên từ 60 đến 43200 (12 giờ), không đặt trong ngoặc kép; không đặt thì theo `approval_ttl_seconds` của `config.yaml`. Job chạy lúc không ai thức nên đặt dài hơn, ví dụ `7200`. Cuộc trò chuyện giữ hạn này cho mọi yêu cầu về sau, kể cả sau khi server khởi động lại, và cuộc của agent con được giao việc chép lại nó. Trình sửa trên web giữ khoá này qua các lần sửa nhưng không có ô nhập; `PATCH /api/agents/{id}` gửi `schedules` mà dòng nào thiếu khoá thì dòng đó mất khoá |

### Lịch trong tệp lên đồng hồ ngay khi lưu

Lưu một agent qua trình sửa trên web, `POST /api/agents` hay `PATCH /api/agents/{id}` thì đồng hồ
đọc lại ngay các dòng lịch mà tệp của nó nêu, kể cả job gom ghi nhớ sinh từ `memory_consolidate`.
Cài một template và `POST /api/agents/reload` cũng làm vậy với agent vừa vào đội. Không lần nào
trong số đó cần khởi động lại. Trên web, sau một lần lưu có đổi lịch, trình sửa nói "Đã lưu. Thay
đổi lịch chạy có hiệu lực ngay, không cần khởi động lại." cho tới khi một ô của form được sửa tiếp
hay form được đặt lại, và màn Lịch chạy đọc lại danh sách job
sau mỗi lần lưu, tạo, cài hay xoá agent, nên dòng mới có mặt và dòng bị bỏ biến mất mà không cần
tải lại trang. `POST /api/agents/reload` chưa có nút nào trên web. Đồng hồ so từng job theo id
với dòng nó đang giữ:

- **Dòng mới, dòng đổi `cron` hay `every`, và dòng tệp vừa bật lại (`enabled` từ tắt sang bật)
  được tính từ lúc lưu.** Job cron chạy ở giờ khớp đầu tiên sau lúc lưu; job `every` chạy sau
  đúng một khoảng tính từ lúc lưu. Giờ đã qua không được chạy bù: đổi `0 7 * * *` thành
  `0 6 * * *` lúc 06:30 thì job chạy lúc 06:00 sáng hôm sau, không chạy ngay vì đã lỡ 06:00 hôm
  nay.
- **Dòng không đổi giờ thì giữ nguyên mốc.** Sửa prompt, lệnh, script, tên hay skill của một
  dòng, hoặc sửa một khoá khác của agent, không dời lần chạy kế tiếp của dòng đó: job `every: 2h`
  đã chờ được 90 phút vẫn chạy sau 30 phút nữa, và chạy bằng nội dung vừa lưu.
- **Dòng bị bỏ khỏi tệp rời đồng hồ và không chạy nữa.** Công tắc tạm dừng của nó (bảng
  `job_state`) bị xoá và số lần hỏng liên tiếp đang đếm cho nó được quên; lịch sử run giữ nguyên.
  Sau này thêm lại một dòng cùng id thì đó là một job mới: đang bật, tính từ lúc lưu, không mang
  gì của dòng cũ.
- **Công tắc tạm dừng sống qua mọi lần lưu còn giữ dòng đó**, kể cả lần lưu đổi giờ của nó. Số
  lần hỏng liên tiếp cũng vậy, nên dòng báo lịch chạy lại được vẫn tới khi job chạy được.
- **Job đang chạy lúc lưu thì chạy xong như dòng nó bắt đầu.** Lần chạy đó không bị cắt và không
  chạy lại vì lần lưu. Nếu dòng của nó vừa bị bỏ thì kết quả của lần chạy ấy không được đếm hay
  báo cho job nào.
- **Dòng được lưu hay bị bỏ trong lúc một job khác của cùng nhịp đang chạy** thì không chạy theo
  dòng cũ ở nhịp đó; nhịp kế tiếp (20 giây sau) xét nó theo dòng mới.

Tệp `agent.yaml` của một agent đang chạy mà sửa bằng tay thì không ai đọc lại cho đến lần khởi
động sau, hoặc đến một lần lưu khoá hay tuyến mô hình chung ở Quản lý → Kết nối: lần lưu đó dựng
lại mọi agent đang chạy từ tệp của nó, và lịch trong tệp lên đồng hồ theo đúng các quy tắc trên.
Lịch tạo từ chat không đi qua đường này: nó vẫn được đọc từ database mỗi lần đồng hồ cần.

### Job chạy script

Một việc kiểm tra mỗi tuần mới tới hạn một lần mà sáng nào cũng hỏi model thì sáng nào cũng trả
tiền để nghe "OK". Lịch có khoá `script` làm việc kiểm tra đó bằng một script của `tool_script`
([tools.md](tools.md#gọi-tool-từ-script)): script tự gọi tool, tự lọc, và **không lượt nào của
agent** được mở trừ khi nó có điều để nói. Model chỉ được gọi ở lượt đó, hoặc khi chính script
hỏi nó một việc nhỏ bằng `llm.classify` / `llm.summarise`. (Đừng nhầm với mục kế tiếp, nơi một
job prompt gọi một script shell trong workspace.)

- **Chạy bằng gì.** Đúng bộ máy và đúng các giới hạn của `tool_script`: cùng ngôn ngữ, cùng tiến
  trình con không khoá không mạng, cùng 25 lời gọi và 300 giây. Agent không cần giữ
  `tool_script`: job chạy trên những tool script của agent gọi được, dù tool ấy có được giao hay
  không, kể cả ở agent ghi `script_calls: none`. Chữ đó lấy `tool_script` khỏi tay model; script
  của lịch là chữ của chủ, viết trong tệp của agent. Script dài tối đa 20.000 ký tự và được xét
  cả đoạn lúc nạp, như khi model viết: sai cú
  pháp hay dùng thứ ngôn ngữ không có thì crew không khởi động, và lần lưu qua
  `PATCH /api/agents/{id}` trả 422, cả hai kèm tên agent, tên lịch và lời của phép xét.
- **Gọi được gì.** Theo `script_calls` của chính agent ([agent.yaml](#agentyaml)). Mặc định
  `read_only`: chỉ những tool đọc mà script của một lượt gọi được; agent ghi `none` cũng chạy
  script của lịch ở đúng mức chỉ đọc đó. Với `gated`, script gọi thêm
  tool có ghi, và cổng duyệt xét từng lời gọi như trong cuộc trò chuyện autonomous mà một job
  prompt mở ra: tool cần duyệt mà không có lý do hỏi riêng thì chạy, lệnh shell không khớp mẫu
  nào cũng chạy. Giao việc cho agent khác (`tools.delegate`) thì không, ở cả hai mức: job không
  có cuộc trò chuyện nào để làm cha của việc được giao, nên script dừng với câu bảo gọi trực
  tiếp.
- **Hỏi model từ script.** `llm.classify` và `llm.summarise` dùng được trong script của job như
  trong một lượt, ở mọi mức `script_calls` ([tools.md](tools.md#gọi-tool-từ-script), bullet
  "Script tự hỏi model"): model của chính agent, route đầu tiên, tối đa 10 lần mỗi script. Mỗi
  lần là một lần trả tiền, nên job dùng nó không còn là job "không tốn gì khi không có gì để
  nói": script hỏi bao nhiêu lần mỗi sáng thì trả bấy nhiêu lần. Lọc bằng code trước, chỉ hỏi
  model cho phần code không quyết được. Agent ghi `script_llm: false`
  ([agent.yaml](#agentyaml)) thì script của job không hỏi được model nào: lời gọi `llm.` là một
  lỗi script bắt được ("không hỏi model được ở đây."), không bắt thì run là `error`, và không
  lần hỏi nào được gửi đi hay bị tính tiền.
- **Không bao giờ hỏi người.** Không ai trông một job và không có cuộc trò chuyện nào để một câu
  trả lời quay về, nên lời gọi mà cổng phải hỏi dù ai đang trông (lệnh khớp `shell_ask_patterns`,
  hay một tool tự khai lý do phải hỏi) làm script **dừng tại đó**, tool chưa chạy; lệnh khớp
  `shell_deny_patterns` cũng vậy. Không gì chờ, không yêu cầu duyệt nào được tạo, và run của job
  là `error` kèm câu từ chối. `ask_user` và `schedule_create` vẫn ở ngoài mọi script.
- **Không có cuộc trò chuyện.** Script của job chạy ngoài mọi cuộc trò chuyện, nên tool làm việc
  qua một cuộc trò chuyện hỏng ở đó như một lỗi script bắt được: các tool canvas ("Canvas chỉ
  dùng được trong một cuộc trò chuyện.") và `tool_output_read`; câu trả lời dài hơn 200.000 ký
  tự cũng không được giữ lại để đọc tiếp. Việc nào cần cuộc trò chuyện thì để cho lượt của
  `then_prompt`.
- **Run.** Mỗi lần chạy là một run nguồn `job:<agent id>/<schedule id>`, không gắn cuộc trò
  chuyện nào, có đúng một bước `tool_script` với các lời gọi của script liệt kê bên dưới như ở
  một lượt. Script chạy xong thì run `done`, tóm tắt là 160 ký tự cuối của cái nó in, đứng sau
  dấu `…` khi phía trước còn chữ bị cắt; hỏng, bị cổng hay một giới hạn dừng thì run `error`, tóm
  tắt là dòng đã làm script dừng, gộp về một dòng, 160 ký tự đầu của nó và dấu `…` khi còn nữa,
  không kèm chữ nào script đã in trước đó; server tắt giữa lúc
  script chạy thì run đóng lại là `error` với tóm tắt `interrupted`, như run của một lượt bị
  cắt. Lời gọi có trả tiền cho model (`image_read`, `pdf_read` trên trang scan, một lần script
  hỏi model bằng `llm.`) được tính vào run; sổ cái sử dụng ghi lần hỏi model đó dưới mục đích
  `script`, không kèm cuộc trò chuyện nào.
- **Hỏng thì có tin báo.** Script chạy xong mà không in gì thì không ai nghe gì, đó là chủ ý.
  Script hỏng cũng không mở lượt nào, nên nếu im lặng thì từ chat hai chuyện ấy trông như nhau.
  Vì vậy run của script kết thúc `error` thì crew gửi một tin tới kênh của đội
  ([channels.md](channels.md#giao-theo-lịch)), bốn dòng: `Lịch "<tên lịch>" gặp lỗi khi chạy
  script:`, rồi lý do, rồi `Xem lượt chạy ở web UI, mục Quản lý → Hoạt động.`, rồi `Nếu lịch còn
  hỏng, tin nhắc kế tiếp sẽ đến sau 6 giờ.` Lý do là thứ đã làm
  script dừng: dòng lỗi của nó (`Lỗi ở dòng N: …` hay `Dừng ở dòng N: …`), hoặc dòng nói rằng script
  chạy xong mà không giữ được gì bằng `store`. Nó được gộp về một dòng: nguyên văn khi không quá 600
  ký tự, dài hơn thì 200 ký tự đầu, dấu `…` và 400 ký tự cuối, nên câu chỉ cách sửa ở cuối một lời
  từ chối vẫn tới nơi. Lý do không mang chữ nào script đã in trước khi hỏng (những chữ ấy vẫn nằm ở
  bước `tool_script` của run), và tin không bao giờ chứa nguyên văn script. Lời của một tool hỏng
  được giữ nguyên, câu của một lỗi mà script tự `raise` cũng vậy: tham số của một lời gọi chỉ có
  trong tin khi chính tool hỏng nhắc lại nó, và dữ liệu chỉ có khi script tự viết nó vào câu lỗi.
  Còn một đường thứ ba: lỗi mà trình thông dịch ném ra khi script đang xử lý một giá trị thì
  trích chính giá trị ấy (`int(...)` của một chuỗi không phải số, một khoá mà mapping không có),
  nên lý do có thể mang một phần thứ tool vừa trả về, trong giới hạn 600 ký tự nói trên.
  Lịch hỏng mãi thì không nhắn mãi: lần hỏng đầu được báo ngay, sau đó chừng nào lịch còn hỏng
  thì nhiều nhất 6 giờ một tin, và tin nhắc nói đó là lần hỏng thứ mấy liên tiếp, tính từ lúc nào.
  Lịch chạy mỗi 5 phút mà hỏng suốt một ngày vì thế nhắn bốn tin chứ không phải 288 tin. Lịch chạy
  lại được thì kênh nhận một dòng nói vậy, kèm số lần đã hỏng. Chạy tay bằng nút hay
  `POST /api/jobs/{agent}/{id}/run` được đếm và báo như lần chạy của đồng hồ. Job `command` và lần
  cô đọng bộ nhớ theo lịch hỏng cũng được báo và giãn theo cùng cách, bằng lý do của riêng chúng;
  cách đếm, lúc nào thử gửi lại và khoá `failing` của `GET /api/jobs` nằm ở
  [channels.md](channels.md#giao-theo-lịch). Lượt mà `then_prompt` mở ra hỏng thì được giao như
  lượt của job prompt và không được đếm ở đây, và run đóng lại là `interrupted` vì server tắt giữa
  chừng cũng không có tin. Không có kênh thì không gì được gửi; gửi không được, hoặc chưa gửi xong
  sau 60 giây, thì ghi log, run vẫn như nó đã kết thúc, các job tới hạn sau vẫn chạy, và lần hỏng
  kế tiếp thử gửi lại.
- **`then_prompt`.** Script chạy xong **và** in ra thứ gì đó không trống thì crew mở một lượt như
  job prompt mở: cuộc trò chuyện autonomous mới, `skills` và `approval_ttl_seconds` của lịch áp
  cho nó. Tin mở lượt là `then_prompt`, rồi một câu nói rằng phần bên dưới là những gì script
  của lịch in ra và là **dữ liệu** để làm theo lời dặn ở trên chứ không phải chỉ dẫn, rồi cái
  script in ra (cắt theo `tool_output_chars` của agent) nằm giữa hai dòng đánh dấu
  `<<<SCRIPT_IN_RA <số>` và `SCRIPT_IN_RA <số>>>>`. Số đó được tạo riêng cho từng tin, sau khi
  script đã chạy xong, nên không gì script in ra viết được dòng đóng. Cái script in ra là cái
  tool của nó đọc về (tiêu đề một thư, nội dung một trang), và lượt này không ai trông: hàng
  rào giữ cho nó không đứng ngang hàng với lời dặn của chủ. Nó **không ràng buộc** được model;
  `then_prompt` vẫn nên nói rõ việc cần làm với dữ liệu, và việc gì không được để dữ liệu sai
  khiến thì đừng trao tool cho agent đó. Run của lượt đó là kết quả của job: nó là `last_run` của job,
  và câu trả lời cuối của nó được gửi đi theo đúng luật của job prompt (kể cả luật "chỉ trả lời
  `OK` thì không gửi"). Script không in gì, hỏng, hoặc lịch không có `then_prompt` thì không
  lượt nào được mở và không gì được gửi.
- **Nhớ giữa các lần chạy.** `store(khoá, giá_trị)` và `load(khoá)` giữ dữ liệu của job dưới
  `job:<schedule id>` ([tools.md](tools.md#gọi-tool-từ-script), bullet "Giữ lại giữa các lần
  chạy"); lượt của `then_prompt` đọc và ghi cùng chỗ đó. Cái script ghi được lưu trước khi lượt
  ấy mở, nên lượt ấy hỏng giữa chừng thì sổ vẫn đã ghi: trong ví dụ dưới, việc đã vào `told` sẽ
  không được nhắc lại dù tin nhắc chưa tới tay ai. Lịch nào có script cần nhớ thì khai `id`: `id`
  mặc định theo vị trí trong danh sách, chèn một lịch phía trên là job đọc sang chỗ khác.

Ví dụ: một job nhắc hạn. Bản viết bằng `prompt` gọi model mỗi sáng dù không có gì tới hạn; bản
dưới đây chỉ gọi model vào sáng có việc mới tới hạn, và model chỉ lo phần câu chữ. Tệp
`data/deadlines.json` là của workspace (một job `command` khác làm mới nó), mỗi dòng có `id`,
`title` và `days_left`:

```yaml
schedules:
  - id: due-reminders
    name: Nhắc hạn
    cron: "30 7 * * *"
    script: |
      rows = json.loads(tools.workspace_read(path="data/deadlines.json"))
      told = load("told") or []
      due = [row for row in rows if row["days_left"] <= 3 and row["id"] not in told]
      for row in due:
          print(row["title"], "- còn", row["days_left"], "ngày")
      store("told", told + [row["id"] for row in due])
    then_prompt: |
      Dưới đây là các việc vừa tới hạn. Viết một tin nhắc ngắn, việc gấp nhất đứng trước.
```

Sáng không có việc nào mới tới hạn thì script không in gì: run ghi lại một bước, không model nào
được gọi và không tin nào được gửi. Việc đã nhắc được nhớ trong `told` nên sáng hôm sau không
nhắc lại. Tệp không đọc được thì script hỏng, run là `error`, và `told` giữ nguyên như trước lần
chạy.

Trình sửa agent trên web sửa được cả `script` lẫn `then_prompt` của một dòng lịch
([Trình sửa trên web](#trình-sửa-trên-web)), và không lưu một dòng script chưa có `id`. Một lần
lưu có gửi `schedules` viết lại cả danh sách trong `agent.yaml`, mỗi dòng của script một dòng
trong tệp. Script nhiều dòng gõ trong form không có dấu xuống dòng sau dòng cuối, nên được viết
thành khối `script: |-`; script kết thúc bằng đúng một dấu xuống dòng, như khối `script: |` của
người viết tay, vẫn được viết là `script: |`. Script một dòng nằm ngay trên dòng của khoá, và
script có dấu tab được viết trong ngoặc kép trên một dòng. Chú thích nằm giữa các dòng lịch thì
mất theo danh sách cũ.

### Một script mỗi job

Job prompt gom dữ liệu từ nhiều nơi nên gọi **một** script trả về
một khối JSON, chứ không để model điều khiển từng lệnh. Job tự điều phối
tiêu phần lớn ngân sách bước vào cú pháp shell và có thể chạm `max_steps` trước khi viết một
chữ của câu trả lời; script chỉ tốn một bước. Giữ script ngoài repo khi nó
mang id tài khoản hoặc đường dẫn. `docs/examples/job-data-script.sh` là hình mẫu: mọi
lệnh đều được rào để một thất bại ghi lại lỗi và phần dữ liệu còn lại vẫn về.

Cùng lý do, phần chuyên môn của một job prompt (câu truy vấn, tên cột, cách chọn biểu đồ, bố cục
bản tin) nên nằm trong một tài liệu ở workspace mà prompt chỉ trỏ tới và bảo agent đọc bằng
`workspace_read`. Prompt trong `agent.yaml` chỉ đổi khi agent được lưu lại hay server khởi động
lại, còn tệp trong workspace được đọc lại mỗi lần
job chạy: sửa tài liệu thì sáng hôm sau có hiệu lực, không cần lưu hay khởi động lại gì, và nội dung đi cùng
schema mà nó mô tả thay vì lệch dần với nó. Trong `agent.yaml` chỉ còn cron, lệnh script và vài
dòng prompt.

Cron `memory_consolidate` thành một job cùng hình dạng, `<agent id>/memory-consolidate`,
không có prompt hay command riêng. Nó làm hai việc liên tiếp: viết lại `MEMORY.md` (master xem
lại luôn các fact người dùng trong cùng run), rồi biên dịch wiki vault từ chính các ghi chú đó.
Việc biên dịch không có cron riêng vì cả hai nửa đọc cùng ghi chú và vault nên lắng từ cùng một đêm đọc. Mỗi nửa
có run riêng trong Activity, và biên dịch hỏng không làm job hỏng — lúc đó bản viết lại
đã xong rồi, và báo cả job thất bại sẽ khiến ai đó đi tìm
hư hại không có ở đó. Xem [memory.md](memory.md#compile).

Sau một job prompt, hay sau lượt mà một job script mở cho `then_prompt`, scheduler đẩy câu trả
lời cuối tới chat Telegram của master khi có, dưới tên của agent (bản tin sáng về
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
