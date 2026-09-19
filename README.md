# my-agent-crew

Một agent vạn năng, chạy local, có web UI thân thiện. Agent đọc/ghi tệp trong thư mục làm việc,
tải trang web, tìm kiếm, ghi nhớ — và **hỏi bạn trước** mọi thao tác thay đổi dữ liệu.

Đây là bản viết lại tinh gọn của [my-crew](https://github.com/phuc-nt/my-crew): bỏ đội nhiều vai,
router, DAG; giữ một agent + công cụ + kỹ năng, đặt web UI làm mặt tiền chính.

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
| `OPENROUTER_API_KEY` | bật provider OpenRouter | — |
| `TAVILY_API_KEY` / `BRAVE_API_KEY` | bật công cụ `web_search` | — |

`config.yaml` trong `MY_AGENT_HOME` nhận `routes`, `cost_cap_usd`, `max_steps`, `language`,
`autonomous_default`. Kỹ năng tự viết: thêm tệp `.md` có frontmatter `name` vào `skills/`.

## Nhiều agent có tên riêng

Mỗi thư mục `MY_AGENT_HOME/agents/<id>/` chứa `agent.yaml` cùng các tệp nhân cách
(`AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md`) và trí nhớ (`MEMORY.md`, `memory/YYYY-MM-DD.md`)
được nạp vào system prompt mỗi lượt. Ví dụ một huấn luyện viên sức khoẻ:

```yaml
name: HLV sức khoẻ
description: Đọc dữ liệu Garmin, gửi bản tin sáng
routes: [openrouter:z-ai/glm-5.3-flash, openrouter:z-ai/glm-5]
workspace: ~/workspace/my-health-coach   # sandbox cho công cụ tệp + shell_run
skills_dirs: [~/.openclaw/workspace-personal/skills]
autonomous: true                          # job chạy không cần duyệt
schedules:
  - id: morning-brief
    name: Bản tin sáng
    cron: "0 7 * * *"                     # giờ máy, 5 trường
    prompt: |
      Chạy scripts/health-sync.py --json rồi viết bản tin 4-6 dòng…
      Kèm ảnh bằng dòng `MEDIA: data/charts/sleep.png`.
  - id: backup
    name: Sao lưu Drive
    cron: "20 2 * * *"
    command: ./scripts/backup-to-drive.sh
```

Job `prompt` mở một cuộc trò chuyện mới và chạy như người dùng nhắn; job `command` chỉ chạy shell.
Bí mật vẫn chỉ đến từ biến môi trường của tiến trình server. Thư mục `agents/` là dữ liệu cá nhân,
không nằm trong repo này.

## Theo dõi hoạt động

Thanh **Hoạt động** bên phải web UI nhận SSE từ `/api/activity/stream`: mỗi lượt chat hay job
hiện thành một thẻ với từng bước (gọi model, gọi công cụ, kết quả, thời gian, chi phí), mục
**Cần chú ý** gom các lượt chờ duyệt / lỗi, tab **Lịch chạy** cho bấm *Chạy ngay*, tab **Chi phí**
theo agent / model / ngày. Dòng `MEDIA: <đường dẫn trong workspace>` trong câu trả lời được hiển
thị thành ảnh.

## Phát triển

```bash
uv run pytest -q                 # backend
cd web && npm ci
npm run typecheck && npm test    # frontend unit
npm run e2e                      # Playwright (mock /api trong trình duyệt)
npm run bundle                   # dựng lại bundle vào my_agent_crew/server/static (đã commit)
```

Đọc [docs/design.md](docs/design.md) để hiểu các quyết định thiết kế và
[docs/testing.md](docs/testing.md) để biết tính năng nào được test ở tầng nào.
