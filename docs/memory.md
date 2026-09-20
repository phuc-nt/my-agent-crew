# Memory

Memory is Markdown on disk, the same shape a person could keep by hand. Nothing is
embedded or summarised behind the agent's back; what the model reads is what is on disk.
Source of truth: `agents/context.py`, `memory/user_store.py`, `memory/agent_store.py`,
`tools/memory.py`.

It comes in two scopes:

- **Shared** — what the crew knows about *the person*, under `<home>/users/owner/`. Every
  agent reads the same files, so telling one agent something does not leave the others
  guessing.
- **Per agent** — what one agent knows about *its own work*, in its agent dir.

## The shared scope

| File | Role | Read into the prompt |
|---|---|---|
| `users/owner/USER.md` | who the person is, in their own words | every turn, every agent |
| `users/owner/facts/<name>.md` | one remembered fact each: frontmatter + Markdown body | only its index line; the body through `memory_search` or `workspace_read` |
| `users/owner/facts/INDEX.md` | generated table of contents, one line per fact | every turn, every agent |

The user sections are capped at 4 000 characters (`MAX_USER_SECTION_CHARS`) because they
ride along in every agent's prompt. A fact's frontmatter records `name`, `description`,
`type` (one of `profile`, `preference`, `feedback`, `project`, `reference`), `written_by`,
`source` and `updated`; `INDEX.md` is regenerated after every write.

## One agent's own scope

| File | Role | Read into the prompt |
|---|---|---|
| `MEMORY.md` | durable facts: who the user is, standing preferences, decisions, how things are set up | every turn |
| `memory/YYYY-MM-DD.md` | daily notes: what happened, measurements, what was said | today's and yesterday's file, every turn |
| older `memory/*.md` | history | only through `memory_search` |

A note is named after its day, with an optional suffix — `2026-09-19.md` and
`2026-09-19-1030.md` are both notes of 19 September, which is how a workspace written by
another tool keeps several notes a day. The suffix is lowercase letters, digits and
hyphens, so a name can never point outside the folder. `memory_save` always writes the
plain `YYYY-MM-DD.md`, and only that name is read into the prompt; a suffixed note is
history, reached through `memory_search`, the Ghi nhớ tab and consolidation.

Each file becomes a `## <file name>` section of the system prompt, capped at 24 000
characters (`MAX_SECTION_CHARS`, cut with a trailing `…`). A missing file is simply
skipped. Paths: `profile.memory_file = <agent dir>/MEMORY.md`,
`profile.memory_dir = <agent dir>/memory` (created at startup). The default agent keeps
them in `MY_AGENT_HOME` itself.

## Writing memory

Several ways, all visible in the activity rail:

- **`user_memory_save` / `user_memory_forget`** write a shared fact. Whether they write at
  all depends on who is in the room: in a turn the person is present for (chat, Telegram)
  the write lands immediately; in a scheduled job it becomes a **proposal** for review,
  because nobody is there to correct a bad guess. Resuming a paused job keeps the job's
  source, so an approval mid-job does not turn it into a chat turn.
- **`memory_save`** appends one line `- HH:MM <text>` to today's note, creating it with a
  `# YYYY-MM-DD` header. No approval: a note is not a state change outside the
  conversation. Use it for things worth remembering tomorrow.
- **`workspace_write` / `shell_run`** for `MEMORY.md` and for rewriting a note, because
  durable memory should be edited deliberately. `workspace_write` reaches these files only
  when the workspace is the agent dir; otherwise the persona file (`AGENTS.md`) should say
  how the agent maintains `MEMORY.md`, for example with a `shell_run` heredoc or a script.

## Reading memory

- **`memory_search <query>`** returns up to 12 hits (`MAX_HITS`) as `[<file> › <heading>]
  <entry>`. The unit is the **entry**, not the line: a bullet together with its indented
  continuation lines, or a paragraph. A thought written over two lines — `- Jimny 5 cửa,` /
  `  ngân sách 1.5 tỷ` — is one hit with both halves, which matching line by line loses.
  The heading the entry sits under travels with it, both as context in the label and as
  text that can be matched.
- Matching ignores accents on both sides, so `sach dang doc` finds `sách đang đọc`: a
  person searching their own notes from a phone rarely types the marks. `đ` is handled on
  its own, since it is a letter of the Vietnamese alphabet rather than a `d` with a mark
  and decomposition leaves it untouched.
- Ranking prefers the entry that has the **word**: a word found whole scores double a word
  found inside another, because without accents `doc` sits inside `docs` as surely as
  inside `đọc`. A word of three characters or fewer only counts when found whole — `ô`
  becomes `o`, which is inside nearly every Vietnamese entry. When some entry has every
  word of the query, entries missing one are dropped; when none does, the partial matches
  are still shown, since half an answer beats none.
- The file order breaks ties: shared facts first — what the crew knows about the person
  outranks one agent's notes — then `MEMORY.md` and every markdown file in the memory
  folder, newest first, so a fresh note outranks an old one at the same score. Files that
  are not dated notes are searched too, because a workspace written by hand keeps things
  like `facebook-books.md` there and they are memory as well. A fact matches on its
  description and body together and reports both, since a fact is one thought.
- A hit longer than 300 characters (`MAX_CHARS`) is folded onto one line and cut with `…`.
- The prompt already holds `MEMORY.md` and the last two days, so the model should not
  search for those.

## What goes where

| Write to | Examples |
|---|---|
| `USER.md` | name, work, how the person likes to be answered |
| a fact | a standing preference, a goal, feedback the person gave, a project they are on |
| `MEMORY.md` | user profile, goals, thresholds, tool locations, recurring schedule, rules the user gave |
| today's note | a measurement, a decision made today, a question left open, a brief that was sent |
| neither | anything the workspace files already hold (data files, scripts), transient tool output |

Persona files (`AGENTS.md` and friends, see [agents.md](agents.md)) are for *how to
behave*; memory is for *what is known*. Both are personal data and stay in
`MY_AGENT_HOME`, never in this repo.

## Proposals

A job runs unattended, so a shared write it asks for is held in the `memory_proposals`
table until someone decides. Approving applies the write; rejecting leaves nothing behind.
Deciding the same proposal twice is a conflict, not a fresh write, so a double click
cannot apply it again. `GET /api/stats` carries `pending_proposals` so the web UI can
badge the tab. Source: `store/memory_proposals.py`, `memory/proposals_apply.py`.

## Consolidation

Memory only grows: every turn can append, nothing removes, so `MEMORY.md` drifts towards a
long list of things that were true once. Consolidation asks the model to rewrite the file
from the recent daily notes — keep what still holds, merge repeats, drop what mattered for
a day — and **proposes** the result rather than writing it, because a rewrite can lose
something and nobody watches a scheduled job. The proposal carries `previous_body`, the
text it replaces, so one step back is always possible from the history list.

An agent opts in with a `memory_consolidate` cron in its profile, which becomes an
ordinary schedule (kind `consolidate`) next to its prompt and command jobs. It reads up to
7 days of notes (`MAX_NOTES`, counted in days rather than files, so several notes of one
day still count as that one day) within a 40 000-character budget, newest first, and does
nothing at all when no note is newer than `MEMORY.md`. An agent marked `autonomous` applies
the rewrite immediately; everyone else sees it in **Ghi nhớ → Đề xuất**. The run appears in
Activity with its cost, and a failed rewrite leaves the file exactly as it was. Source:
`memory/consolidate.py`, `scheduler/jobs.py`.

## What one agent sees of another

On a shared Telegram bot several agents answer in one thread, so a person can tell Pong
something and then ask the coach about it. Each agent still holds its own conversation, so
the coach would otherwise see none of that. Before a turn on a channel, the last 10 lines
the *other* agents exchanged in that chat **today** are lifted into the prompt as a
read-only section, one line each as `[Tên agent] role: text`, cut to 300 characters a line
and 4 000 in total. Tool traffic is left out — it is not something a reader of the chat
would have seen — and the agent's own lines are not repeated, since they are already in
its history. A private channel has one agent and the web has no channel, so neither gets
the section. Source: `memory/shared_chat.py`.

## Over HTTP and in the web UI

Everything the agent sees in its prompt is editable by the person, so they are never
arguing with a memory they cannot reach. Routers: `server/routes_memory_user.py` (shared
scope, search, proposals) and `server/routes_memory_agent.py` (one agent's files).

| Endpoint | Does |
|---|---|
| `GET/PUT /api/memory/user` | read/write `USER.md`, with the facts and the index |
| `PUT/DELETE /api/memory/user/facts/{name}` | upsert or forget one fact; a non-slug name or unknown type is a 422 |
| `GET/PUT /api/agents/{id}/memory` | read/write that agent's `MEMORY.md` |
| `GET/PUT /api/agents/{id}/memory/notes/{day}` | read/write one dated note; a name that is not a day with an optional suffix is a 422 |
| `GET /api/memory/search?q=&agent_id=` | hits across both scopes, each labelled with the scope it came from |
| `GET /api/memory/proposals?status=` | pending by default; `status=all` includes decided ones |
| `POST /api/memory/proposals/{id}` | `{approve: bool}`; deciding twice is a 409 |
| `POST /api/agents/{id}/memory/consolidate` | starts a rewrite and answers 202; 409 while one is already running for that agent |

The **Ghi nhớ** tab in the activity rail is these endpoints: edit `USER.md`, add or forget
facts, edit each agent's `MEMORY.md` and notes, search every scope, and approve or reject
what a job proposed — an `agent_memory` proposal shows which lines it would add, and a
rewrite is shown against the text it replaces with an **Hoàn tác** button in the history.
**Cô đọng ngay** asks for a rewrite without waiting for the cron.

## Compared with openclaw

The file names and roles match openclaw's workspace memory (`MEMORY.md`,
`memory/YYYY-MM-DD.md`) so an existing workspace can be reused. openclaw adds a vector
index and a `memory_search` with semantic ranking; here search is a plain grep, ordered by
file recency, which is enough for a single user's notes and keeps the result explainable.
Pruning here is the consolidation job above, which openclaw has no equivalent of: it
proposes a rewrite on a schedule and keeps what it replaced. The shared user scope has no
openclaw equivalent either: openclaw keeps one workspace per agent, so a fact about the
person learned by one agent stays there. Tests: `test_tools_memory.py`, `test_tools_memory_user.py`,
`test_agent_context.py`, `test_memory_user_store.py`, `test_memory_agent_store.py`,
`test_memory_proposals_apply.py`, `test_server_memory_api.py`,
`test_memory_consolidate.py`, `test_memory_shared_chat.py`.
