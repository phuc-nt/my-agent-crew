---
layout: default
title: Cài đặt, vận hành và publish tài liệu
---

# Cài đặt, vận hành và publish tài liệu

**Phiên bản**: 0.5.0 · **Cập nhật**: 2026-09-23

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

Thử không tốn tiền: `MY_AGENT_ROUTES=fake:echo uv run python -m my_agent_crew`; gõ `/tool workspace_list` để thấy vòng lặp tool chạy qua provider giả.

## 3. Home và các tệp cần biết

```
~/.my-agent-crew/
├── config.yaml        # routes, cost_cap_usd, max_steps, language, timezone, autonomous_default, approval_ttl_seconds
├── env                # KEY=value, chmod 600, KHÔNG nằm trong repo
├── agent.yaml         # master
├── agent.sqlite3
├── users/owner/       # USER.md + facts/
├── skills/            # skill dùng chung
├── .agents/           # kit dùng chung (commands, agents, skills, settings.json)
├── workspace/inbox/   # ảnh từ Telegram
└── agents/<id>/       # mỗi agent một thư mục, xem agents.md
```

Đổi home bằng `MY_AGENT_HOME`. Mỗi lần thử nghiệm nên trỏ `MY_AGENT_HOME` sang thư mục tạm thay vì đụng home thật.

## 4. Biến môi trường và bí mật

| Biến | Ý nghĩa |
|---|---|
| `MY_AGENT_HOME` | thư mục home |
| `MY_AGENT_ROUTES` | danh sách model, ví dụ `openrouter:a,openrouter:b` hoặc `fake:echo` |
| `MY_AGENT_COST_CAP_USD`, `MY_AGENT_MAX_STEPS`, `MY_AGENT_AUTONOMOUS`, `MY_AGENT_APPROVAL_TTL_SECONDS`, `MY_AGENT_TIMEZONE` | ghi đè `config.yaml` |
| `OPENROUTER_API_KEY` | bắt buộc trừ khi dùng `fake:` |
| `TAVILY_API_KEY` / `BRAVE_API_KEY` | nguồn tìm kiếm trả phí cho `web_search` (không có vẫn chạy bằng DuckDuckGo) |
| `FIRECRAWL_BASE_URL` | host firecrawl, ví dụ `http://127.0.0.1:3002`; bật tìm kiếm + scrape markdown |
| `FIRECRAWL_API_KEY` | chỉ cần cho firecrawl cloud; host tự dựng để trống |
| tên do `telegram.token_env` trong `agent.yaml` chỉ định | token bot |

Server tự nạp `<home>/env` lúc khởi động; biến đã có sẵn trong môi trường tiến trình thắng giá trị trong tệp.

**Quản lý từ web.** Quản lý → **Kết nối** liệt kê các khoá theo việc chúng phục vụ (mô hình, tìm kiếm, Telegram, biến khác): đã đặt hay chưa, đặt từ tệp hay từ môi trường tiến trình. Đặt/Thay ghi vào `<home>/env` (chmod 600, giá trị bọc nháy đơn nên `source` an toàn, không nhận xuống dòng) rồi dựng lại provider, nguồn tìm kiếm và kênh Telegram ngay — không cần khởi động lại. **Kiểm tra** gọi thử OpenRouter, Telegram `getMe`, Ollama, Firecrawl. **Xoá** chỉ gỡ được giá trị nằm trong tệp; giá trị do môi trường tiến trình cấp phải gỡ ở nơi khởi động server. Trước khi ghi, server dựng thử cả đội với giá trị mới; nếu đội không chạy được (vd. xoá khoá duy nhất mà route cần) thì từ chối (409) và tệp giữ nguyên. Bot Telegram chỉ dựng lại khi token hay `chat_id` của nó đổi; đổi khoá khác không cắt tin đang trả lời. Giá trị chỉ đi một chiều: API (`/api/credentials`) không bao giờ trả khoá bí mật về, chỉ trả địa chỉ host (mật khẩu trong URL bị che).

**Chỉ nhận request cục bộ.** Mọi đường dẫn (API lẫn trang) từ chối (403) request có `Host` không phải `localhost` hay địa chỉ IP, hoặc `Origin` khác đúng host:port đang gọi (kể cả trang local ở cổng khác) — để trang web lạ trỏ tên miền về 127.0.0.1 (DNS rebinding) không đọc hay sửa được đội. Mở UI qua tên máy (vd. Tailscale MagicDNS) thì thêm tên đó vào `MY_AGENT_ALLOWED_HOSTS` (phân cách dấu phẩy) trong môi trường khởi động server; truy cập bằng IP không cần.

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
<key>StandardOutPath</key><string>…/logs/server.log</string>
```

Lệnh hay dùng:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.my-agent-crew.server.plist
launchctl kickstart -k gui/$(id -u)/com.my-agent-crew.server   # khởi động lại sau khi pull
curl -s http://127.0.0.1:8765/api/health
```

Linux: systemd user unit với `ExecStart=/bin/zsh …/run-server.zsh`, `Restart=always`.

## 6. Nâng cấp

```bash
cd my-agent-crew && git pull && uv sync
launchctl kickstart -k gui/$(id -u)/com.my-agent-crew.server
```

Schema SQLite tự thêm cột/bảng khi khởi động; không có bước migrate tay. Đọc `docs/agents.md` khi nâng phiên bản lớn vì bố cục persona có thể đổi.

Bản này khác bản trước ở đâu: [CHANGELOG.md](../CHANGELOG.md).

## 6b. Phát hành một phiên bản

Dự án phát hành bằng **tag git có chú thích**, không dựng GitHub Release và không đẩy lên PyPI —
người dùng cài bằng cách clone rồi `uv sync`, nên tag là đủ để trỏ tới một trạng thái code.

**Số hiệu** theo SemVer, và **một số dùng chung cho cả backend lẫn web**:

| Loại | Khi nào | Ví dụ ở dự án này |
|---|---|---|
| major | đổi vỡ: lược đồ cần migrate tay, bỏ endpoint, đổi hình dạng `config.yaml`/`agent.yaml` | chưa có |
| minor | thêm tính năng, thêm endpoint, đổi lớn ở UI mà dữ liệu cũ vẫn chạy | v0.4.0 — web UI dựng lại, 8 endpoint mới, bảng mới đều `IF NOT EXISTS` |
| patch | chỉ sửa lỗi và tài liệu | — |

### Các bước

```bash
# 1. Cổng: chạy đủ chín cổng ở code-standards §4. Không tag khi còn một cổng đỏ.

# 2. Nâng số ở năm chỗ — phải khớp nhau
#    pyproject.toml · my_agent_crew/__init__.py · web/package.json
#    + dòng "**Phiên bản**" ở sáu tài liệu chuẩn trong docs/
grep -rn '"\?version"\?[ =:]' pyproject.toml my_agent_crew/__init__.py web/package.json
grep -rn '^\*\*Phiên bản\*\*' docs/*.md

# 3. Viết mục mới trong CHANGELOG.md: Thêm / Đổi / Sửa / Lưu ý khi nâng cấp
#    Nguồn là `git log --oneline vX.Y.Z..HEAD`, nhưng viết theo giá trị cho người dùng,
#    không chép nguyên commit message.

# 4. Commit rồi đẩy — để CI chạy thật trước khi tag
git add -A && git commit -m "chore(release): v0.4.0"
git push origin main

# 5. Đợi CI xanh. Chỉ tag khi đã xanh: tag trỏ vào commit đỏ là thứ khó gỡ.
gh run watch

# 6. Tag có chú thích (ba tag cũ đều là annotated — giữ cho đồng nhất)
git tag -a v0.4.0 -m "v0.4.0 — web UI dựng lại quanh việc nhìn thấy agent đang làm gì"
git push origin v0.4.0
```

**Không nên**: tag trước khi push (tag trỏ tới commit chưa ai thấy); tag khi CI đang đỏ; nâng số
ở `pyproject.toml` mà quên `web/package.json` (hai bên lệch nhau là thứ không có test nào bắt được).

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
- Số liệu test trong [codebase-summary.md](codebase-summary.md) khớp `uv run pytest -q` và `npm test`.

## Câu hỏi mở

- Chưa có Dockerfile; người dùng Linux hiện tự viết unit systemd.
- GitHub Pages với Jekyll bỏ qua thư mục bắt đầu bằng `_`; `docs/diagrams/` không bị ảnh hưởng nhưng cần nhớ nếu sau này thêm thư mục con.
