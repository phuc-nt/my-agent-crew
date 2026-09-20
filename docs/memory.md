# Memory

Memory is two kinds of Markdown in the agent dir, the same shape a person could keep by
hand. Nothing is embedded or summarised behind the agent's back; what the model reads is
what is on disk. Source of truth: `agents/context.py`, `tools/memory.py`.

| File | Role | Read into the prompt |
|---|---|---|
| `MEMORY.md` | durable facts: who the user is, standing preferences, decisions, how things are set up | every turn |
| `memory/YYYY-MM-DD.md` | daily notes: what happened, measurements, what was said | today's and yesterday's file, every turn |
| older `memory/*.md` | history | only through `memory_search` |

Each file becomes a `## <file name>` section of the system prompt, capped at 24 000
characters (`MAX_SECTION_CHARS`, cut with a trailing `…`). A missing file is simply
skipped. Paths: `profile.memory_file = <agent dir>/MEMORY.md`,
`profile.memory_dir = <agent dir>/memory` (created at startup). The default agent keeps
them in `MY_AGENT_HOME` itself.

## Writing memory

Two ways, both visible in the activity rail:

- **`memory_save`** appends one line `- HH:MM <text>` to today's note, creating it with a
  `# YYYY-MM-DD` header. No approval: a note is not a state change outside the
  conversation. Use it for things worth remembering tomorrow.
- **`workspace_write` / `shell_run`** for `MEMORY.md` and for rewriting a note, because
  durable memory should be edited deliberately. `workspace_write` reaches these files only
  when the workspace is the agent dir; otherwise the persona file (`AGENTS.md`) should say
  how the agent maintains `MEMORY.md`, for example with a `shell_run` heredoc or a script.

## Reading memory

- **`memory_search <query>`** greps `MEMORY.md` and then every daily note, newest first,
  and returns up to 12 lines (`MAX_HITS`) that contain **every** term of the query, case
  insensitive, as `<file>: <line>`. Use it before answering "when did I…" or "what did we
  decide about…".
- The prompt already holds `MEMORY.md` and the last two days, so the model should not
  search for those.

## What goes where

| Write to | Examples |
|---|---|
| `MEMORY.md` | user profile, goals, thresholds, tool locations, recurring schedule, rules the user gave |
| today's note | a measurement, a decision made today, a question left open, a brief that was sent |
| neither | anything the workspace files already hold (data files, scripts), transient tool output |

Persona files (`AGENTS.md` and friends, see [agents.md](agents.md)) are for *how to
behave*; memory is for *what is known*. Both are personal data and stay in
`MY_AGENT_HOME`, never in this repo.

## Compared with openclaw

The file names and roles match openclaw's workspace memory (`MEMORY.md`,
`memory/YYYY-MM-DD.md`) so an existing workspace can be reused. openclaw adds a vector
index and a `memory_search` with semantic ranking; here search is a plain grep, ordered by
file recency, which is enough for a single user's notes and keeps the result explainable.
There is no automatic summarisation or pruning: when `MEMORY.md` nears the 24 000-char
cap, the agent (or the user) rewrites it. Tests: `test_tools_memory.py`,
`test_agent_context.py`.
