# Design

## Goal

A single general-purpose agent that a person uses daily through a web UI: chat, let it use tools,
approve the risky ones, see what it cost. Everything else is subordinate to that loop.

## What is deliberately not repeated from my-crew

| my-crew | Measured problem | Here |
|---|---|---|
| Team of role-agents, router, DAG task graph | Most value came from one capable agent; coordination code dominated the codebase and the bug list | One agent, one loop (`agent/loop.py`) |
| Profiles + company YAML + per-agent settings | Config surface too large to keep tested; secrets could leak into YAML | Env vars + whitelisted `config.yaml` (`config.py`) |
| Web UI added late, many pages | UI lagged features; tests were a separate world | UI is the primary surface; three test tiers share the same event contract |
| Files grew past 1000 lines | Hard to review, hard for LLM tooling | 200-line budget enforced by a test |
| Cost tracking optimistic | Unknown prices silently counted as 0 | `cost_usd=None` counts as `unknown_cost_calls` and is shown in the UI |
| Vietnamese strings scattered | Identifier drift, hard to localise | `texts.py` and `i18n/vi.ts` only |

## Runtime shape

```
browser ──/api (JSON + SSE)──▶ FastAPI ──▶ run_turn(conversation)
                                           │  ProviderChain (ordered routes, fallback before first item)
                                           │  ToolRegistry (workspace, web, memory)
                                           │  Skills (system-prompt fragments)
                                           └─ Store (SQLite: conversations, messages, approvals)
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

## Web UI

React + Vite, no state library: `thread-reducer.ts` is a pure function over the same
`AgentEvent` union the server emits, so the reducer test suite and the backend SSE tests pin the
contract from both sides. `use-thread.ts` owns one conversation (load, stream, approve, abort);
`use-conversations.ts` owns the list. All strings come from `i18n/vi.ts`.

## Extension points

- Provider: implement `Provider.stream` (`llm/provider.py`) and register it in `build_providers`.
- Tool: a `Tool` with `spec` + `run`; set `requires_approval` when it changes state.
- Skill: a Markdown file with `name` (and optional `always`, `description`) in `MY_AGENT_HOME/skills`.
