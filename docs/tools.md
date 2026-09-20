# Tools

A tool is a function the model can call during a turn (`tools/registry.py`). Every agent
gets the same set, assembled in `server/runtime.py` from the `build_*_tools` helpers
with the agent's workspace and memory paths.
The system prompt lists the available names; the model sees each tool's JSON schema.

## Common rules

- **Arguments are validated** against the schema before the tool runs; a bad call is
  returned to the model as an error, not raised.
- **Output is capped** at 8 000 characters (`MAX_OUTPUT_CHARS`) before it enters the
  context; the cut is marked.
- **Errors are honest.** A `ToolError` is returned to the model as "Công cụ lỗi: …"; any
  other exception is logged with its traceback and returned by type name. The prompt frame
  tells the model to report a failed tool instead of pretending.
- **Approval.** A tool with `requires_approval` pauses the turn with an `approval_required`
  event and a stored `Approval`. The web UI shows a bar, Telegram shows `/approve` /
  `/deny`; the decision resumes the same turn. A conversation (or agent) marked
  `autonomous` skips the pause — except for a `shell_run` command matching
  `settings.shell_ask_patterns` (see [Shell](#shell)), which asks anyway and says which
  pattern matched. Hard denials, workspace escapes and private network targets, are not
  approvable.
- **Content is data.** The frame tells the model that anything a tool returns is data,
  never instructions.

## The tools

| Tool | Approval | Limits | What it does |
|---|---|---|---|
| `workspace_list` | no | — | lists a directory inside the workspace |
| `workspace_read` | no | 20 000 chars (`MAX_READ_CHARS`) | reads a text file inside the workspace |
| `workspace_write` | **yes** | — | writes a text file inside the workspace, creating parents |
| `fetch_url` | no | 6 000 chars (`MAX_PAGE_CHARS`), 20 s, no redirects | GET of a public http(s) page, HTML reduced to text |
| `web_search` | no | 5 results | only with `BRAVE_API_KEY` or `TAVILY_API_KEY` (Brave preferred); returns title, URL, snippet |
| `memory_save` | no | — | appends `- HH:MM text` to today's note, see [memory.md](memory.md) |
| `memory_search` | no | 12 hits (`MAX_HITS`) | searches the shared user facts, then `MEMORY.md` and every daily note, newest first; every term must match |
| `user_memory_save` | no | — | remembers one thing about the person, shared by the whole crew, see [memory.md](memory.md) |
| `user_memory_forget` | no | — | drops one remembered fact by name |
| `shell_run` | **yes** | 120 s default, 900 s max | runs a command in the workspace, returns stdout+stderr |
| `skill_read` | no | — | returns one skill's full text by name, see [agents.md](agents.md#skills) |

### Workspace tools

Paths are resolved with `resolve_inside(root, relative)`: `..` and absolute paths that
leave the workspace are refused, symlinks that stay inside are followed. The workspace is
`agent.yaml: workspace`, default `<agent dir>/workspace`. Nothing outside it is reachable
through these tools; `shell_run` is the escape hatch, and it needs approval.

### Shared user memory

`user_memory_save` and `user_memory_forget` write to `<home>/users/owner/`, one file per
fact under `facts/` plus a regenerated `INDEX.md`. That directory is the same for every
agent, so what one agent learns about the person, the whole crew sees on its next turn.

Whether a write lands immediately depends on who asked for it. In a chat or Telegram turn
the person is right there and can object, so the fact is written at once. In a scheduled
job nobody is watching, so the same call becomes a row in `memory_proposals` with status
`pending`, and nothing is written until someone approves it — an unattended agent cannot
rewrite the person's profile on its own. A turn that resumes after an approval keeps the
source of the turn that paused, so approving a tool on the web does not turn a job into a
chat.

Names are slugs (`a-z`, `0-9`, `-`, up to 60 characters); saving the same name again
updates that fact rather than adding a second one. `type` is one of `profile`,
`preference`, `feedback`, `project`, `reference`.

The per-agent side has no forget tool to match: `MEMORY.md` is rewritten deliberately, by
the person or by the consolidation job in [memory.md](memory.md), never dropped a line at
a time by a tool call.

### Web tools

`fetch_url` resolves the host first and refuses private, loopback, link-local, reserved
and multicast addresses; it does not follow redirects, so a public URL that bounces to an
internal one fails closed. Only `http` and `https`. `web_search` picks Brave when both keys
are present.

### Shell

`shell_run` executes in the agent workspace with a minimal environment (`PATH`, `HOME`,
`LANG`, `LC_ALL`, `TERM`, `TMPDIR`, `USER`, `SHELL`), so the model never sees the server's
API keys. Timeout comes from the `timeout_s` argument, capped at 900 s. A non-zero exit is
a `ToolError` carrying the last 4 000 characters of output. A scheduled `command` job uses
the same tool and records a single step.

`autonomous` would otherwise let every command run unwatched, which is too much for the
shapes that cannot be undone. So `shell_ask_patterns` lists command fragments that get an
approval regardless — by default `rm -rf`, `rm -r `, `sudo `, `| sh`, `| bash`, `mkfs`,
`git push --force`, `git reset --hard`, `> /dev/`, `chmod -R` and `launchctl`. Matching is
a case-insensitive substring test and the approval names the pattern that matched, in the
web bar, the Telegram notice and the run card. Set the list in `config.yaml`, per agent in
`agent.yaml`, or through `MY_AGENT_SHELL_ASK_PATTERNS` (separated by `;`); declaring it
replaces the defaults and an empty list turns the guard off.

This is a soft second guard, not a sandbox: `rm  -rf` with two spaces, or the same command
built inside `$(…)`, walks straight past it. It catches the obvious mistake, not a
determined one.

### Media

An assistant line `MEDIA:<path relative to the workspace>` is not a tool; it is a
convention the frame teaches. The web UI renders it through
`GET /api/agents/{id}/files?path=`, which serves files from inside the workspace only;
Telegram turns it into `sendPhoto`.

## Echo provider and `/tool`

With `MY_AGENT_ROUTES=fake:echo` no model is called and a message `/tool <name> {json}`
runs that tool through the real registry and approval path. This is how the live smoke
and the browser tests drive tools without a key.

## Adding a tool

Create a `Tool(name, description, parameters, run, requires_approval)` in a builder next
to the existing ones and add it to the list in `server/runtime.py`. Description and parameter texts are shown to the model,
so write them in the prompt language (`texts.py` for Vietnamese). Set `requires_approval`
whenever the tool changes state outside the conversation. Add a row to
[testing.md](testing.md) and a test next to `test_tools_*.py`.

## Compared with openclaw

openclaw ships many more tools (browser, cron, messaging, sub-agents, canvas) and a
per-agent allow/deny list. Here the set is fixed and small on purpose: file, web, memory,
shell, with approval as the safety layer instead of allow-lists — and, once a conversation
is autonomous, approval by command pattern. Skills cover the rest:
a skill can describe a script in its folder and the model runs it with `shell_run`.
