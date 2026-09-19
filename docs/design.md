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
| Team of role-agents, router, DAG task graph | Most value came from one capable agent; coordination code dominated the codebase and the bug list | One agent loop (`agent/loop.py`); profiles only vary its inputs |
| Profiles + company YAML + per-agent settings | Config surface too large to keep tested; secrets could leak into YAML | Env vars + whitelisted `config.yaml` (`config.py`); `agent.yaml` has a fixed key set (`PROFILE_KEYS`) and no secrets |
| Web UI added late, many pages | UI lagged features; tests were a separate world | UI is the primary surface; three test tiers share the same event contract |
| Files grew past 1000 lines | Hard to review, hard for LLM tooling | 200-line budget enforced by a test |
| Cost tracking optimistic | Unknown prices silently counted as 0 | `cost_usd=None` counts as `unknown_cost_calls` and is shown in the UI |
| Vietnamese strings scattered | Identifier drift, hard to localise | `texts.py` and `i18n/vi.ts` only |

## Runtime shape

```
browser ──/api (JSON + SSE)──▶ FastAPI ──▶ run_turn(deps, conversation)
                                 │           │  ProviderChain (ordered routes, fallback before first item)
                                 │           │  ToolRegistry (workspace, web, memory, shell)
                                 │           │  Skills + persona/memory sections (system prompt)
                                 │           └─ Store (SQLite: conversations, messages, approvals, runs)
                                 ├─ ActivityHub  (live runs → SSE /api/activity/stream)
                                 └─ Scheduler    (cron/every jobs per agent, 20 s tick)
```

- **Durable state is the message log.** A turn resumes from the last stored assistant message:
  unfinished tool calls are settled first, so a crash mid-turn is recoverable (`test_agent_resume.py`).
- **Approval is first-class.** A `requires_approval` tool pauses the turn with an `approval_required`
  event and a stored `Approval`; the UI shows a bar, the decision endpoint resumes the same turn.
  A conversation marked `autonomous` skips the pause. Hard denials — path escape from the
  workspace, private/loopback network targets — are not approvable.
- **Fallback only before output.** The chain tries the next route only if the previous one failed
  before yielding anything; a failure mid-stream is surfaced, never hidden by a silent retry.
- **Honest cost.** Each assistant message stores `cost_usd` or `None`. The conversation keeps
  `spent_usd` and `unknown_cost_calls`; `cost_cap_usd` halts before the next model call
  (0 = unlimited).
- **Echo provider is a product feature.** `MY_AGENT_ROUTES=fake:echo` runs the whole stack with no
  key; `/tool <name> {json}` drives real tools through the real approval path. It is also what the
  live smoke and the browser tests lean on.
- **Tool output is capped** at 8000 characters before it enters the context.

## Agent profiles

`MY_AGENT_HOME/agents/<id>/agent.yaml` describes one agent (`agents/profile.py`). The `default`
agent always exists and is the top-level settings, so a fresh home needs no profile.

| Key | Meaning |
|---|---|
| `name`, `description` | shown in the UI |
| `routes` | `provider:model` list; falls back to the global routes |
| `workspace` | tool sandbox; relative to the agent dir, `~` expands; default `<agent dir>/workspace` |
| `persona_files` | Markdown read from the agent dir every turn; default `AGENTS.md, SOUL.md, IDENTITY.md, USER.md` |
| `skills_dirs` | extra skill folders (`name.md` or `name/SKILL.md`); `<agent dir>/skills` is always included |
| `cost_cap_usd`, `max_steps`, `autonomous` | per-agent overrides of the global settings |
| `schedules` | list of jobs, see below |

Every turn also gets `MEMORY.md` and `memory/<yesterday>.md`, `memory/<today>.md` from the agent
dir, each section capped at 24 000 characters (`agents/context.py`). The agent writes those files
itself with the workspace tools when its workspace is the agent dir, or through `shell_run`.
Persona files are the agent's identity, so they live in `MY_AGENT_HOME`, never in this repo.

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
exactly one of `cron` (five fields, local machine time) or `every` (`30m`, `2h`, `1d`) and exactly
one of `prompt` or `command`. A **prompt job** opens a fresh autonomous conversation for the agent
and runs a turn; a **command job** runs the string with `shell_run` in the agent workspace and
records only that step. The tick is 20 s; `POST /api/jobs/{id}/run` starts a job immediately and
returns 202. There is no timezone field: the machine clock is the schedule clock.

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

The activity rail (ideas borrowed from openhuman's session view, no code) shows: live runs
expanded step by step with tool arguments and output; an attention centre for runs that wait for
approval, failed or were halted; a jobs tab with next/last run and a run-now button; a costs tab
by agent, model and day; an agent switcher that scopes the conversation list and new conversations;
a status line with stream connectivity. An error boundary keeps a rendering crash from taking the
chat down with it.

## Extension points

- Provider: implement `Provider.stream` (`llm/provider.py`) and register it in `build_providers`.
- Tool: a `Tool` with `spec` + `run`; set `requires_approval` when it changes state.
- Skill: a Markdown file with `name` (and optional `always`, `description`) in `MY_AGENT_HOME/skills`
  or in an agent's `skills_dirs`.
- Agent: a folder under `MY_AGENT_HOME/agents/` with `agent.yaml` and persona files.
