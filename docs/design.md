# Design

## Goal

A single general-purpose agent that a person uses daily through a web UI: chat, let it use tools,
approve the risky ones, see what it cost. Everything else is subordinate to that loop.

Since 0.2.0 the same loop can be instantiated several times as **named agents** (a health coach,
a personal assistant) that keep their own persona, memory, workspace and schedules, and the UI shows
every run of every agent live. The loop itself did not change; profiles and the scheduler sit
around it.

## What is deliberately not repeated from my-crew

| my-crew | Measured problem | Here |
|---|---|---|
| Team of role-agents, router, DAG task graph | Most value came from one capable agent; coordination code dominated the codebase and the bug list | One agent loop (`agent/loop.py`); profiles only vary its inputs. No long-lived agents talking to each other: delegation is a tool call, one level deep, and a child conversation runs one turn and returns its answer |
| Profiles + company YAML + per-agent settings | Config surface too large to keep tested; secrets could leak into YAML | Env vars + whitelisted `config.yaml` (`config.py`); `agent.yaml` has a fixed key set (`PROFILE_KEYS`) and no secrets |
| Web UI added late, many pages | UI lagged features; tests were a separate world | UI is the primary surface; three test tiers share the same event contract |
| Files grew past 1000 lines | Hard to review, hard for LLM tooling | 200-line budget enforced by a test |
| Cost tracking optimistic | Unknown prices silently counted as 0 | `cost_usd=None` counts as `unknown_cost_calls` and is shown in the UI |
| Vietnamese strings scattered | Identifier drift, hard to localise | `texts.py` and `i18n/vi.ts` only |

## Runtime shape

```
browser ──/api/conversations/{id}/messages (SSE)──┐
Telegram poller ──────────────────────────────────┤
any platform ──POST /api/inbound (JSON, sync)─────┴─▶ Inbound ──▶ run_turn(deps, conversation)
                                                        │           │  ProviderChain (ordered routes, fallback before first item)
                                                        │           │  ToolRegistry (workspace, web, memory, shell, delegate)
                                                        │           │  Skills + persona/memory + crew roster (system prompt)
                                                        │           └─ Store (SQLite: conversations, messages, approvals, runs)
                                                        ├─ ActivityHub  (live runs → SSE /api/activity/stream)
                                                        └─ Scheduler    (cron/every jobs per agent, 20 s tick)
```

- **One door for every platform.** `Inbound` (`inbound.py`) finds the agent, opens or
  reuses the conversation (one per agent per channel per day), guards it while an approval
  is pending, runs the turn under activity tracking and records the run's source. The web
  reads the event stream; Telegram and `POST /api/inbound` take the collected `TurnReply`
  (text, status, steps). No platform is special, so a backend change reaches all of them and
  a feature is tested by posting to the API.

- **Durable state is the message log.** A turn resumes from the last stored assistant message:
  unfinished tool calls are settled first, so a crash mid-turn is recoverable (`test_agent_resume.py`).
- **Approval is first-class.** A `requires_approval` tool pauses the turn with an `approval_required`
  event and a stored `Approval`; the UI shows a bar, the decision endpoint resumes the same turn.
  A conversation marked `autonomous` skips the pause. Hard denials — path escape from the
  workspace, private/loopback network targets — are not approvable.
- **An unanswered approval fails closed.** Every `Approval` carries a deadline
  (`approval_ttl_seconds`, default 600); the scheduler tick sweeps overdue ones
  (`agent/approval_expiry.py`), closes them as `expired`, resumes the turn with the tool refused
  and delivers the reply like any other, so a request nobody saw never keeps a conversation
  hanging. The decision endpoint also takes `always`: approving with it adds the tool to the
  conversation's `auto_approve` list and later calls of that tool run without asking, until the
  chip in the header revokes it. The shell ask list still pauses an always-allowed `shell_run`.
  Decided requests stay readable in `GET /api/approvals`.
- **Fallback is visible.** Each route that gives up is logged, streamed as a `route_fallback`
  event and recorded as a `fallback` step on the run, so a model that keeps failing shows up in
  the timeline instead of silently costing more on the next route.
- **Fallback only before output.** The chain tries the next route only if the previous one failed
  before yielding anything; a failure mid-stream is surfaced, never hidden by a silent retry.
- **Honest cost.** Each assistant message stores `cost_usd` or `None`. The conversation keeps
  `spent_usd` and `unknown_cost_calls`; `cost_cap_usd` halts before the next model call
  (0 = unlimited).
- **Echo provider is a product feature.** `MY_AGENT_ROUTES=fake:echo` runs the whole stack with no
  key; `/tool <name> {json}` drives real tools through the real approval path. It is also what the
  live smoke and the browser tests lean on.
- **Tool output is capped** before it enters the context: 8000 characters by default, per
  agent via `tool_output_chars`.

## Agent profiles

`MY_AGENT_HOME/agents/<id>/agent.yaml` describes one agent (`agents/profile.py`): a fixed key
set, no secrets, every unset value inherited from the global settings. The `default` agent
always exists and is the top-level settings, so a fresh home needs no profile. Persona files
and memory are Markdown in the agent dir, read into the system prompt every turn. Key
reference and folder layout: [agents.md](agents.md); memory files and tools:
[memory.md](memory.md); the tool set and its limits: [tools.md](tools.md).

**Work mode.** `mode: work` swaps the defaults for the ones a coding job needs — a higher
spend cap, more steps, and autonomy on — because a person who asks for a refactor is not
there to approve each file write. It is a different default, not a different rule: the
tools that always ask still ask, and the cap still stops the turn. A work agent also
gets `delegate` unless its `tools` allow-list leaves it out, so a specialist stays a
specialist instead of quietly starting a crew of its own.

**The master.** The `default` agent is the one the person talks to. It carries `delegate`
and, unless its optional `MY_AGENT_HOME/agent.yaml` names a `delegates` list, may reach
every other agent in the home; its system prompt lists that crew each turn. This keeps the
product "one capable, autonomous agent" while letting it staff a job: the person does not
pick an agent, the master does. Agents that talk on Telegram keep their channel and
schedules and are simply also on the roster. Details: [agents.md](agents.md#the-master-agent).

**Templates.** Nine profiles ship with the app — a lead and eight roles — installed with
`agent add <id>` or `POST /api/agents/install` (what the crew tab calls), which brings
the peers the role hands work to and one shared set of skills. Every manifest works as
installed (the home's shared workspace, the global routes); `--workspace` pins a role to
one repository. An install over the API joins the running crew at once, while channels and
schedules start at boot. They are a starting point to edit, not a framework: each is an
`agent.yaml` of the same fixed keys, so there is nothing to learn beyond the profile format.

## Memory

Memory is Markdown on disk in two scopes: what the crew knows about **the person**
(`users/owner/`, read by every agent) and what **one agent** knows about its own work
(`MEMORY.md` plus dated notes in its dir). Full reference: [memory.md](memory.md).

Two scopes rather than one, because the two have different readers. A fact about the
person — how they like to be answered, what they are working on — is wrong to relearn per
agent: telling the coach something and having the assistant not know it is the failure
this fixes. Work notes are the opposite: the coach's measurements would be noise in the
assistant's prompt, and every agent's notes in one file would blow the section cap.

Writes the person is present for land immediately; writes from an unattended job become
**proposals** in `memory_proposals`. The split is who can object, not how risky the write
looks: a scheduled job that rewrites the person's profile with a bad guess has nobody to
catch it. The same reasoning makes **consolidation** — the scheduled rewrite of `MEMORY.md`
from recent notes — a proposal that keeps the text it replaced, so one step back is always
possible. On a shared Telegram bot each agent also reads the last few lines the others
exchanged in that chat today, read-only, so a person can carry a subject from one agent to
the next without repeating themselves.

## Activity hub and runs

Every model turn — chat, approval resume, scheduled prompt, scheduled command — is a **run**
(`store/runs.py`, `activity/hub.py`). A run records its agent, source (`chat`, `job:<id>`),
conversation, status, steps (model calls with cost, tool calls with result and duration), spend
and a summary. Live runs are kept in memory and broadcast as SSE on `/api/activity/stream`
(`snapshot` on connect, then `run` and `event` frames); finished runs are read from SQLite.
Runs still marked running when the server starts are closed as `failed` with the summary
`interrupted`.

## Scheduler

`scheduler/` turns each enabled schedule into a job `<agent_id>/<schedule_id>`. A schedule has
exactly one of `cron` (five fields, in the person's zone) or `every` (`30m`, `2h`, `1d`) and exactly
one of `prompt` or `command`. A **prompt job** opens a fresh autonomous conversation for the agent
and runs a turn; a **command job** runs the string with `shell_run` in the agent workspace and
records only that step; a **consolidate job**, added by a `memory_consolidate` cron, rewrites the
agent's `MEMORY.md` with one model call and opens no conversation, so it delivers nothing. The tick is 20 s; `POST /api/jobs/{id}/run` starts a job immediately and
returns 202. The schedule clock is `Settings.now()`: the `timezone` key in `config.yaml` (or
`MY_AGENT_TIMEZONE`), an IANA name such as `Asia/Ho_Chi_Minh`, and the machine zone when unset.
Every stamp in the database stays UTC; `clock.py` turns them into the person's day for the
prompt, `/status`, the activity stats and the usage ledger.
`PATCH /api/jobs/{id}/state` pauses or resumes a schedule at runtime; the override lives in
the `job_state` table (`store/job_state.py`), survives a restart and only applies to a schedule
the profile enables — one turned off in yaml is reported as `enabled: false, paused: false` and
cannot be switched on from the UI. `GET /api/jobs/{id}/runs` lists that job's past runs.

## Channels

`channels/` lets an agent talk on something other than the web UI. Today that is Telegram:
a profile with `telegram: {token_env, chat_id}` gets a `TelegramChannel` at startup when the
named env var is set. Turns from the chat go through `Inbound` like every other platform,
with source `telegram`, replies go back as text and `sendPhoto`, slash commands are answered without a
model call, and the scheduler's `Runtime.deliver` pushes a prompt job's reply to the chat.
Agents that name the same `token_env` share one poller: `@<agent id>` picks the agent, the
pick is remembered per chat in the `channel_state` table (explicit, not derived from
timestamps, so a delivered brief never switches the agent), and every reply carries a
`[Name]` prefix. Full behaviour, commands, offsets and secrets: [channels.md](channels.md).

## Shell tool and agent files

`shell_run` executes a command in the agent workspace with a minimal environment
(PATH, HOME, LANG, TERM, TMPDIR, USER, SHELL) and a bounded timeout; it always requires approval
unless the conversation or agent is autonomous. `GET /api/agents/{id}/files?path=` serves a file
from inside that workspace only, which is how an assistant line `MEDIA: charts/sleep.png` is
rendered inline by the UI.

## Web UI

React + Vite, no state library. Two pure reducers pin the server contract from both sides:
`thread-reducer.ts` over the `AgentEvent` union for one conversation, and
`activity-reducer.ts` over the `ActivityPayload` union for the activity rail. `use-thread.ts`
owns one conversation (load, stream, approve, abort); `use-conversations.ts` owns the list;
`use-activity.ts` owns the SSE subscription and reloads the run list when a run finishes;
`use-agents.ts` owns agents, jobs and stats and is refreshed from the same signal.
All strings come from `i18n/vi.ts`.

There is one chat, with the master: the conversation list holds the master's conversations
and a new one is always opened for it. The welcome screen speaks as the master and names
the crew; a header chip (`Đội: N`) opens the crew tab in the rail, which lists every agent
(master first, with mode, live, schedule and Telegram badges) and installs a bundled
template in one click. A delegate's conversation is not listed, but opens from a run card
or the attention centre.

The activity rail (ideas borrowed from openhuman's session view, no code) shows: live runs
expanded step by step with tool arguments and output; an attention centre for runs that wait for
approval, failed or were halted; a jobs tab with next/last run, a run-now button, a pause/resume
switch and the job's run history on demand; an approvals tab listing decided requests with their
outcome (approved, denied, expired); a costs tab by agent, model and day, where the last seven
days and the per-model table come from `store/usage.py`, a ledger read straight from the message
log with token counts, so the figures are what was actually billed and not an estimate; the
crew tab above; a status line with stream connectivity. The approval bar shows the deadline of the pending request and a "always allow"
button next to approve/deny; the header lists the always-allowed tools as chips that revoke on
click. An error boundary keeps a rendering crash from taking the chat down with it.

## Extension points

- Provider: implement `Provider.stream` (`llm/provider.py`) and register it in `build_providers`.
- Tool: a `Tool` with `spec` + `run`; set `requires_approval` when it changes state.
- Skill: a Markdown file with `name` (and optional `always`, `description`) in `MY_AGENT_HOME/skills`
  or in an agent's `skills_dirs`.
- Agent: a folder under `MY_AGENT_HOME/agents/` with `agent.yaml` and persona files.
- Channel: a class with `start`/`stop`/`deliver(conv_id)` built in `channels/build_channels`
  from a profile block; keep secrets as env-var names in the profile.
