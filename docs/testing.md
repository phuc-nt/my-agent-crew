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
| Config from env + whitelisted yaml, route parsing, the shell ask list from yaml or env and emptied on purpose | `test_config.py` | — | — |
| Route fallback before first item, logged and yielded as `RouteFailed`; mid-stream failure surfaces | `test_provider_chain.py` | — | — |
| Fallback becomes a `route_fallback` event, a `fallback` run step and a chat notice | `test_agent_loop.py`, `test_activity.py` | `activity-reducer.test.ts`, `thread-reducer.test.ts`, `activity-cards.test.tsx` | — |
| OpenRouter streaming, error chunks, HTTP errors | `test_openrouter.py` | — | — |
| Tool registry, JSON arg validation, output cap | `test_tools_registry.py` | — | — |
| Workspace tools refuse `..` escapes, follow symlinks inside | `test_tools_workspace.py` | — | — |
| Web tools refuse private/loopback hosts; search only with a key | `test_tools_web.py`, `test_app_wiring.py` | — | — |
| Memory save/search: a note appended with a timestamp, a search covering the shared facts, `MEMORY.md` and the notes newest first | `test_tools_memory.py` | — | — |
| Search ranking: a bullet keeps its continuation lines, a numbered item and a bare paragraph are entries too, accents dropped on both sides with `đ` its own letter, a word found whole outranks the same word inside another, a word of three characters or fewer must be found whole, full matches push out partial ones but partial ones show when nothing is complete, caller order breaks a tie, a long entry is cut | `test_memory_search.py` | — | — |
| Shared user scope: `USER.md`, one file per fact, slug + type validation, regenerated `INDEX.md` | `test_memory_user_store.py`, `test_tools_memory_user.py` | — | — |
| An agent's own `MEMORY.md` and dated notes: append, rewrite, list, read, a note named with a suffix listed and read as a note of its day while other files stay out, a name that is not a day refused | `test_memory_agent_store.py`, `test_server_memory_api.py` | `memory-panel.test.tsx` (two notes of one day are two entries) | — |
| A job's shared write becomes a proposal; approve applies it, reject leaves nothing, deciding twice is a 409 | `test_memory_proposals_apply.py`, `test_server_memory_api.py` | `memory-panel.test.tsx` | — |
| Consolidation: nothing newer than `MEMORY.md` never calls the model, a rewrite waits for approval, autonomous applies at once, an unchanged or empty rewrite is no proposal, a provider failure writes nothing, note budget and newest-first selection, the day limit counting days rather than files | `test_memory_consolidate.py` | — | — |
| Consolidate as a job and over HTTP: `memory_consolidate` cron becomes a `consolidate` job with no conversation, 202 to start, 409 while one runs, 404 for an unknown agent | `test_scheduler.py`, `test_server_memory_api.py` | `memory-panel.test.tsx` (button, busy notice, undo a rewrite) | — |
| Previous conversation's summary carried into a new one on the same channel | `test_memory_session_summary.py` | — | — |
| Shared chat context: only other agents, only today, only this channel, last 10 lines, long lines cut, tool traffic excluded, unknown agent keeps its id | `test_memory_shared_chat.py`, `test_store.py`, `test_agent_loop.py`, `test_channels_telegram_shared.py` | — | — |
| Shell tool: cwd, env allow-list, timeout, exit code, approval | `test_tools_shell.py` | — | — |
| Shell ask list: case-insensitive substring match, an autonomous command on the list still waits and names the pattern, an empty list turns the guard off, the same command asks the same way when not autonomous | `test_tools_shell.py` | `thread-reducer.test.ts`, `activity-reducer.test.ts`, `components.test.tsx` (reason shown, and nothing when absent) | — |
| Store ordering, budgets, approvals, agent filter, runs round-trip | `test_store.py` | — | — |
| Skills loading (builtin + home + `skills_dirs`, `SKILL.md` folders), `always` | `test_skills.py` | — | `settings drawer` (shown) |
| Skill index in the system prompt: names only for unattached skills, description cut, names-only above 40, no section when empty | `test_skills.py` | — | — |
| `skill_read` returns a body, names what exists on an unknown skill | `test_tools_skills.py` | — | — |
| Agent profiles: key whitelist, workspace/skills resolution, schedule validation, default agent, per-agent shell ask list | `test_agent_profiles.py` | — | — |
| Persona + memory sections in the system prompt, size cap | `test_agent_context.py` | — | — |
| Agent loop: text, tool round-trips, max steps, cost cap halt | `test_agent_loop.py` | reducer `halted`/`done` | — |
| Approval pause / approve / deny / autonomous bypass | `test_agent_approval.py`, `test_server_api.py` | reducer, `ApprovalBar`, App approval flow | `approval bar pauses…` |
| Crash-resume from unfinished tool calls | `test_agent_resume.py` | — | — |
| Activity hub: run lifecycle, steps, spend, interrupted on restart, SSE fan-out | `test_activity.py` | `activity-reducer.test.ts` | — |
| Scheduler: cron/every parsing, due detection, prompt vs command vs consolidate jobs, run-now, delivery hook and its one-line result log, a schedule's `skills` reaching the conversation and the prompt | `test_scheduler.py` | `activity-cards.test.tsx` (job kind label, attached skills) | `jobs tab…` |
| Telegram channel: inbound → tracked turn, chat filter, per-day conversation, slash commands (`/new`, `/reset`, `/help`, `/status`, `/tools`, `/approve`, `/deny`, unknown, path is not a command), menu registered once at start, text next to a tool call kept, error/approval notices (an approval forced by the ask list says which pattern matched), typing indicator kept alive and tolerant of API errors, `deliver` joins the last turn's texts with `MEDIA:` photos or reports a run that stopped without a reply, a turn and a delivered run that produce no text at all say so with their step count instead of staying silent, token redaction, 409 | `test_channels_telegram.py` | — | — |
| An API error with no description still names the method and status; a reply from a run that halted carries a cut-short notice, a done run does not | `test_channels_telegram.py` | — | — |
| Shared Telegram bot: `@id` mention parsing, routing + sticky current agent, bare mention switch, unknown mention, `/help` + `/agents` unprefixed, agent commands on the mentioned agent, a bare `/new` cutting every agent on the bot while `@id /new` cuts only that one, `deliver` prefix + stranger agent, `build_channels` grouping by `token_env` with shared offset seeding, differing `chat_id` rejected, menu registered once per shared channel | `test_channels_telegram_shared.py` | — | — |
| `channel_state` table remembers the current agent per channel across reopen | `test_store.py` | — | — |
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
