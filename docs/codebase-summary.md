---
layout: default
title: Bản đồ mã nguồn
---

# Bản đồ mã nguồn

**Phiên bản**: 0.19.0 · **Cập nhật**: 2026-10-14

Đọc [system-architecture.md](system-architecture.md) trước để biết các khối là gì; tài liệu này
chỉ nói khối nào nằm ở **gói** nào. Tên tệp, hàm và số liệu không ghi ở đây: mã nguồn là nguồn
sự thật, mở thư mục là thấy.

## 1. Bố cục repo

```
my-agent-crew/
├── my_agent_crew/        # backend Python
│   ├── server/static/    # bundle web đã build, commit cùng repo
│   ├── skills/builtin/   # skill có sẵn
│   └── agents/templates/ # mẫu agent cho `agent add`
├── web/                  # SPA React + Vite; vitest + Playwright
├── desktop-helper/       # trình trợ giúp desktop: gói Swift cho macOS, XCTest
├── tests/                # pytest
├── docs/                 # tài liệu này + diagrams/
├── scripts/gates.sh      # mọi cổng CI trừ job macOS của trình trợ giúp desktop
├── pyproject.toml        # uv, ruff
└── .github/workflows/ci.yml
```

## 2. Backend `my_agent_crew/`

| Gói | Chịu trách nhiệm |
|---|---|
| `agent/` | vòng lặp một lượt: ghép lời nhắc, gọi mô hình, chạy tool, dừng chờ duyệt, chạy tiếp, cắt ngữ cảnh dài, sự kiện của lượt, lượt đến từ kênh nào (và vì thế có được ghi canvas không), phần canvas model còn đang viết để web xem trước, một lời gọi tool lẻ chạy trong task riêng để lượt báo từng lời gọi của script ngay khi nó xong (`tool_run.py`), số lời gọi lồng mà các script của một lượt dùng chung (`nested_calls.py`), và phần kết quả của script được lưu kèm tin (`tool_events.py`) |
| `agents/` | hồ sơ agent từ đĩa: đọc/ghi `agent.yaml` giữ chú thích, vá và kiểm tra, một lần sửa được đưa đường dẫn nào vào và viết nó thế nào (`profile_edit_paths.py`), đọc lại tệp sắp ghi bằng bộ đọc của lúc khởi động trước khi ghi (`profile_read_back.py`), roster cho master và cách kể mỗi agent đang có gì, đọc kit `.agents/`, mẫu agent |
| `activity/` | run và step của mọi lượt cùng mọi thay đổi canvas, phát cho web qua SSE từ bất kỳ luồng nào; lời gọi của script được liệt kê và tính tiền trên step của nó ngay khi xong, rồi xếp lại theo thứ tự đã viết khi script có kết quả (`tool_steps.py`); phần câu trả lời được giữ cho mỗi bước tool là 160 ký tự đầu khi đạt, còn khi lỗi là cả câu tới 600 ký tự hoặc đầu và cuối của nó (`step_previews.py`) |
| `artifacts/` | canvas: loại nào giữ chữ hay byte và trần của mỗi loại, áp và định vị một lần sửa, diff gọn trong ngân sách, tên tệp khi tải về, trang chạy cách ly của canvas `html` và `mermaid` |
| `browser/` | trình duyệt của agent: mỗi agent một Chromium với hồ sơ riêng, mở ở lời gọi đầu và dừng khi không ai dùng (`pool.py`, nơi duy nhất nạp Playwright); tab thuộc về cuộc trò chuyện đã mở nó (`tabs.py`); proxy trong tiến trình mà mọi request của trang đi qua, từ chối địa chỉ không công khai (`proxy.py`, `network.py`); đọc một địa chỉ đúng cách trình duyệt đọc, khớp host với `browser_hosts` và tìm từ phải dừng lại hỏi người trong tên phần tử (`policy.py`); dàn ý của trang thành `ref`, tên và vai trò (`snapshot.py`, `snapshot_view.py`) và câu trả lời đặt trang giữa hai dòng rào (`report.py`); tám tool `browser_*` (`navigate.py`, `tools_read.py`, `screenshot.py`, `tools_pdf.py`, `tools_act.py`, `tools_download.py`), luật xét một thao tác trước khi hỏi trình duyệt (`act.py`) và phần kiểm phần tử ngay trước khi làm (`act_page.py`); tệp trang gửi về, chỉ giữ khi đang có một lời gọi chờ đúng tệp ấy (`downloads.py`); thư mục và tên của tệp mà tool để lại trong workspace (`saved.py`, `tools_files.py`), tệp ấy được ghi qua descriptor và không qua symlink nào (`folder.py`), kèm dấu cách ly của macOS (`quarantine.py`); khởi động và đóng một Chromium của đội, dù là của agent hay cửa sổ đăng nhập (`launch.py`), và một trình duyệt khi đang chạy (`session.py`); cửa sổ đăng nhập có giao diện trên chính hồ sơ của agent (`login.py`, `login_window.py`), máy có người ở trước màn hình không khoá hay không (`console.py`), và những host trình duyệt có thể còn đăng nhập, đọc từ host và hạn của cookie (`logins.py`); máy đã cài trình duyệt hay chưa (`install.py`). Xem [tools.md](tools.md#trình-duyệt) |
| `channels/` | Telegram: poll, tin vào, ảnh và album, tin ra, lệnh `/…`, câu trả lời cho `ask_user`, gửi canvas như một tệp và báo lượt đã ghi canvas nào, offset, che token |
| `desktop/` | desktop của agent, phía server: client Unix socket nói chuyện với trình trợ giúp (mỗi yêu cầu một dòng JSON trên một kết nối, chỉ tin socket của chính người dùng chạy server), mức và danh sách ứng dụng của từng agent, luật xét một thao tác trước khi ai bị hỏi (ứng dụng, khung hình, `ref`, phím, chữ không bao giờ gõ) và lý do phải hỏi người, dàn ý mà hội thoại vừa được xem, ảnh chụp lưu trong workspace, câu trả lời đặt màn hình giữa hai dòng rào, và bốn tool `computer_*`. Xem [tools.md](tools.md#desktop) |
| `inbound.py` | một cổng vào chung cho mọi nền tảng |
| `llm/` | provider: OpenRouter, Ollama, provider giả; chuỗi tuyến và fallback |
| `mcp/` | client MCP viết tay trên `httpx`: đọc `mcp_servers` của `config.yaml`, một request JSON-RPC qua streamable HTTP (JSON hoặc SSE), phiên làm việc và danh sách tool, tool MCP thành tool của agent (tên, duyệt, mức mở, kết quả thành chữ), hub giữ trạng thái từng máy chủ và giao tool cho agent, `tool_search` để agent tìm và nạp tool chưa khai sẵn (BM25 trên tên, mô tả, tham số), đăng nhập OAuth 2.1 (dò metadata, tự đăng ký, PKCE, gia hạn) và nơi giữ token |
| `memory/` | ghi chú ngày, facts chung, gom 7 ngày thành đề xuất, tìm kiếm, tóm tắt cuộc trước, vault wiki |
| `scheduler/` | cron: phân tích lịch, job đến hạn, chạy job (prompt, command, consolidate, và script: `script_job.py` chạy một script mà không mở lượt nào của agent, trừ khi script in ra gì đó và lịch có `then_prompt`; cái in ra tới lượt đó giữa hai dòng đánh dấu, là dữ liệu chứ không phải chỉ dẫn), giao kết quả ra kênh, và báo kênh khi một job hỏng mà không mở lượt nào, dù là script, lệnh hay lần cô đọng bộ nhớ (`failure_notice.py`): lần hỏng đầu báo ngay, sau đó nhiều nhất 6 giờ một tin chừng nào job còn hỏng, và một dòng khi job chạy lại được (`failure_streaks.py`) |
| `script/` | `tool_script`: một trình thông dịch nhỏ cho một phần của Python (kiểm cả đoạn trước khi chạy, biểu thức, câu lệnh, hàm có sẵn, phương thức của từng kiểu, `json`), các giới hạn về bước, bộ nhớ, đầu ra và số lời gọi, tiến trình con chạy script với môi trường rỗng (trên macOS trong sandbox riêng), bên chạy nói chuyện với nó từng dòng JSON, và tool giao cho mọi agent giữ ít nhất một tool script gọi được, trừ agent ghi `script_calls: none` (`hand_script`, gọi lúc dựng agent và mỗi lần giao tool MCP): mặc định chỉ gọi được tool chỉ đọc, còn agent khai `script_calls: gated` thì gọi được cả tool đổi trạng thái, mỗi lời gọi qua phán quyết của cổng duyệt trước khi chạy (`gate.py`, `scope.py` nói tool nào script gọi được), lời mô tả nêu tool có sẵn rồi tool MCP mở cho script trong chung một trần ba mươi dòng, ghi lại từng lời gọi, cho script tra tên và tham số của tool (`names`, `search`, `describe`) mà không chạy tool nào, và cho script gọi nhiều tool cùng lúc trong một lô (`batch`: `calls.py` kiểm lô và đếm lời gọi bên tiến trình con, `replies.py` trả lời từng loại tin của tiến trình con bên cha, `nested.py` chạy lô với tối đa bốn lời gọi một lúc, `one_by_one.py` chạy lô có lời gọi ghi từng lời gọi một và hỏi lại cổng trước mỗi lời gọi sau lời đầu); `nested.py` cũng lấy từng lời gọi từ số lời gọi lồng của lượt và đếm số ký tự script nhận được, còn `fit.py` cắt câu trả lời cho vừa script và giữ lại cả bản dài hơn mức script nhận để đọc tiếp bằng `tool_output_read`; `description.py` dựng lời mô tả của `tool_script` cho từng agent; `printed.py` giữ phần đầu và phần cuối của cái script in ra khi nó in quá mức; `store` và `load` giữ dữ liệu JSON giữa các lần chạy (`kept.py` nói khoá và giá trị phải thế nào cho cả tiến trình con lẫn bên cha, `store_session.py` chọn kho theo job hay cuộc trò chuyện và chỉ áp các lần ghi khi script chạy xong); `gate.py` cũng là cổng cho script của một job, việc không ai trông; script hỏi model của agent bằng `llm.classify` và `llm.summarise`, trừ agent ghi `script_llm: false` (`llm_calls.py` kiểm tham số và đếm lần hỏi bên tiến trình con, `model_calls.py` gọi model bên cha trên route đầu tiên và ghi mỗi lần hỏi thành một lời gọi của script, `model_answers.py` dựng câu hỏi với hàng rào quanh văn bản và đọc câu trả lời thành một nhãn hay một bản tóm tắt đã cắt); script của agent `script_calls: gated` giao việc được cho agent khác bằng `tools.delegate` (`delegation.py` nói script nào được giao và cho ai, cho mỗi việc một id lời gọi riêng và giữ số việc được giao cùng lúc ở mức ba; script như thế được chạy lâu hơn, và kết quả của nó mang tiền các cuộc trò chuyện con đã tiêu) |
| `server/` | FastAPI: dựng runtime, lắp provider và tool cho từng agent, đọc mỗi agent của đội đang chạy có gì để roster kể lại, áp dụng kết nối không cần restart, kiểm tra khoá, ghi `<home>/env`, hàng rào Host/Origin, phục vụ tệp agent viết như nội dung không tin cậy, đổi lời từ chối của kho canvas thành mã HTTP, các nhóm route |
| `skills/` | nạp skill markdown, chỉ mục trong lời nhắc |
| `store/` | SQLite: cuộc trò chuyện, tin, duyệt, run, trạng thái job, đề xuất trí nhớ, sổ chi tiêu; canvas với phiên bản, liên kết canvas với cuộc trò chuyện, canvas đang mở cùng đoạn được chọn, ghi chú canvas đi kèm tin, lời gọi và hai số đo của script đi kèm kết quả của nó, những gì script giữ giữa các lần chạy (`script_store`) |
| `tools/` | mọi tool: workspace, shell và sandbox, web, trí nhớ, wiki, giao việc, canvas (kèm nhập từ và xuất ra tệp workspace, và agent nào với tới canvas nào), hỏi người dùng, PDF, ảnh, skill, hook |
| `config*.py` | cài đặt từ env + `config.yaml` |
| `texts*.py` | mọi chuỗi tiếng Việt của backend |
| `__main__.py` | CLI: `python -m my_agent_crew`, `agent list-templates`, `agent add` |

Một lượt phát ra một chuỗi sự kiện (chữ, tin trợ lý, gọi tool, kết quả tool, cần duyệt, xong,
dừng, lỗi, đổi tuyến, leo thang). Cùng một chuỗi vừa là SSE cho web, vừa là step ghi vào run. Vài sự kiện
chỉ để hiển thị (chữ đang chảy, `user_context`, `tool_call_delta`) đi qua SSE của lượt mà không
được lưu; xem [system-architecture.md](system-architecture.md#28-canvas-tài-liệu-người-và-agent-cùng-sửa).

## 3. API

| Nhóm | Đường |
|---|---|
| Sức khoẻ | `GET /api/health` |
| Cổng vào | `POST /api/inbound` |
| Cuộc trò chuyện | `GET/POST/DELETE /api/conversations[/{id}]`, `POST …/{id}/messages` (SSE; `request_id` do tab đặt để một lần gửi lặp lại không tạo tin thứ hai), `GET …/{id}/summary` |
| Lượt đang chạy | `GET /api/conversations/{id}/turn` (SSE: xem lượt server đang đọc, kể cả lượt của Telegram hay job; `204` khi không có lượt nào), `POST …/{id}/stop` (trả các tin còn chờ và dừng lượt server đang đọc cho cuộc đó; `cancelled` cho biết có lượt nào bị dừng không) |
| Tìm trong hội thoại | `GET /api/messages/search?q=&agent_id=&limit=` (FTS5 trên nội dung tin, `conversation_search` là bản cho model) |
| Duyệt | `GET /api/approvals`, `POST /api/conversations/{id}/approvals/{aid}` (`{"approve": bool}`), `POST …/approvals/{aid}/answer` (câu hỏi của `ask_user`) |
| Run | `GET /api/activity/runs`, `GET …/runs/{id}`, `GET …/runs/{id}/trajectory?format=json\|md[&full=1]` (cả lượt chạy thành tệp để lưu), `GET …/stream` (SSE: run, step, và event `artifact` mỗi lần một canvas được tạo, ghi, đổi tên, khôi phục hay xoá), `GET /api/stats` |
| Canvas | `GET/POST /api/artifacts` (`?conversation_id=&q=&limit=`), `GET …/usage` (`{count, bytes, cap, by_artifact}`: số canvas, tổng byte của mọi phiên bản, trần chung của kho và cỡ từng canvas), `GET/PUT/PATCH/DELETE …/{id}` (`PUT` cần `base_version`; lưu trên bản cũ là 409 kèm bản mới nhất, không ghi đè), `GET …/{id}/versions[/{n}]`, `POST …/{id}/restore`, `GET …/{id}/raw[?version=&download=1]` (luôn là chữ thuần, không chạy gì), `GET …/{id}/render` (trang chạy cách ly, chỉ cho `html` và `mermaid`), `POST …/{id}/reimport` (`{"base_version"}`; đọc lại tệp workspace mà canvas ghi là nguồn, không đổi thì không thêm phiên bản, trả `{changed, artifact}`); mọi lần ghi qua REST là của người. Agent đưa tệp trong workspace vào canvas bằng `artifact_import` và ghi canvas ra tệp bằng `artifact_export` (cần duyệt); web hiện nguồn của canvas và nút "Nhập lại" |
| Canvas đang mở | `GET/PUT /api/conversations/{id}/canvas` (`{"artifact_id", "selection"}`, `null` là đóng); mỗi tin chat mang `canvas` của tab gửi nó, nên ghi chú nói đúng canvas thiết bị đó đang mở |
| Agent | `GET /api/agents`, `GET …/{id}`, `GET …/{id}/files`, `GET …/{id}/script-store` (những gì script của agent đã giữ bằng `store`, theo từng kho, kèm trần của mỗi kho và kho là của lịch hay cuộc trò chuyện nào, còn hay đã mất), `GET …/{id}/script-store/value?namespace=&key=` (một giá trị nguyên vẹn), `DELETE …/{id}/script-store?namespace=[&key=]` (quên một khoá hoặc cả một kho; không có đường ghi một giá trị), `POST /api/agents/install`, `GET /api/templates` |
| Sửa agent | `POST /api/agents`, `PATCH …/{id}`, `DELETE …/{id}` |
| Trình duyệt của agent | `GET /api/agents/{id}/browser` (mức của agent, máy đã bật và đã cài chưa, đang chạy hay không, từng tab theo nhãn, tiêu đề, host và cuộc trò chuyện, cửa sổ đăng nhập có đang mở và mở được không (`login`), những host có thể còn đăng nhập (`logins`, `logins_more`); không mở trình duyệt nào và không bao giờ trả cả địa chỉ), `POST …/{id}/browser/stop` (dừng ngay, đóng cả cửa sổ đăng nhập đang mở, phiên đăng nhập còn nguyên), `DELETE …/{id}/browser/tabs/{tab_id}` (đóng một tab), `POST …/{id}/browser/login` (`{"url"}` tuỳ chọn; mở cửa sổ đăng nhập trên màn hình máy chạy đội; 409 kèm lý do khi không mở được, 422 khi địa chỉ là nơi trình duyệt của đội không tới), `POST …/{id}/browser/login/done` (đóng cửa sổ). `GET /api/connections` mang khối `browser` của máy |
| Desktop của agent | `GET /api/agents/{id}/desktop` (mức và ứng dụng của agent, cùng điều trình trợ giúp nói về máy; không có trình trợ giúp không phải lỗi), `POST …/{id}/desktop/screenshot` (một lần chụp thử, giữ đúng giới hạn của agent, ảnh là một tệp trong workspace của nó; 409 kèm một câu khi không chụp được), `POST /api/desktop/permissions` (nhờ trình trợ giúp hỏi macOS hai quyền, đường duy nhất có thể bật hộp thoại trên màn hình của máy; 409 khi không có trình trợ giúp hay màn hình khoá). `GET /api/connections` mang khối `desktop` của máy |
| Tệp tính cách | `PUT /api/agents/{id}/files/{name}`, `GET …/{id}/prompt` (lời nhắc hệ thống đã ghép, và khối ghi chú đọc trước tin đầu), `POST /api/agents/reload` |
| Tool & kết nối | `GET /api/tools`, `GET /api/connections` |
| Máy chủ MCP | `GET /api/mcp`, `POST …/{name}/reconnect`, `POST/DELETE …/{name}/login` (bắt đầu đăng nhập chỉ từ `localhost`/`127.0.0.1`; đăng xuất), `GET /api/mcp/oauth/callback` (đường duy nhất nhận một lượt điều hướng từ trang khác); không bao giờ trả giá trị header hay token |
| Khoá & biến môi trường | `GET /api/credentials`, `PUT/DELETE …/{name}` (ghi `<home>/env`, áp dụng ngay), `POST …/{name}/check`; không trả giá trị bí mật; thay đổi làm đội không chạy được bị từ chối 409, không ghi gì |
| Tuyến mô hình chung | `PUT /api/connections/routes` (lưu vào `config.yaml` giữ chú thích; khi `MY_AGENT_ROUTES` đặt thì chỉ xem, không sửa) |
| Trí nhớ agent | `GET/PUT /api/agents/{id}/memory`, `GET/PUT …/memory/notes/{day}`, `POST …/memory/consolidate` |
| Wiki | `GET /api/agents/{id}/memory/wiki`, `GET/PUT/DELETE …/wiki/pages/{slug}`, `GET …/wiki/report`, `POST …/wiki/compile` |
| Trí nhớ người dùng | `GET/PUT /api/memory/user`, `…/user/facts/{name}`, `GET /api/memory/proposals[/{id}]`, `GET /api/memory/search` |
| Job | `GET /api/jobs` (mỗi dòng mang `kind`: `prompt`, `command`, `script` hay `consolidate`, và luôn có đủ bốn khoá `prompt`, `command`, `script`, `then_prompt`, cái nào không dùng thì `null`; khoá `failing` là `null`, hoặc số lần hỏng liên tiếp của job cùng lúc bắt đầu, lúc chủ được báo và lúc tin nhắc kế tiếp), `GET …/{id}/runs`, `PATCH …/{id}/state` (tạm dừng/chạy lại), `POST …/{id}/run`, `DELETE …/{id}` (chỉ job `origin: "chat"`, tạo qua `schedule_create`) |
| Cài đặt | `GET /api/settings` |

Mọi đường không phải `/api/*` trả SPA. Web định tuyến bằng hash, nên một lượt chạy có đường
riêng: `#/manage/activity/<run_id>` mở đúng lượt đó, tải lại vẫn ở đó, và chia sẻ được.

## 4. Web `web/`

| Thư mục | Nội dung |
|---|---|
| `src/api/` | client HTTP, đọc SSE, kiểu dữ liệu |
| `src/screens/` | hai màn: chat và quản lý (mười mục, trong đó Canvas là thư viện mọi canvas và trang riêng của từng canvas ở `#/manage/canvas/<id>`) |
| `src/hooks/` | tải và giữ trạng thái từng mảng: hội thoại, luồng chat của cuộc đang mở, hoạt động và lịch sử run đã lưu, agent và bản nháp của trình sửa agent (kèm các kiểm tra trước khi gửi và id của từng lịch), trí nhớ, wiki, kết nối, route hash, phím tắt; cùng những mảnh nhỏ của màn hình: cuộc nào đã xem tới đâu, bản nháp của từng cuộc, đồng hồ cho nhãn thời gian tương đối, số việc chờ trên tiêu đề tab và badge app, tải lại cuộc đang mở khi kênh khác chạy trong nó, yêu cầu mà một run chờ duyệt đang giữ, run do một nút trên màn vừa khởi chạy, canvas agent đang viết nào hiện ở dock và khi nào nó nhường chỗ (`use-canvas-writing.ts`), thiết bị này có xem trước canvas đang viết hay không (`use-live-preview.ts`), dò bản build mới, và trình duyệt của một agent như nó đang chạy, đọc lại mỗi 5 giây khi trang đang được xem, cùng việc dừng nó, đóng một tab, mở và đóng cửa sổ đăng nhập (`use-agent-browser.ts`), và luật đọc ô host của trình sửa (`browser-hosts.ts`); desktop của một agent như trình trợ giúp nói về máy, cùng lần chụp thử |
| `src/state/` | reducer cho luồng chat và hoạt động; các canvas model còn đang viết trong lượt (`writing-previews.ts`) |
| `src/components/` | mọi thành phần giao diện, mỗi mảng quản lý một nhóm; `canvas/` giữ panel, dock, thư viện, trang riêng, dòng canvas trên thẻ giao việc, thẻ cùng khung chỉ đọc của canvas agent còn đang viết (`canvas-writing-card.tsx`, `canvas-writing-view.tsx`), và công tắc tắt việc xem trước ấy ở mục Cài đặt (`live-preview-setting.tsx`); `script-calls.tsx` vẽ danh sách lời gọi của một script và dòng hai số đo, dùng chung cho thẻ run và thẻ tool trong khung chat; phần trình duyệt của agent gồm thẻ của máy ở mục Kết nối (`connections-browser-card.tsx`), mức dùng và danh sách host trong trình sửa (`agent-editor/browser-controls.tsx`), thẻ các tab đang mở trên trang agent (`agent-editor/browser-card.tsx`), trong thẻ ấy là nút mở cửa sổ đăng nhập (`agent-editor/browser-login.tsx`) và danh sách nơi có thể còn đăng nhập (`agent-editor/browser-signed-in.tsx`), và ảnh nhỏ của một lần chụp (`screenshot-thumb.tsx`); phần desktop gồm thẻ của máy ở mục Kết nối với nút xin quyền, mức và danh sách ứng dụng trong trình sửa, thẻ desktop trên trang agent với nút chụp thử, câu và ảnh có dấu điểm trên thẻ duyệt `computer_act`, và ảnh của `computer_screenshot` trên bước của run và thẻ tool |
| `src/lib/` | hàm thuần dùng chung: diff dòng, tiến độ run và câu tóm tắt vì sao run dừng, kết quả giao việc, lọc lịch sử run, các run đã bấm "Đã xem", thời gian tương đối theo lịch của người xem, cron đọc thành chữ, định dạng token và cache, xuất cuộc trò chuyện ra Markdown, lọc lệnh `/`, link `[[…]]` của wiki, đọc đối số JSON chưa đóng của một lời viết canvas, luật chung cho lời gọi của script dù chúng tới qua step của run, sự kiện của lượt hay kết quả đã lưu (`nested-calls.ts`), lớp bọc `localStorage` mà mọi thứ trình duyệt nhớ đều đi qua, một lời gọi `browser_*` chờ duyệt đọc thành một câu (`browser-call.ts`), và đường dẫn ảnh trong dòng đầu của `browser_screenshot` (`screenshot-path.ts`); một lời gọi `computer_act` chờ duyệt đọc thành một câu, và ảnh cùng `frame_id` đọc từ câu trả lời của `computer_screenshot` |
| `src/i18n/` | mọi chuỗi tiếng Việt của web: `vi.ts` gom các tệp theo vùng ở `vi/` thành một đối tượng `vi` |
| `src/styles/` | CSS theo mảng, mỗi tệp tối đa 200 dòng, `styles.css` liệt kê chúng theo thứ tự áp dụng; `tokens.css` giữ thang chữ, khoảng cách và màu sáng, `tokens-preferences.css` giữ màu tối và phần giảm chuyển động |
| `public/` | favicon, icon cài app và manifest, chép nguyên vào gốc bundle |
| `scripts/` | `render-icons.mjs`: vẽ các PNG icon từ `public/favicon.svg` |
| `e2e/` | spec Playwright + mock `/api`; `live-stream.ts` giữ một lượt còn mở để spec đẩy từng event vào |

Script: `dev`, `typecheck`, `test` (vitest), `bundle` (build → `my_agent_crew/server/static`), `e2e`,
`icons` (vẽ lại icon sau khi sửa logo).

## 5. Test

Ba tầng (pytest, vitest, Playwright) và cách chạy ở [testing.md](testing.md). Provider giả
`MY_AGENT_ROUTES=fake:echo` cho phép chạy cả harness không cần mạng.

## 6. Trình trợ giúp desktop `desktop-helper/`

Một gói Swift riêng cho macOS, dựng thành ứng dụng không biểu tượng chạy trong phiên đăng nhập của
chủ, là thứ duy nhất giữ hai quyền Ghi màn hình và Trợ năng; server nói chuyện với nó qua một Unix
socket. Gói tách hai phần: thư viện lõi giữ mọi luật (socket, giao thức, điều kiện của máy, khung
hình, dàn ý, thao tác) và chỉ chạm máy qua một giao diện, nên test chạy trên một hệ thống giả và
không bao giờ bật hộp thoại; phần chạy được nối giao diện ấy vào máy thật.
`scripts/desktop-helper-check.sh` dựng và chạy test, `scripts/desktop-helper-pack.sh` đóng gói và
ký ad-hoc; cài đặt ở [deployment-guide.md](deployment-guide.md#4c-desktop-cho-agent-tuỳ-chọn-macos).

## 7. Mẫu agent và skill có sẵn

- `agents/templates/`: `fullstack-developer`, `kongming`, `researcher`, và `_shared_skills/` dùng chung.
- `skills/builtin/`: `cite-sources`.

Cài bằng `python -m my_agent_crew agent add <template> [--id <id>] [--force] [--workspace <dir>]` hoặc `POST /api/agents/install`. Cả hai đi qua `agents/templates_cli.py`; phần kiểm trước khi ghi và trả lại home khi lần cài bị từ chối ở `server/agent_install.py`.

## 8. Bộ tài liệu

| Tệp | Cho ai |
|---|---|
| [index.md](index.md) | điểm vào, thứ tự đọc |
| [system-architecture.md](system-architecture.md) | người mới, giải phẫu harness với 5 sơ đồ |
| [codebase-summary.md](codebase-summary.md) | định hướng theo gói trước khi mở code |
| [deployment-guide.md](deployment-guide.md) | người cài và vận hành, cách publish doc |
| [project-overview-pdr.md](project-overview-pdr.md) | vấn đề, phạm vi, tiêu chí |
| [code-standards.md](code-standards.md) | quy ước code, test, commit, bí mật, tài liệu |
| [CHANGELOG.md](../CHANGELOG.md) | thay đổi của từng bản phát hành |
| [design.md](design.md), [agents.md](agents.md), [tools.md](tools.md), [memory.md](memory.md), [channels.md](channels.md), [canvas.md](canvas.md), [testing.md](testing.md) | tham chiếu từng mảng |
| [diagrams/](diagrams/README.md) | spec, HTML, SVG của 5 sơ đồ |

## Câu hỏi mở

- `server/static/` được commit và CI kiểm `git diff --exit-code` sau `bundle`; khi web đổi nhiều, diff commit sẽ lớn — chưa quyết có chuyển sang build lúc cài hay không.
