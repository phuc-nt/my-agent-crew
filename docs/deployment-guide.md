---
layout: default
title: Cài đặt, vận hành và publish tài liệu
---

# Cài đặt, vận hành và publish tài liệu

**Phiên bản**: 0.3.0 · **Cập nhật**: 2026-09-22

## 1. Yêu cầu

- macOS hoặc Linux, Python 3.12+, [uv](https://docs.astral.sh/uv/).
- Node 20+ chỉ khi sửa web (bundle đã commit sẵn).
- Một API key OpenRouter. Tuỳ chọn: token bot Telegram, key Tavily hoặc Brave cho `web_search`.

## 2. Cài và chạy lần đầu

```bash
git clone <repo> my-agent-crew && cd my-agent-crew
uv sync
export OPENROUTER_API_KEY=…      # hoặc để trong tệp env, xem §4
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
| `TAVILY_API_KEY` / `BRAVE_API_KEY` | `web_search` |
| tên do `telegram.token_env` trong `agent.yaml` chỉ định | token bot |

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

## 7. Thêm agent

```bash
uv run python -m my_agent_crew agent list-templates
uv run python -m my_agent_crew agent add reviewer            # → agents/reviewer/
uv run python -m my_agent_crew agent add dev --id pong --workspace ~/workspace/x
```

Sau đó sửa `agents/<id>/agent.yaml` (`routes`, `tools`, `schedules`, `autonomous`) và persona (`AGENTS.md`, `SOUL.md`). Thêm id vào `delegates:` của master để master thấy trong roster. Khởi động lại server.

## 8. Telegram

1. Tạo bot với BotFather, ghi token vào tệp env dưới tên tuỳ chọn.
2. Trong `agent.yaml` của master:
   ```yaml
   telegram:
     token_env: TELEGRAM_BOT_TOKEN
     chat_id: <id chat của bạn>
   ```
3. Khởi động lại; poller bắt đầu. Chỉ chat từ `chat_id` được nhận. Xem [channels.md](channels.md).

## 9. Publish bộ doc để sơ đồ archify chuyển động

Sơ đồ `.html` trong `docs/diagrams/` là trang tự chứa: script, style, animation đều inline. Markdown không nhúng được HTML có script, nên bộ doc dùng hai lớp: SVG tĩnh nhúng trong `.md`, và link "bản động" tới `.html`. Bản động chỉ chạy khi `docs/` được phục vụ như **site tĩnh** — mọi cách dưới đây đều làm được vì không cần build gì.

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

**Nhúng vào trang khác**: `<iframe src="diagrams/crew-architecture.html" width="100%" height="760"></iframe>`.

**Không nên**: mở `.html` bằng `file://` từ một số trình duyệt chặn script cục bộ; dán nội dung `.html` vào `.md`; đổi tên `.svg` mà không sửa link trong `.md` và `index.html`.

**Tái tạo sơ đồ**: sửa `.json`, chạy validate → deliver → to-svg theo [diagrams/README.md](diagrams/README.md), xoá artifact `*.visual-check.*`.

## 10. Kiểm tra bộ doc

- Link nội bộ: mở `docs/diagrams/index.html` qua http.server, bấm cả 5 "Mở bản động".
- Không có bí mật hoặc dữ liệu cá nhân trong `docs/`: grep theo tiền tố key OpenRouter, dạng token bot Telegram, chat id, đường dẫn home cá nhân phải rỗng.
- Số liệu test trong [codebase-summary.md](codebase-summary.md) khớp `uv run pytest -q` và `npm test`.

## Câu hỏi mở

- Chưa có Dockerfile; người dùng Linux hiện tự viết unit systemd.
- GitHub Pages với Jekyll bỏ qua thư mục bắt đầu bằng `_`; `docs/diagrams/` không bị ảnh hưởng nhưng cần nhớ nếu sau này thêm thư mục con.
