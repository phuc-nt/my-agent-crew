# Testing

Three tiers, one contract. Add a row whenever you add a feature.

| Tier | Runs with | Scope |
|---|---|---|
| pytest (`tests/`) | `uv run pytest -q` | loop, tools, store, providers, profiles, scheduler, HTTP + SSE |
| vitest (`web/src/**/*.test.ts(x)`) | `cd web && npm test` | parser, reducers, client, components, full App against an in-memory fake server |
| Playwright (`web/e2e/`) | `cd web && npm run e2e` | real browser + real Vite dev server, `/api` answered by `page.route` (`e2e/mock-api.ts`) |

Guard tests: `tests/test_file_size_budget.py` (≤200 lines), `tests/test_static_spa.py`
(bundle present and served), CI `git diff --exit-code` on the bundle.

## Feature → test map

| Feature | pytest | vitest | Playwright |
|---|---|---|---|
| Config from env + whitelisted yaml, route parsing | `test_config.py` | — | — |
| Route fallback before first item, logged and yielded as `RouteFailed`; mid-stream failure surfaces | `test_provider_chain.py` | — | — |
| Fallback becomes a `route_fallback` event, a `fallback` run step and a chat notice | `test_agent_loop.py`, `test_activity.py` | `activity-reducer.test.ts`, `thread-reducer.test.ts`, `activity-cards.test.tsx` | — |
| OpenRouter streaming, error chunks, HTTP errors | `test_openrouter.py` | — | — |
| Tool registry, JSON arg validation, output cap | `test_tools_registry.py` | — | — |
| Workspace tools refuse `..` escapes, follow symlinks inside | `test_tools_workspace.py` | — | — |
| Web tools refuse private/loopback hosts; search only with a key | `test_tools_web.py`, `test_app_wiring.py` | — | — |
| Memory save/search | `test_tools_memory.py` | — | — |
| Shell tool: cwd, env allow-list, timeout, exit code, approval | `test_tools_shell.py` | — | — |
| Store ordering, budgets, approvals, agent filter, runs round-trip | `test_store.py` | — | — |
| Skills loading (builtin + home + `skills_dirs`, `SKILL.md` folders), `always` | `test_skills.py` | — | `settings drawer` (shown) |
| Agent profiles: key whitelist, workspace/skills resolution, schedule validation, default agent | `test_agent_profiles.py` | — | — |
| Persona + memory sections in the system prompt, size cap | `test_agent_context.py` | — | — |
| Agent loop: text, tool round-trips, max steps, cost cap halt | `test_agent_loop.py` | reducer `halted`/`done` | — |
| Approval pause / approve / deny / autonomous bypass | `test_agent_approval.py`, `test_server_api.py` | reducer, `ApprovalBar`, App approval flow | `approval bar pauses…` |
| Crash-resume from unfinished tool calls | `test_agent_resume.py` | — | — |
| Activity hub: run lifecycle, steps, spend, interrupted on restart, SSE fan-out | `test_activity.py` | `activity-reducer.test.ts` | — |
| Scheduler: cron/every parsing, due detection, prompt vs command jobs, run-now, delivery hook | `test_scheduler.py` | — | — |
| Telegram channel: inbound → tracked turn, chat filter, per-day conversation, slash commands (`/new`, `/reset`, `/help`, `/status`, `/tools`, `/approve`, `/deny`, unknown, path is not a command), menu registered once at start, text next to a tool call kept, error/approval notices, typing indicator kept alive and tolerant of API errors, `deliver` joins the last turn's texts with `MEDIA:` photos, token redaction, 409 | `test_channels_telegram.py` | — | — |
| `telegram:` profile block parsing; `channel` column + `latest_for_channel`; channel built only with its env var | `test_agent_profiles.py`, `test_store.py`, `test_app_wiring.py` | `ConversationList` tag, `vi` labels | — |
| `/api/agents`, `/api/agents/{id}/files` (workspace only), `/api/activity/*`, `/api/stats`, `/api/jobs` | `test_server_agents_activity_jobs.py` | `client.test.ts` (activity api) | `jobs tab…` |
| HTTP API: CRUD, PATCH, 409 while awaiting approval, SSE framing | `test_server_api.py` | `client.test.ts`, App 409 notice | — |
| SSE parsing (chunk boundaries, CRLF, flush, bad JSON) | `test_server_api.py` (`parse_sse`) | `sse.test.ts` | — |
| History restore incl. denied tool + pending approval | — | reducer `loaded`, App restore test | — |
| Streaming bubble → final assistant message | — | reducer, App first-send test | `send a message…` |
| Budget display, unknown-cost badge, over-budget flag | — | `BudgetIndicator`, App | `send a message…` |
| Composer keys (Enter / Shift+Enter), stop, disabled while pending | — | `Composer` | approval test (disabled) |
| Rename / autonomous toggle / skills attach via PATCH | — | App header test | — |
| Delete with confirmation | — | App delete test | — |
| Settings drawer shows routes, key presence (never values), tools, paths | `test_server_api.py` | `SettingsPanel` via App | `settings drawer…` |
| Run card: status, steps, tool args/output, cost, unknown-cost badge, open conversation | — | `activity-cards.test.tsx` | `the activity rail shows a live job…` |
| Attention centre, jobs panel (run-now, disabled), stats panel | — | `activity-cards.test.tsx` | `jobs tab…` |
| Activity panel tabs + badge, "only this conversation", agent switcher, status line, error boundary | — | `activity-chrome.test.tsx` | — |
| Live run arriving over SSE → done, stats refresh, stream loss notice | — | `app-activity.test.tsx` | `the activity rail shows a live job…` |
| Agent switcher scopes list + new conversation; `MEDIA:` lines render from `/api/agents/{id}/files` | — | `app-activity.test.tsx` | `agent switcher scopes…` |
| Echo provider + `/tool` directive | `test_agent_loop.py`, `test_server_api.py` | — | — |
| Bundle served at `/`, SPA fallback, `/api/*` 404 stays JSON | `test_static_spa.py` | — | — |

## Live smoke (manual)

`MY_AGENT_ROUTES=fake:echo` against a throwaway `MY_AGENT_HOME`, then through the UI or curl:
chat → `/tool workspace_list {"path":"."}` → `/tool workspace_write {...}` → approve → file exists
in `MY_AGENT_HOME/workspace`. With an agent profile that has a schedule: `POST /api/jobs/<agent>/<schedule>/run`
must produce a run on `/api/activity/runs` and a card in the rail. This is the check to repeat
before tagging a release.
