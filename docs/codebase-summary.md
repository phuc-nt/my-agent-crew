---
layout: default
title: Bản đồ mã nguồn
---

# Bản đồ mã nguồn

**Phiên bản**: 0.3.0 · **Cập nhật**: 2026-09-22

Đọc [system-architecture.md](system-architecture.md) trước để biết các khối là gì; tài liệu này chỉ nói khối nào nằm ở tệp nào.

## 1. Bố cục repo

```
my-agent-crew/
├── my_agent_crew/        # backend Python (~9.3k dòng)
│   ├── server/static/    # bundle web đã build, commit cùng repo
│   ├── skills/builtin/   # skill có sẵn (cite-sources)
│   └── agents/templates/ # mẫu agent cho `agent add`
├── web/                  # SPA React 19 + Vite + vitest + Playwright
├── tests/                # pytest, 54 tệp
├── docs/                 # tài liệu này + diagrams/
├── pyproject.toml        # uv, ruff
└── .github/workflows/ci.yml
```

## 2. Backend `my_agent_crew/`

| Gói | Vai trò | Tệp chính |
|---|---|---|
| `agent/` | vòng lặp một lượt | `loop.py` (`run_turn`), `prompt.py` (`build_system_prompt`), `tool_calls.py` (`settle_tool_calls`), `tool_batches.py`, `approval_expiry.py` (`expire_overdue`), `context_trim.py`, `events.py`, `turn_context.py` |
| `agents/` | hồ sơ agent từ đĩa | `profile.py` (`AgentProfile`), `profile_yaml.py` (đọc), `profile_write.py` (ghi round-trip), `profile_edit.py` (vá + validate), `roster.py`, `context.py` (`bootstrap_sections`), `kit*.py` (đọc `.agents/`), `channels.py`, `templates_cli.py` |
| `activity/` | run và step cho web | `hub.py` (`ActivityHub`), `steps.py` |
| `channels/` | Telegram | `telegram_channel.py` (start/stop), `telegram_inbound.py` (tin, ảnh, `inbox/`), `telegram_albums.py`, `telegram_outbound.py`, `telegram_commands.py`, `telegram_api.py` (redact token), `telegram_offset.py` |
| `inbound.py` | một cổng vào, `InboundBusy` | — |
| `llm/` | provider | `provider.py` (`Provider`, `ProviderChain`), `openrouter.py`, `fake.py`, `types.py` |
| `memory/` | trí nhớ | `agent_store.py` (ghi chú ngày), `user_store.py` (facts), `consolidate.py` (7 ngày → đề xuất), `proposals_apply.py`, `search.py`, `session_summary.py` |
| `scheduler/` | cron | `cron.py`, `jobs.py`, `runner.py` |
| `server/` | FastAPI | `app.py`, `runtime.py`, `runtime_build.py`, `agent_assembly.py` (`build_providers`), `tool_assembly.py`, `deps.py`, `agent_edit_common.py` (khoá ghi + helper dùng chung), `routes_*.py` |
| `skills/` | skill md | `loader.py` (`always`, chỉ mục) |
| `store/` | SQLite | `db.py`, `schema.py`, `models.py`, `messages.py`, `runs.py`, `approvals.py`, `usage.py`, `job_state.py`, `memory_proposals.py`, `conversation_lookup.py` |
| `tools/` | tool | `registry.py` (`ToolRegistry`), `workspace*.py`, `shell.py`, `web.py`, `memory.py`, `memory_user.py`, `delegate.py`, `image.py`, `skills.py`, `hooks.py` |
| `config.py`, `config_parse.py` | `Settings` từ env + `config.yaml` | — |
| `clock.py` | giờ và múi giờ | — |
| `texts.py`, `texts_*.py` | mọi chuỗi tiếng Việt của backend | `texts_delegate.py`, `texts_image.py`, `texts_kit.py`, `texts_telegram.py` |
| `__main__.py` | CLI | `python -m my_agent_crew`, `agent list-templates`, `agent add` |

### Event của một lượt (`agent/events.py`)

`TextDelta`, `AssistantMessage`, `ToolCall`, `ToolResult`, `ApprovalRequired`, `Done`, `Halted`, `Error`, `RouteFallback`. Chúng vừa là SSE cho `/api/conversations/{id}/messages`, vừa là step trong run.

### Bảng SQLite (`store/schema.py`)

`conversations`, `messages`, `approvals`, `runs`, `job_state`, `memory_proposals`. Timestamp lưu UTC.

### Cấu hình

`Settings` (`config.py`): `home`, `routes`, `vision_routes`, `openrouter_api_key`, `brave_api_key`, `tavily_api_key`, `cost_cap_usd`, `language`, `timezone`, `max_steps`, `autonomous_default`, `shell_ask_patterns`, `approval_ttl_seconds`, `tool_output_chars`.

`AgentProfile` (`agents/profile.py`): `id`, `name`, `dir`, `workspace`, `settings`, `description`, `persona_files`, `skills_dirs`, `schedules`, `telegram`, `memory_consolidate`, `mode`, `delegates`, `tools`, `commands`, `hooks`, `kits`.

## 3. API (`server/routes_*.py`)

| Nhóm | Đường |
|---|---|
| Sức khoẻ | `GET /api/health` |
| Cổng vào | `POST /api/inbound` |
| Cuộc trò chuyện | `GET/POST/DELETE /api/conversations[/{id}]`, `POST …/{id}/messages` (SSE), `GET …/{id}/summary` |
| Duyệt | `GET /api/approvals`, `POST /api/approvals/{id}` |
| Run | `GET /api/activity/runs`, `GET …/runs/{id}`, `GET …/stream` (SSE), `GET /api/stats` |
| Agent | `GET /api/agents`, `GET …/{id}`, `GET …/{id}/files`, `POST /api/agents/install`, `GET /api/templates` |
| Sửa agent | `POST /api/agents`, `PATCH …/{id}`, `DELETE …/{id}` |
| Tệp tính cách | `PUT /api/agents/{id}/files/{name}`, `GET …/{id}/prompt` (lời nhắc hệ thống đã ghép), `POST /api/agents/reload` |
| Tool & kết nối | `GET /api/tools`, `GET /api/connections` |
| Trí nhớ agent | `GET /api/agents/{id}/memory`, `…/memory/notes/{day}`, `POST …/memory/consolidate` |
| Trí nhớ người dùng | `GET/PUT /api/memory/user`, `…/user/facts/{name}`, `GET /api/memory/proposals[/{id}]`, `GET /api/memory/search` |
| Job | `GET /api/jobs`, `GET …/{id}/runs`, `GET …/{id}/state`, `POST …/{id}/run` |
| Cài đặt | `GET /api/settings` |

Mọi đường không phải `/api/*` trả SPA. Web định tuyến bằng hash, nên một lượt chạy có đường
riêng: `#/manage/activity/<run_id>` mở đúng lượt đó, tải lại vẫn ở đó, và chia sẻ được.

**Hình dạng `arguments` của một bước tool.** Là mapping tên → giá trị; chuỗi dài và giá trị
dạng list/dict bị cắt còn 160 ký tự trước khi ghi (`activity/steps.py`), vì bản xem trước này
được phát lại kèm mọi bước sau của cùng lượt chạy. Các lượt chạy ghi trước khi store giữ
mapping lưu cả cụm thành **một chuỗi**; những hàng đó vẫn nằm trong DB, nên phía đọc phải
chịu được cả hai hình dạng — duyệt một chuỗi theo chỉ số sẽ cho một hàng mỗi ký tự.

## 4. Web `web/src/`

| Thư mục | Nội dung |
|---|---|
| `api/` | `client.ts`, `sse.ts`, `types.ts`, `activity-types.ts` |
| `hooks/` | `use-activity`, `use-agents`, `use-conversations`, `use-memory`, `use-thread` |
| `state/` | reducer cho thread và activity |
| `components/` | 34 tệp: `message-thread`, `composer`, `approval-bar`, `approval-history`, `run-timeline`, `run-progress-header`, `run-replay`, `tool-call-card`, `empty-state`, `activity-panel`, `crew-panel`, `jobs-panel`, `job-run-history`, `memory-*`, `settings-panel`, `stats-panel`, `budget-indicator`, `status-line`, `attention-center`, `error-boundary` |
| `lib/` | `delegate-result.ts`, `line-diff.ts`, `run-progress.ts`, `run-rows.ts` |
| `i18n/vi.ts` | mọi chuỗi tiếng Việt của web |
| `e2e/` | 11 spec Playwright + `mock-api.ts` |

Script: `dev`, `typecheck`, `test` (vitest), `bundle` (vite build → `my_agent_crew/server/static`), `e2e`.

## 5. Test

| Bộ | Lệnh | Hiện tại |
|---|---|---|
| Backend | `uv run pytest -q` | 56 tệp, 597 passed |
| Web unit | `cd web && npm test` | 36 tệp, 354 passed |
| Web e2e | `cd web && npm run e2e` | 11 spec, 36 test, mock toàn bộ `/api` |
| Lint | `uv run ruff check . && uv run ruff format --check .` | sạch |

Provider giả `MY_AGENT_ROUTES=fake:echo` cho phép chạy cả harness trong test không cần mạng; xem [testing.md](testing.md).

## 6. Mẫu agent và skill có sẵn

- `agents/templates/`: `dev`, `coder`, `debugger`, `git`, `planner`, `researcher`, `reviewer`, `scout`, `tester`, và `_shared_skills/` dùng chung.
- `skills/builtin/cite-sources.md`.

Cài bằng `python -m my_agent_crew agent add <template> [--id <id>] [--force] [--workspace <dir>]` hoặc `POST /api/agents/install`.

## 7. Bộ tài liệu

| Tệp | Cho ai |
|---|---|
| [index.md](index.md) | điểm vào, thứ tự đọc |
| [system-architecture.md](system-architecture.md) | người mới, giải phẫu harness với 5 sơ đồ |
| [codebase-summary.md](codebase-summary.md) | người sắp sửa code |
| [deployment-guide.md](deployment-guide.md) | người cài và vận hành, cách publish doc |
| [project-overview-pdr.md](project-overview-pdr.md) | vấn đề, phạm vi, tiêu chí |
| [code-standards.md](code-standards.md) | quy ước code, test, commit, bí mật |
| [design.md](design.md), [agents.md](agents.md), [tools.md](tools.md), [memory.md](memory.md), [channels.md](channels.md), [testing.md](testing.md) | tham chiếu từng mảng, có từ trước |
| [diagrams/](diagrams/README.md) | spec, HTML, SVG của 5 sơ đồ |

## Câu hỏi mở

- `server/static/` được commit và CI kiểm `git diff --exit-code` sau `bundle`; khi web đổi nhiều, diff commit sẽ lớn — chưa quyết có chuyển sang build lúc cài hay không.
