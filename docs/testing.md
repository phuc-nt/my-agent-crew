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
| Config from env + whitelisted yaml, route parsing, the shell ask list from yaml or env and emptied on purpose, the tool output cap from yaml or env and positive | `test_config.py` | — | — |
| Route fallback before first item, logged and yielded as `RouteFailed`; mid-stream failure surfaces | `test_provider_chain.py` | — | — |
| Fallback becomes a `route_fallback` event, a `fallback` run step and a chat notice | `test_agent_loop.py`, `test_activity.py` | `activity-reducer.test.ts`, `thread-reducer.test.ts`, `activity-cards.test.tsx` | — |
| OpenRouter streaming, error chunks, HTTP errors | `test_openrouter.py` | — | — |
| Tool registry, JSON arg validation, output cap (default and per registry, kept when narrowed) | `test_tools_registry.py` | — | — |
| Workspace tools refuse `..` escapes, follow symlinks inside | `test_tools_workspace.py` | — | — |
| Web tools refuse private/loopback hosts; search only with a key | `test_tools_web.py`, `test_app_wiring.py` | — | — |
| Memory save/search: a note appended with a timestamp, a search covering the shared facts, `MEMORY.md` and the notes newest first | `test_tools_memory.py` | — | — |
| Search ranking: a bullet keeps its continuation lines, a numbered item and a bare paragraph are entries too, accents dropped on both sides with `đ` its own letter, a word found whole outranks the same word inside another, a word of three characters or fewer must be found whole, full matches push out partial ones but partial ones show when nothing is complete, caller order breaks a tie, a long entry is cut | `test_memory_search.py` | — | — |
| Shared user scope: `USER.md`, one file per fact, slug + type validation, regenerated `INDEX.md` | `test_memory_user_store.py`, `test_tools_memory_user.py` | — | — |
| An agent's own `MEMORY.md` and dated notes: append, rewrite, list, read, a note named with a suffix listed and read as a note of its day while other files stay out, a name that is not a day refused | `test_memory_agent_store.py`, `test_server_memory_api.py` | `memory-panel.test.tsx` (two notes of one day are two entries) | — |
| A job's shared write becomes a proposal; approve applies it, reject leaves nothing, deciding twice is a 409 | `test_memory_proposals_apply.py`, `test_server_memory_api.py` | `memory-panel.test.tsx` | — |
| Search over HTTP: both scopes labelled, narrowed to one agent, an empty query returns nothing, an unknown agent is a 404, without an agent the agents' hits are interleaved by rank so a note-heavy agent cannot bury another's best hit | `test_server_memory_api.py` | — | — |
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
| Agent profiles: key whitelist, workspace/skills resolution, schedule validation, default agent, per-agent shell ask list and tool output cap (reported, `< 1` rejected) | `test_agent_profiles.py` | — | — |
| Work mode: `mode` must be one of two words, `delegates` must name agents that exist, a `tools` allow-list keeps only what it names — including `delegate`, so a capped work agent cannot hand work on — an unknown name warns while a tool that merely needs a key does not, the coding tools reach a work agent and no other | `test_agent_profiles.py`, `test_tools_workspace_edit.py`, `test_tools_workspace_search.py` | — | — |
| Bundled templates: all nine ship and parse as profiles, the lead delegates to every peer, each role's allow-list matches what it is for, personas and shared skills name no tool from another harness and stay short enough to read every turn, adding writes the agent and the shared skills, a lead brings the peers it delegates to while a peer already there is left alone, an id may differ from the template name, a second add refuses rather than overwriting an edited profile, an unknown name writes nothing, an installed crew starts with delegation and the shared skills already wired, and a pinned `--workspace` reaches the lead and every peer it brings | `test_agent_templates.py` | — | — |
| The master: it is the default agent and says so, `MY_AGENT_HOME/agent.yaml` shapes it and without the file it is the plain default, it reaches every other agent unless it names its own `delegates`, the roster names each delegate with what it does, it holds `delegate` while a plain assistant does not, it reads its roster in the system prompt while a child turn sees none, agents added while running join its roster, and a runtime built around one agent refuses to grow | `test_crew_roster.py` | — | — |
| Install over HTTP: a template installed becomes live for the master, a workspace is pinned into the agent and the peers it brings, unknown templates and taken ids are refused, and the master can delegate to an agent installed moments ago | `test_api_agents_install.py` | — | — |
| One gate for every platform: a message opens today's conversation on its channel and is answered, a new day opens another, channels and explicit conversations are kept apart, unknown agents and conversations are refused, a conversation waiting on an approval refuses new messages, the master delegates and the child's answer comes back over HTTP, and how a turn ended is reported with the text | `test_api_inbound.py` | — | — |
| Crew tab: master first, then each member with what the master can hand it; a template installs with one click and says when a restart is still needed; a failed install is reported and templates already in the crew are marked; the header chip counts the crew and opens the tab | — | `crew-panel.test.tsx`, `app.test.tsx` (master welcome + install) | `crew-smoke.spec.ts` |
| Trimming a long context: the oldest turns go first, the system frame and the newest turn always stay, a tool result never outlives the call it answers | `test_agent_context_trim.py` | — | — |
| Delegation: the parent gets the child's answer and pays for it, the child starts with no history, an agent outside `delegates` is refused while an agent may always delegate to itself, a child's toolbox has no `delegate` and a delegated turn refuses to delegate anyway, resuming the same call reuses the child instead of opening a second one, the cap on how many one conversation may hand out, the child inherits what is left of the budget | `test_tools_delegate.py` | — | — |
| `parent_call_id` on a conversation, `for_parent_call`, `children_of` ordering | `test_store.py` | — | — |
| Batching: only tools marked parallel share a batch, the batch is capped, an unknown tool is left alone; batched calls really do overlap and their results come back in call order | `test_agent_tool_batches.py` | — | — |
| Waiting on a conversation: the finished run comes back, a timeout returns nothing, a run paused for approval is not finished until it resumes | `test_activity.py` | — | — |
| Persona + memory sections in the system prompt, size cap | `test_agent_context.py` | — | — |
| Agent loop: text, tool round-trips, max steps, cost cap halt | `test_agent_loop.py` | reducer `halted`/`done` | — |
| Approval pause / approve / deny / autonomous bypass | `test_agent_approval.py`, `test_server_api.py` | reducer, `ApprovalBar`, App approval flow | `approval bar pauses…` |
| Approval deadline: the TTL from yaml or env must be positive, an overdue request closes as `expired`, the turn resumes with the tool refused and is delivered, a failing delivery still counts it closed, the scheduler sweeps on every tick, a row written before deadlines existed never expires, Telegram announces the refusal before the reply | `test_config.py`, `test_store_approvals_jobs_usage.py`, `test_approval_expiry.py`, `test_channels_telegram.py` | reducer `expiresAt`, `ApprovalBar` deadline | — |
| Always allow: approving with `always` lets the same tool run without asking again, `always` on a denial allows nothing, the shell ask list still pauses an always-allowed tool, `auto_approve` stored as a list and patched over HTTP | `test_agent_approval.py`, `test_server_api.py`, `test_store_approvals_jobs_usage.py` | App always-allow test (bar → header chips → revoke) | `approval bar pauses…` (button present) |
| Approval history: decided requests newest first, pending skipped, `GET /api/approvals` carries the agent id | `test_store_approvals_jobs_usage.py`, `test_server_api.py` | `app-activity.test.tsx` approvals tab | — |
| Job state: a pause survives reopen, `PATCH /api/jobs/{id}/state` and `GET /api/jobs/{id}/runs`, a profile-disabled schedule cannot be resumed | `test_store_approvals_jobs_usage.py`, `test_server_agents_activity_jobs.py` | `activity-cards.test.tsx` (switch, profile-off, run history), `app-activity.test.tsx` | `jobs tab…` |
| Usage ledger: by day fills empty days and counts only model calls, by model sums tokens and orders by spend, token counts round-trip through the message log, `/api/stats` `days` + `models` | `test_store_approvals_jobs_usage.py`, `test_server_agents_activity_jobs.py` | `StatsPanel` (days, models) | `jobs tab…` |
| Crash-resume from unfinished tool calls | `test_agent_resume.py` | — | — |
| Activity hub: run lifecycle, steps, spend, interrupted on restart, SSE fan-out | `test_activity.py` | `activity-reducer.test.ts` | — |
| Scheduler: cron/every parsing, due detection, prompt vs command vs consolidate jobs, run-now, delivery hook and its one-line result log, a schedule's `skills` reaching the conversation and the prompt | `test_scheduler.py` | `activity-cards.test.tsx` (job kind label, attached skills) | `jobs tab…` |
| Telegram channel: inbound → tracked turn, chat filter, per-day conversation, slash commands (`/new`, `/reset`, `/help`, `/status`, `/tools`, `/approve`, `/deny`, unknown, path is not a command), menu registered once at start, text next to a tool call kept, error/approval notices (an approval forced by the ask list says which pattern matched), typing indicator kept alive and tolerant of API errors, `deliver` joins the last turn's texts with `MEDIA:` photos or reports a run that stopped without a reply, a turn and a delivered run that produce no text at all say so with their step count instead of staying silent, a photo (largest size) or document saved to `inbox/` with the caption in the turn text, a crafted file name reduced to a plain one, a failed download reported without a turn and without the token, token redaction, 409 | `test_channels_telegram.py` | — | — |
| An API error with no description still names the method and status; a reply from a run that halted carries a cut-short notice, a done run does not | `test_channels_telegram.py` | — | — |
| Shared Telegram bot: `@id` mention parsing, routing + sticky current agent, bare mention switch, unknown mention, `/help` + `/agents` unprefixed, agent commands on the mentioned agent, a bare `/new` cutting every agent on the bot and confirmed in the bot's own voice while `@id /new` cuts only that one, `deliver` prefix + stranger agent, `build_channels` grouping by `token_env` with shared offset seeding, differing `chat_id` rejected, menu registered once per shared channel | `test_channels_telegram_shared.py` | — | — |
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
| Attention centre, jobs panel (run-now, pause/resume, profile-off, run history), stats panel (totals, last days, per model) | — | `activity-cards.test.tsx` | `jobs tab…` |
| Activity panel tabs + badge, "only this conversation", status line, error boundary | — | `activity-chrome.test.tsx` | — |
| Delegated work in the UI: a `delegate` call reads as the task it is (who took it, cost, steps) with the child's reply instead of the result header, a running one offers nothing to open yet, a work agent's conversation is badged with its cap and step budget, spend says how many children it covers, a conversation an agent opened is marked and sorted below the person's own, a delegated run nests under the run that asked for it, and settings lists the crew with the master badged first and what each role may hand off | — | `delegate-cards.test.tsx`, `delegate-result.test.ts`, `activity-reducer.test.ts` | `delegate-smoke.spec.ts` |
| Live run arriving over SSE → done, stats refresh, stream loss notice | — | `app-activity.test.tsx` | `the activity rail shows a live job…` |
| One chat with the master: the list holds only its conversations and new ones are created for it, a delegate's conversation opens from the attention centre without being listed; `MEDIA:` lines render from `/api/agents/{id}/files` | — | `app-activity.test.tsx` | `the list holds only the master's conversations…` |
| Echo provider + `/tool` directive | `test_agent_loop.py`, `test_server_api.py` | — | — |
| Bundle served at `/`, SPA fallback, `/api/*` 404 stays JSON | `test_static_spa.py` | — | — |

## Live smoke (manual)

`MY_AGENT_ROUTES=fake:echo` against a throwaway `MY_AGENT_HOME`, then through the UI or curl:
chat → `/tool workspace_list {"path":"."}` → `/tool workspace_write {...}` → approve → file exists
in `MY_AGENT_HOME/workspace`. With an agent profile that has a schedule: `POST /api/jobs/<agent>/<schedule>/run`
must produce a run on `/api/activity/runs` and a card in the rail. With at least one other
agent installed: `POST /api/inbound {"text": "Nhờ scout …"}` must answer with the master's
summary and leave a child run whose `source` is `delegate:<conversation id>` on
`/api/activity/runs`. This is the check to repeat before tagging a release.
