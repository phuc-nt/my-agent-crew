---
layout: default
title: Cài đặt, vận hành và publish tài liệu
---

# Cài đặt, vận hành và publish tài liệu

**Phiên bản**: 0.12.0 · **Cập nhật**: 2026-10-07

## 1. Yêu cầu

- macOS hoặc Linux, Python 3.12+, [uv](https://docs.astral.sh/uv/).
- Node 20+ chỉ khi sửa web (bundle đã commit sẵn).
- Một API key OpenRouter. Tuỳ chọn: token bot Telegram, một host firecrawl, hoặc key Tavily/Brave
  để `web_search` chạy nhanh hơn — không có gì thêm thì vẫn tìm được qua DuckDuckGo.

## 2. Cài và chạy lần đầu

```bash
git clone <repo> my-agent-crew && cd my-agent-crew
uv sync
export OPENROUTER_API_KEY=…      # hoặc đặt sau trong web: Quản lý → Kết nối, xem §4
uv run python -m my_agent_crew   # http://127.0.0.1:8765
```

Lần chạy đầu tạo home `~/.my-agent-crew/` với `config.yaml`, `agent.sqlite3`, `agent.yaml` cho master và `users/owner/`. Mở trình duyệt, gõ một câu, xem run xuất hiện ở panel hoạt động.

Thử không tốn tiền: `MY_AGENT_ROUTES=fake:echo uv run python -m my_agent_crew`; gõ `/tool workspace_list` để thấy vòng lặp tool chạy qua provider giả. Đổi thành `MY_AGENT_ROUTES=fake:slow` thì cùng provider giả ấy chờ 0,1 giây giữa hai mảnh, để nhìn câu trả lời và đối số của lời gọi tool tới dần. Máy đang có một crew chạy trên home mặc định thì lệnh này dừng ngay với lời báo home đang có một server khác chạy (xem §3): cho lần thử một home và một cổng riêng, ví dụ `MY_AGENT_HOME=/tmp/crew-thu MY_AGENT_ROUTES=fake:echo uv run python -m my_agent_crew --port 8799`.

## 3. Home và các tệp cần biết

```
~/.my-agent-crew/
├── config.yaml        # routes, cost_cap_usd, max_steps, language, timezone, web_url, autonomous_default, approval_ttl_seconds, mcp_servers
├── env                # KEY=value, chmod 600, KHÔNG nằm trong repo; token đăng nhập MCP cũng ghi ở đây
├── agent.yaml         # master
├── agent.sqlite3
├── users/owner/       # USER.md + facts/
├── skills/            # skill dùng chung
├── .agents/           # kit dùng chung (commands, agents, skills, settings.json)
├── workspace/inbox/   # ảnh từ Telegram
└── agents/<id>/       # mỗi agent một thư mục, xem agents.md
```

Đổi home bằng `MY_AGENT_HOME`. Mỗi lần thử nghiệm nên trỏ `MY_AGENT_HOME` sang thư mục tạm thay vì đụng home thật.

**Một home, một server.** Server giữ home của nó từ lúc khởi động tới khi tiến trình mất, dù tiến trình kết thúc thế nào. Lần khởi động thứ hai trên cùng home, dù ở cổng khác hay với `--no-schedule`, không đọc gì của home, nói home đang có một server khác chạy rồi thoát với mã 1. Trước đây một lần khởi động như vậy đóng các run của server đang chạy trong sổ rồi mới hỏng vì cổng đã bị chiếm. Các lệnh con `agent` không giữ home nên vẫn dùng được khi server đang lên. Home nằm trên hệ tệp không cho khoá thư mục thì server không khởi động và nói đúng lỗi của hệ thống.

`config.yaml` chỉ nhận những khoá nó biết; một khoá lạ làm server dừng lúc khởi động. Máy chủ MCP khai dưới `mcp_servers` không mang bí mật nào: giá trị header lấy từ biến môi trường, còn đăng nhập OAuth từ thẻ Kết nối ghi token vào `env` dưới tên `MCP_<MÁY_CHỦ>_ACCESS_TOKEN` và `MCP_<MÁY_CHỦ>_REFRESH_TOKEN`, kèm nơi đã cấp chúng (`MCP_<MÁY_CHỦ>_ISSUER`) và tên của crew ở nơi đó (`MCP_<MÁY_CHỦ>_CLIENT_ID`) ([tools.md](tools.md#máy-chủ-mcp)).

## 4. Biến môi trường và bí mật

| Biến | Ý nghĩa |
|---|---|
| `MY_AGENT_HOME` | thư mục home |
| `MY_AGENT_ROUTES` | danh sách model, ví dụ `openrouter:a,openrouter:b` hoặc `fake:echo` |
| `MY_AGENT_COST_CAP_USD`, `MY_AGENT_MAX_STEPS`, `MY_AGENT_AUTONOMOUS`, `MY_AGENT_APPROVAL_TTL_SECONDS`, `MY_AGENT_TIMEZONE` | ghi đè `config.yaml` |
| `MY_AGENT_WEB_URL` | ghi đè `web_url` của `config.yaml`: địa chỉ người dùng mở web, ví dụ `http://127.0.0.1:8765`, để tin gửi ra kênh viết được link về web. Chỉ nhận `http`/`https`, host, cổng và path trơn; có tên đăng nhập, query hay fragment có nội dung, khoảng trắng nằm giữa địa chỉ hay ký tự ẩn ở bất cứ đâu thì server dừng lúc khởi động, và câu lỗi không lặp lại giá trị. Khoảng trắng ở hai đầu, dấu `/` cuối và một dấu `?` hay `#` không có gì theo sau thì được bỏ đi, không làm server dừng. Host chỉ gồm chữ không dấu, số, `.`, `-`, `_` hoặc là địa chỉ IPv6 trong ngoặc vuông, nên tên miền có chữ ngoài ASCII phải viết ở dạng punycode (`xn--…`). Để trống thì không link nào được viết |
| `OPENROUTER_API_KEY` | bắt buộc trừ khi dùng `fake:` |
| `TAVILY_API_KEY` / `BRAVE_API_KEY` | nguồn tìm kiếm trả phí cho `web_search` (không có vẫn chạy bằng DuckDuckGo) |
| `FIRECRAWL_BASE_URL` | host firecrawl, ví dụ `http://127.0.0.1:3002`; bật tìm kiếm + scrape markdown |
| `FIRECRAWL_API_KEY` | chỉ cần cho firecrawl cloud; host tự dựng để trống |
| tên do `telegram.token_env` trong `agent.yaml` chỉ định | token bot |

Server tự nạp `<home>/env` lúc khởi động; biến đã có sẵn trong môi trường tiến trình thắng giá trị trong tệp.

**Quản lý từ web.** Quản lý → **Kết nối** liệt kê các khoá theo việc chúng phục vụ (mô hình, tìm kiếm, Telegram, biến khác): đã đặt hay chưa, đặt từ tệp hay từ môi trường tiến trình. Đặt/Thay ghi vào `<home>/env` (chmod 600, giá trị bọc nháy đơn nên `source` an toàn, không nhận xuống dòng) rồi dựng lại provider, nguồn tìm kiếm và kênh Telegram ngay — không cần khởi động lại. **Kiểm tra** gọi thử OpenRouter, Telegram `getMe`, Ollama, Firecrawl, Tavily (`/usage`, miễn phí, kèm số lượt đã dùng) và Brave (một lượt tìm 1 kết quả — nút ghi rõ "tốn 1 lượt tìm"); hết lượt (429) được báo khác với khoá sai. **Xoá** chỉ gỡ được giá trị nằm trong tệp; giá trị do môi trường tiến trình cấp phải gỡ ở nơi khởi động server. Trước khi ghi, server dựng thử cả đội với giá trị mới; nếu đội không chạy được (vd. xoá khoá duy nhất mà route cần) thì từ chối (409) và tệp giữ nguyên. Bot Telegram chỉ dựng lại khi token hay `chat_id` của nó đổi; đổi khoá khác không cắt tin đang trả lời. Giá trị chỉ đi một chiều: API (`/api/credentials`) không bao giờ trả khoá bí mật về, chỉ trả địa chỉ host (mật khẩu trong URL bị che).

**Tuyến mô hình chung** (tuyến agent không có tuyến riêng dùng, và tuyến agent có tuyến riêng quay về khi không tuyến nào của nó có khoá) sửa ở thẻ Tuyến mô hình cùng trang: thêm/bớt/sửa dòng rồi **Lưu tuyến**. Server từ chối (409) nhà cung cấp chưa có khoá, danh sách đội không chạy được, và `fake` (chỉ lặp lại tin nhắn) khi tuyến đang lưu chưa dùng nó, rồi mới ghi `routes` vào `<home>/config.yaml` kiểu round-trip (giữ chú thích và khoá khác) và áp dụng từ lượt kế tiếp. `/api/connections` trả `routes_source`: `env` khi `MY_AGENT_ROUTES` đang đặt — biến thắng tệp nên trang chỉ cho xem —, `config` hoặc `default`. Xoá khoá mà tuyến duy nhất cần bị từ chối kèm tên tuyến dạng `provider:model` và cách gỡ (thêm tuyến khác trước).

**Chỉ nhận request cục bộ.** Mọi đường dẫn (API lẫn trang) từ chối (403) request có `Host` không phải `localhost` hay địa chỉ IP, hoặc `Origin` khác đúng host:port đang gọi (kể cả trang local ở cổng khác) — để trang web lạ trỏ tên miền về 127.0.0.1 (DNS rebinding) không đọc hay sửa được đội. Mở UI qua tên máy (vd. Tailscale MagicDNS) thì thêm tên đó vào `MY_AGENT_ALLOWED_HOSTS` (phân cách dấu phẩy) trong môi trường khởi động server; truy cập bằng IP không cần. Trang 403 nêu đúng tên host bị từ chối và biến cần thêm, log server ghi tên đó một lần. `web_url` đi cùng hàng rào này: nếu nó dùng một tên máy thì tên đó cũng phải có trong `MY_AGENT_ALLOWED_HOSTS`, không thì link trong tin gửi ra kênh mở ra trang 403. Server không đối chiếu hai giá trị lúc khởi động, nên hãy bấm thử một link sau khi đặt.

**Không có đăng nhập.** Ai tới được cổng là điều khiển được đội: đọc hội thoại, sửa agent, đặt khoá, và `POST /api/inbound` chạy một lượt không cần xác thực (header `Origin` không có ở `curl` nên hàng rào Origin không chặn). Hàng rào Host chỉ chống trang web lạ trong trình duyệt, không phải kiểm soát truy cập. Vì vậy chỉ mở cổng trên máy hoặc trong tailnet riêng; đừng đưa ra ngoài bằng Tailscale Funnel, ngrok, Cloudflare Tunnel hay reverse proxy công khai — tên của đường hầm công khai cũng đừng thêm vào `MY_AGENT_ALLOWED_HOSTS`.

Quy tắc: bí mật chỉ nằm trong tệp env ngoài repo; `agent.yaml` chỉ ghi **tên** biến (`token_env: TELEGRAM_BOT_TOKEN`), không ghi giá trị. Log server đi qua bộ lọc redact nên token không xuất hiện trong `logs/`.

## 5. Chạy thường trực (launchd, macOS)

Bộ cài thật dùng một script và một plist:

```zsh
# ~/.my-agent-crew/run-server.zsh
set -a; source "$HOME/.my-agent-crew/env"; set +a
cd "$HOME/workspace/my-agent-crew"
exec uv run python -m my_agent_crew --host 127.0.0.1 --port 8765
```

```xml
<!-- ~/Library/LaunchAgents/com.my-agent-crew.server.plist -->
<key>ProgramArguments</key><array><string>/bin/zsh</string><string>…/run-server.zsh</string></array>
<key>KeepAlive</key><true/>
<key>ExitTimeOut</key><integer>45</integer>
<key>StandardOutPath</key><string>…/logs/server.log</string>
```

`ExitTimeOut` phải dài hơn thời gian bot chờ khi dừng (30 s cho lượt đang chạy + 5 s cho lời
báo "tin bị ngắt"). Mặc định của launchd là 20 s, nên thiếu khoá này thì một lần `kickstart -k`
giữa lượt dài sẽ SIGKILL trước khi người gửi được báo.

Lệnh hay dùng:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.my-agent-crew.server.plist
launchctl kickstart -k gui/$(id -u)/com.my-agent-crew.server   # khởi động lại sau khi pull
curl -s http://127.0.0.1:8765/api/health
```

Dịch vụ là server duy nhất của home đó. Chạy tay một server thứ hai trên cùng home thì bị từ chối; ngược lại, dịch vụ gặp home đang do một server chạy tay giữ thì thoát mã 1 và được launchd dựng lại cho tới khi server kia dừng.

Linux: systemd user unit với `ExecStart=/bin/zsh …/run-server.zsh`, `Restart=always`.

## 6. Nâng cấp

```bash
cd my-agent-crew && git pull && uv sync
launchctl kickstart -k gui/$(id -u)/com.my-agent-crew.server
```

Schema SQLite tự thêm cột/bảng khi khởi động; không có bước migrate tay. Đọc `docs/agents.md` khi nâng phiên bản lớn vì bố cục persona có thể đổi.

**Lượt đang chạy lúc khởi động lại được làm tiếp một lần.** `kickstart -k` giữa một lượt cắt lượt đó: lượt web bị cắt ngay, lượt Telegram được chờ tối đa 30 s rồi chat nhận lời báo sẽ làm tiếp ([channels.md](channels.md#offset-và-restart)). Server khởi động kế tiếp mở lại đúng run đó, cùng số tiền đã tiêu và dưới cùng trần chi phí, rồi chạy tiếp từ nhật ký; tool chỉ đọc được gọi lại, còn lệnh gọi nào có thể đã chạy mà đổi trạng thái thì được đóng bằng một ghi chú "không rõ đã chạy hay chưa" để model tự kiểm, không chạy lại ngầm. Lượt đang chờ một quyết định thì vẫn chờ quyết định đó; lượt của cuộc đã hết ngân sách, đã có lượt mới hơn, hoặc đã từng được làm tiếp một lần thì ở lại trạng thái bị ngắt. Chi tiết ở [design.md](design.md#hình-dạng-runtime). Vẫn nên khởi động lại lúc không có lượt nào đang chạy khi chọn được. Server chạy với `--no-schedule` không làm tiếp lượt nào và đóng hẳn những lượt bị cắt, nên dùng cờ đó khi cần xem dữ liệu sau một lần sập mà không muốn lượt cũ chạy tiếp (dừng dịch vụ trước, vì một home chỉ nhận một server mỗi lúc).

**Sao lưu `agent.sqlite3` trước.** Schema chỉ đi một chiều: bản mới thêm bảng và cột (canvas thêm bốn bảng và ba cột, xem [system-architecture.md](system-architecture.md#28-canvas-tài-liệu-người-và-agent-cùng-sửa); bản 0.12.0 thêm bảng `message_requests` và ba cột `runs.resumed`, `messages.turn_notes`, `queued_messages.request_id`) và không có bước lùi. Tệp chạy ở chế độ WAL, nên chép tệp bằng `cp` khi server đang chạy có thể thiếu những lần ghi còn nằm trong tệp `-wal`. Dùng API backup của SQLite, mở nguồn chỉ đọc bằng `mode=ro` (đừng dùng `immutable=1` trên tệp đang chạy):

```bash
mkdir -p "$HOME/.my-agent-crew/backups/truoc-nang-cap"
python3 - <<'EOF'
import os, sqlite3
home = os.path.expanduser("~/.my-agent-crew")
src = sqlite3.connect(f"file:{home}/agent.sqlite3?mode=ro", uri=True)
dst = sqlite3.connect(f"{home}/backups/truoc-nang-cap/agent.sqlite3")
src.backup(dst)
dst.close(); src.close()
EOF
```

Kiểm bản sao bằng cách mở nó bình thường và chạy `PRAGMA integrity_check`; mở bản sao ở chế độ chỉ đọc có thể báo lỗi dù bản sao vẫn tốt.

**Sau khi khởi động lại, tải lại các tab đang mở.** Tab mở từ trước vẫn chạy bản web cũ cho tới khi tải lại; thanh "Có bản mới" mời tải lại chứ không ép.

**Agent có danh sách `tools:`.** Agent khai `tools:` trong `agent.yaml` chỉ có đúng những tool nó liệt kê, nên muốn nó dùng canvas thì thêm tên các tool canvas vào danh sách ([canvas.md](canvas.md#6-bảy-tool-của-agent)); agent không khai `tools:` thì có sẵn. Cuộc trò chuyện giao việc đã mở từ trước lần nâng cấp không có kênh gốc được ghi lại, nên agent con trong đó không ghi được canvas ([canvas.md](canvas.md#7-phạm-vi-và-kênh)).

Bản này khác bản trước ở đâu: [CHANGELOG.md](../CHANGELOG.md).

## 6b. Phát hành một phiên bản

Dự án phát hành bằng **tag git có chú thích kèm một GitHub Release**, không đẩy lên PyPI —
người dùng cài bằng cách clone rồi `uv sync`, nên tag là thứ trỏ tới một trạng thái code, còn
Release là chỗ người theo dõi repo đọc bản đó có gì (ghi chú chép từ mục của bản đó trong
CHANGELOG).

**Số hiệu** theo SemVer, và **một số dùng chung cho cả backend lẫn web**:

| Loại | Khi nào | Ví dụ ở dự án này |
|---|---|---|
| major | đổi vỡ: lược đồ cần migrate tay, bỏ endpoint, đổi hình dạng `config.yaml`/`agent.yaml` | chưa có |
| minor | thêm tính năng, thêm endpoint, đổi lớn ở UI mà dữ liệu cũ vẫn chạy | v0.4.0 — web UI dựng lại, 8 endpoint mới, bảng mới đều `IF NOT EXISTS` |
| patch | chỉ sửa lỗi và tài liệu | — |

### Các bước

```bash
# 1. Cổng: mọi cổng CI trong một lệnh (testing.md, mục Chạy các cổng). Không tag khi còn một
#    cổng đỏ.
./scripts/gates.sh

# 2. Bản minor: chạy bộ kiểm thử hành vi bằng model thật (tốn tiền thật; testing.md, mục Kiểm
#    thử hành vi bằng model thật). Ca trượt vì lỗi runtime thì sửa trước khi phát hành; ca
#    trượt vì persona là một phát hiện, không chặn phát hành.
uv run python scripts/run_evals.py --runs 3 --max-usd 0.5

# 3. Nâng số ở mọi chỗ ghi phiên bản — phải khớp nhau:
#    pyproject.toml · my_agent_crew/__init__.py · uv.lock (mục my-agent-crew)
#    web/package.json · web/package-lock.json (hai dòng đầu có "version")
#    + dòng "**Phiên bản**" ở mọi tài liệu trong docs/ có dòng này
grep -n 'version' pyproject.toml my_agent_crew/__init__.py web/package.json
grep -n -A1 'name = "my-agent-crew"' uv.lock
grep -n -m2 '"version"' web/package-lock.json
grep -rn '^\*\*Phiên bản\*\*' docs/*.md
uv lock --check        # uv.lock khớp pyproject.toml chưa; CI chạy `uv sync` nên không bắt lệch

# 4. Viết mục mới trong CHANGELOG.md: Added / Changed / Fixed / Upgrade notes, thêm link ref
#    của bản mới ở cuối tệp và để lại một mục [Unreleased] trống ở trên cùng.
#    Nguồn là `git log --oneline vX.Y.Z..HEAD`, nhưng viết theo giá trị cho người dùng,
#    không chép nguyên commit message.

# 5. Commit rồi đẩy — để CI chạy thật trước khi tag
git add -A && git commit -m "chore(release): v0.12.0"
git push origin main

# 6. Đợi CI xanh. Chỉ tag khi đã xanh: tag trỏ vào commit đỏ là thứ khó gỡ.
gh run watch

# 7. Tag có chú thích (mọi tag cũ đều là annotated — giữ cho đồng nhất)
git tag -a v0.12.0 -m "v0.12.0"
git push origin v0.12.0

# 8. GitHub Release: ghi chú là mục của bản này trong CHANGELOG (bỏ dòng tiêu đề), cộng một
#    dòng kết quả eval nếu đã chạy — chỉ số ca đạt và chi phí, không nội dung ca.
gh release create v0.12.0 --title "v0.12.0 — <một câu nói bản này làm gì>" --notes-file notes.md
```

**Không nên**: tag trước khi push (tag trỏ tới commit chưa ai thấy); tag khi CI đang đỏ; nâng số
ở `pyproject.toml` mà quên `web/package.json` (hai bên lệch nhau là thứ không có test nào bắt
được) hay `uv.lock` (chỉ `uv lock --check` bắt được).

## 7. Thêm agent

```bash
uv run python -m my_agent_crew agent list-templates
uv run python -m my_agent_crew agent add researcher          # → agents/researcher/
uv run python -m my_agent_crew agent add fullstack-developer --workspace ~/workspace/x
```

Sau đó sửa `agents/<id>/agent.yaml` (`routes`, `tools`, `schedules`, `autonomous`) và persona (`AGENTS.md`, `SOUL.md`). Thêm id vào `delegates:` của master để master thấy trong roster. Khởi động lại server.

## 8. Telegram

1. Tạo bot với BotFather, ghi token vào tệp env dưới tên tuỳ chọn (hoặc đặt ở Kết nối sau bước 2).
2. Trong `agent.yaml` của master:
   ```yaml
   telegram:
     token_env: TELEGRAM_BOT_TOKEN
     chat_id: <id chat của bạn>
   ```
3. Sửa từ web (Đội → agent chính → Telegram) thì kênh bật ngay; sửa tay `agent.yaml` thì khởi động lại. Poller bắt đầu. Chỉ chat từ `chat_id` được nhận. Xem [channels.md](channels.md).

## 9. Publish bộ doc để sơ đồ archify chuyển động

Sơ đồ `.html` trong `docs/diagrams/` là trang tự chứa: script, style, animation đều inline. Không dán nội dung đó vào `.md`; thay vào đó `.md` nhúng bằng `<iframe src="diagrams/<tên>.html">` — Jekyll giữ nguyên HTML thô trong markdown, nên sơ đồ chạy ngay trong trang tài liệu. Mỗi sơ đồ kèm link "Mở riêng" và "ảnh tĩnh" (SVG) để trang vẫn đọc được ở nơi iframe bị chặn (GitHub blob view, trình đọc markdown). Bản động chỉ chạy khi `docs/` được phục vụ như **site tĩnh** — mọi cách dưới đây đều làm được vì không cần build gì.

**Cách A — GitHub Pages từ `/docs`** (khuyến nghị)
Settings → Pages → Source: `main` / `/docs`. Front matter `layout: default` để Jekyll render `.md`; các `.html` và `.svg` được phục vụ nguyên vẹn. Link `diagrams/index.html` mở gallery với animation.

**Cách B — Site tĩnh bất kỳ** (Netlify, Cloudflare Pages, S3, Vercel static)
Trỏ thư mục publish vào `docs/`. Nếu site không render markdown, dùng gallery `diagrams/index.html` làm trang vào và đổi link `.md` thành `.html` bằng bộ render tuỳ chọn.

**Cách C — Máy cá nhân**
```bash
python3 -m http.server 8080 --directory docs
# http://localhost:8080/diagrams/index.html
```
Sơ đồ chạy đầy đủ, nhưng link `.md` giữa các tài liệu không mở được vì không có Jekyll rewrite `.md` → `.html`; dùng cách này để xem sơ đồ, cách A để đọc cả bộ.

**Chiều cao iframe**: trang sơ đồ cao hơn viewBox vì có tiêu đề, thanh view, chú giải và thẻ; đo thật bằng `document.documentElement.scrollHeight` rồi đặt `height` hơn số đo một chút. Bộ doc này dùng 1090–1390 px tuỳ sơ đồ.

**Không nên**: mở `.html` bằng `file://` từ một số trình duyệt chặn script cục bộ; dán nội dung `.html` vào `.md`; đổi tên `.svg` mà không sửa link trong `.md` và `index.html`.

**Tái tạo sơ đồ**: sửa `.json`, chạy validate → deliver → to-svg theo [diagrams/README.md](diagrams/README.md), xoá artifact `*.visual-check.*`.

## 10. Kiểm tra bộ doc

- Link nội bộ: mở `docs/diagrams/index.html` qua http.server, bấm cả 5 "Mở bản động".
- Không có bí mật hoặc dữ liệu cá nhân trong `docs/`: grep theo tiền tố key OpenRouter, dạng token bot Telegram, chat id, đường dẫn home cá nhân phải rỗng.
- Tài liệu không kể tên tệp, hàm, hằng hay tệp test của mã nguồn (xem [code-standards.md §7](code-standards.md#7-tài-liệu)): grep `\.py\b`, `\.tsx?\b`, `test_`, `MAX_[A-Z_]+` trong `docs/*.md` chỉ được trả về lệnh chạy, đường dẫn cấu hình và ví dụ người dùng.

## Câu hỏi mở

- Chưa có Dockerfile; người dùng Linux hiện tự viết unit systemd.
- GitHub Pages với Jekyll bỏ qua thư mục bắt đầu bằng `_`; `docs/diagrams/` không bị ảnh hưởng nhưng cần nhớ nếu sau này thêm thư mục con.
