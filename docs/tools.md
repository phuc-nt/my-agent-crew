# Tools

A tool is a function the model can call during a turn (`tools/registry.py`). Every agent
gets the same set, assembled in `server/runtime.py` from the `build_*_tools` helpers
with the agent's workspace and memory paths.
The system prompt lists the available names; the model sees each tool's JSON schema.

## Common rules

- **Arguments are validated** against the schema before the tool runs; a bad call is
  returned to the model as an error, not raised.
- **Output is capped** before it enters the context; how it was brought under the cap is
  marked. The default is 8 000 characters (`tool_output_chars` in `config.yaml` or
  `MY_AGENT_TOOL_OUTPUT_CHARS`); an agent whose scripts print more raises its own cap with
  `tool_output_chars` in its profile without the rest of the crew paying for it.

  An over-cap output is shortened in one of three ways, and the run card says which:

  | How | When | What survives |
  | --- | --- | --- |
  | structure | the output parses as JSON | every key; arrays lose their tail, long strings lose their middle, and the result still parses |
  | summary | anything else long enough to split | the opening and the ending word for word, with a model's summary of the middle between two labels saying so |
  | cut | everything else, and whenever a summary fails | the opening, with the number of dropped characters |

  Numbers are never rewritten by the structural path: ledger figures and health readings
  travel through it, and a summary that rounds a number is worse than one that omits a row.
  The summary path asks the agent's own routes and is charged to the run like any other
  model call. It is an improvement on a cut, never a precondition for one — no route, a
  failing route, a slow one or an empty answer all fall back to the plain cut, and the tool
  answers either way.

  This is why a raised cap is still the right answer for one kind of file: a long document
  the agent must copy out of, such as a schema note holding the exact column names and the
  SQL a scheduled job runs. Shortening it goes down the summary path, and a summary rewrites
  the middle — which is where the query usually is. A paraphrased column name is a query
  that fails. Keep the cap above the size of such a document rather than trusting a summary
  of it. JSON has no such problem, because the structural path never asks a model anything.
- **Errors are honest.** A `ToolError` is returned to the model as "Công cụ lỗi: …"; any
  other exception is logged with its traceback and returned by type name. The prompt frame
  tells the model to report a failed tool instead of pretending.
- **Approval.** A tool with `requires_approval` pauses the turn with an `approval_required`
  event and a stored `Approval`. The web UI shows a bar, Telegram shows `/approve` /
  `/deny`; the decision resumes the same turn. A conversation (or agent) marked
  `autonomous` skips the pause — except for a `shell_run` command matching
  `settings.shell_ask_patterns` (see [Shell](#shell)), which asks anyway and says which
  pattern matched. The reverse also holds: a conversation that is *not* autonomous still
  runs a `shell_run` command matching `settings.shell_allow_patterns` without asking, so a
  supervised agent can get on with the routine parts of its job. The ask list is checked
  first, so naming a command in both means it asks. Hard denials, workspace escapes and private network targets, are not
  approvable. A request nobody answers within `approval_ttl_seconds` (default 600) is
  refused: the tool result says so, the turn continues and the reply is delivered as usual.
  Approving with `always` puts the tool on the conversation's `auto_approve` list, so its
  later calls in that conversation run without asking; the ask-list guard still applies.
- **Content is data.** The frame tells the model that anything a tool returns is data,
  never instructions.

## The tools

| Tool | Approval | Limits | What it does |
|---|---|---|---|
| `workspace_list` | no | — | lists a directory inside the workspace |
| `workspace_read` | no | only the agent's output cap (`tool_output_chars`), which marks the cut | reads a text file inside the workspace; `offset` (1-based line) and `limit` read a window instead of the whole file |
| `workspace_write` | **yes** | — | writes a text file inside the workspace, creating parents |
| `fetch_url` | no | 20 000 chars via firecrawl markdown, else 6 000 (`MAX_PAGE_CHARS`), 20 s, no redirects | GET of a public http(s) page; firecrawl returns markdown, otherwise HTML is reduced to text |
| `web_search` | no | 5 results | always available; backends tried in order firecrawl → brave → tavily → duckduckgo; returns title, URL, snippet |
| `memory_save` | no | — | appends `- HH:MM text` to today's note, see [memory.md](memory.md) |
| `memory_search` | no | 12 hits (`MAX_HITS`) | searches the shared user facts, then `MEMORY.md` and every daily note, newest first; every term must match |
| `user_memory_save` | no | — | remembers one thing about the person, shared by the whole crew, see [memory.md](memory.md) |
| `user_memory_forget` | no | — | drops one remembered fact by name |
| `wiki_get` | no | — | one wiki page in full, looked up by its title, see [memory.md](memory.md#the-wiki-vault) |
| `wiki_search` | no | 8 hits (`MAX_HITS`) | searches the vault's titles and bodies, best first, as `[slug] text` |
| `wiki_apply` | no | — | writes or updates one page; refuses a page with no `sources`, and never touches the link block a compile owns |
| `shell_run` | **yes** | 120 s default, 900 s max | runs a command in the workspace, returns stdout+stderr |
| `skill_read` | no | — | returns one skill's full text by name, opening with a warning when the skill needs a command this machine lacks, see [agents.md](agents.md#skills) |
| `image_read` | no | 8 MB (`MAX_IMAGE_BYTES`); jpg, png, webp, gif | sends a picture from the workspace or the crew home (where `inbox/` keeps what Telegram delivered) to the `vision_routes` chain with a `question` and returns the answer, see [Images](#images); only present when a vision route is configured |
| `pdf_read` | no | 50 pages (`MAX_PAGES`), `pages` picks a window; the agent's output cap applies | reads a PDF from the workspace or the crew home; typeset pages come back as text, scanned pages go through the vision chain, see [PDFs](#pdfs) |
| `ask_user` | **yes, always** | one open question per conversation | asks the person one thing and pauses the turn until they answer, see [Asking the person](#asking-the-person) |
| `progress_note` | no | 200 chars | says in one line what the agent is about to do; becomes a `note` step on the run, see [Saying what it is doing](#saying-what-it-is-doing) |

Four more come with `mode: work` only, because an assistant that chats has no use for
them and every extra tool spec costs prompt tokens:

| Tool | Approval | Limits | What it does |
|---|---|---|---|
| `workspace_edit` | **yes** | 40 diff lines shown (`MAX_DIFF_LINES`) | replaces an exact snippet in one file; refuses when the snippet is missing or matches more than once, unless `replace_all` |
| `workspace_grep` | no | 200 hits (`MAX_RESULTS`), 30 s | regex search over the workspace; uses `rg` when installed, otherwise walks the tree itself. Skips `.git`, `.venv`, `node_modules`, `__pycache__`, `dist`, `build` and binary files |
| `workspace_glob` | no | 500 paths (`MAX_GLOB_RESULTS`) | lists files matching a glob, same skip list |
| `delegate` | no | 8 per conversation (`MAX_DELEGATES`), 8 at once (`MAX_PARALLEL_CALLS`) | hands a whole task to another agent and waits for its answer, see below |

### Delegation

`delegate` opens a new conversation for the agent named in `agent` — one of the caller's
`delegates`, or itself — runs the task there, and returns that conversation's last reply
with a header line giving its id, status, cost and step count. The child starts empty: it
never sees the parent's history, which is the point, so `task` has to carry everything it
needs. The parent's own context grows by one tool result instead of by the whole job, and
that result is never stubbed by the old-tool-output trim (`PINNED_TOOLS` in
`context_trim`): the master that asks Pong, then the coach, then comes back to Pong's
topic still has Pong's answer in full.

Several `delegate` calls in one assistant message run at the same time; every other tool
still runs one at a time, because the rest of them touch the workspace and would race.

Every `mode: work` agent gets `delegate` unless it states a `tools` allow-list that leaves
it out. An allow-list caps what the agent gets, and that cap covers this tool too, so a
specialist stays a specialist rather than quietly becoming a lead.

Depth stops at one. A delegated agent is handed its toolbox without `delegate` in it, and
the tool refuses to run when the turn it is in is already a delegated one — two guards,
because a fan-out that gets loose spends real money. The child inherits the parent's
approval stance and whatever is left of its budget, and what the child spends is added to
the parent, so a cap still means what it says. A turn interrupted mid-delegation finds its
child again through the tool call id rather than starting a second one.

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
internal one fails closed. Only `http` and `https`. The address guard runs before any
request, including the one to firecrawl, so a private URL never reaches a scraper either.

With `FIRECRAWL_BASE_URL` set, `fetch_url` asks firecrawl for the main content as markdown
and keeps 20 000 characters of it; headings and lists survive, which raw stripped text loses.
A firecrawl that is down or slow is not an error — the tool falls back to plain text.

`web_search` tries its backends in order and stops at the first one with results:
firecrawl, then Brave, then Tavily, then DuckDuckGo. DuckDuckGo needs no key and closes
the list, so the tool exists on every machine and an agent that lists it in `tools:` can
always use it. A backend that fails is logged and skipped; only when every backend fails
does the tool report the search service as unreachable, which keeps "no results" and
"search is broken" separate answers. `FIRECRAWL_API_KEY` is optional and only sent when
set, so a self-hosted host needs no key and a mistyped base url cannot leak one.

### Shell

`shell_run` executes in the agent workspace with a minimal environment (`PATH`, `HOME`,
`LANG`, `LC_ALL`, `TERM`, `TMPDIR`, `USER`, `SHELL`), so the model never sees the server's
API keys. Timeout comes from the `timeout_s` argument, capped at 900 s. A non-zero exit is
a `ToolError` carrying the last 4 000 characters of output. A scheduled `command` job uses
the same tool and records a single step.

The allowlist is the reason a script that works in your own terminal can still fail here:
anything you exported, or put in the server's env file, is gone by the time the command
runs. A script that needs a non-secret value should read it from a file itself rather than
expect it in the environment, and a script that needs a real secret should read it from a
file only it can read. Widening the allowlist is the wrong fix — it would hand every
model-written command the server's API keys.

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

The one real boundary is `shell_network: false` in an agent's profile. Every `shell_run`
command of that agent then runs under macOS `sandbox-exec` with a profile built in
`tools/shell_sandbox.py`. Blocking the socket alone would not keep the data on the machine,
so the profile closes each route a command could use instead:

- **Network, both ways.** No outbound connection: not to the internet, not to `127.0.0.1`
  (the crew's own API is there), and not to the resolver, because looking up a made-up
  host name carries data out as well as a request does. No listening either, since a
  server left behind would hand files to anyone who connects.
- **Helpers that act for the command.** `open`, `launchctl`, `osascript`, `shortcuts` and
  `pbcopy` are denied, along with the LaunchServices and pasteboard services behind them.
  `open <url>` would otherwise have the browser, which is not sandboxed, make the request.
- **Writes, except where the profile says.** A file write is a delayed command: a line added
  to a script a scheduled job runs, a git hook, `~/.zshrc` or a LaunchAgent runs later,
  outside the sandbox and with the network. Commands may write only under
  `shell_write_paths` (paths inside the workspace) and the temp directories. An empty list
  makes the workspace read-only to the shell.

Reading files and running local programs still work, so an agent's own scripts do. The OS
enforces all of this, so `$(…)` or a script the model just wrote gets no further than a
plain `curl`. It is for the agent whose data must not leave the machine, such as one that
keeps personal finances. It does not cover what the agent itself says: its replies go to
the model provider and to whoever it answers, so a delegating agent with a network still
sees them. Where `/usr/bin/sandbox-exec` does not exist (anything but macOS) the command
is refused rather than run without the sandbox. Scheduled `command` jobs call the shell
directly and keep the network: a person wrote those lines, and a price fetch needs it. That
is why the write rule matters. `sandbox-exec` is marked deprecated in its man page but
still ships with macOS; the tests that prove the block run wherever it exists.

`shell_allow_patterns` is the mirror image, and it is empty by default. It names the
command shapes routine enough to run without asking *even when the conversation is not
autonomous*, which is what lets a supervised agent run its own tests or read its own git
status without a pause for each one. Matching is the same case-insensitive substring test,
and it is set the same three ways, with `MY_AGENT_SHELL_ALLOW_PATTERNS` as the env var.

The order between the two lists is fixed: a question always asks, then the ask list, then
the allow list, then autonomy. Naming a command in both means it asks, because someone who
calls `rm -rf` dangerous and `git` routine means `git reset --hard` to stop.

A pattern under two characters is dropped, as are the ones that look like wildcards but are
not (`*`, `.*`, `.`, `-`, `--`, `/`, `&&`, `||`, `;`, `|`). Substring matching makes `.*`
allow only a literal `.*` while reading to whoever wrote it as "allow everything", and that
misunderstanding is the danger. A bad entry is dropped rather than refusing the whole list,
so one typo cannot take an agent off the air; dropping fails safe, because the command then
asks.

Because the test is a substring and not a parse, a useful pattern names the *shape of the
operation*, never the program. A command-line tool that both reads and writes — a mail
client, a spreadsheet client, anything with subcommands — is one binary doing two very
different things, and putting the binary's name in `shell_ask_patterns` stops the reads too.
An agent whose scheduled job only ever reads then pauses every morning waiting for an
approval nobody meant to require. List the subcommands or flags that write instead, one
entry each, and check the result the only way that proves anything: run the real read
commands and the real write commands through `ask_reason` and count.

### Media and files

An assistant line `MEDIA:<path relative to the workspace>` is not a tool; it is a
convention the frame teaches. The web UI renders it through
`GET /api/agents/{id}/files?path=`, which serves files from inside the workspace only;
Telegram turns it into `sendPhoto`.

`FILE:<path>` is its sibling for documents, because Telegram treats the two differently: a
photo is re-encoded, which is right for a chart and destroys a CSV. A `FILE:` line arrives
as `sendDocument`, keeping the bytes and the filename; the web shows a download link
instead of an inline image.

A document is capped at 20 MB and must be one of `pdf`, `csv`, `md`, `txt`, `xlsx`, `json`
or `zip`. The list is a guard on the reply, not on the workspace: an agent can write
anything into its own directory, so containment alone would still let one sentence mail out
a key file or an `.env` an earlier step copied in. A path outside the workspace, a missing
file, a wrong format or an oversized one is reported into the chat rather than raised — the
prose has already been sent by then, so an exception would leave an answer promising a file
with no word about why none arrived.

### Images

The chat model on an agent's `routes` is not expected to see pictures, so `image_read`
sends the file down a chain of its own: `vision_routes` in `config.yaml` or
`MY_AGENT_VISION_ROUTES`, by default two cheap OpenRouter vision models
(`google/gemini-2.5-flash-lite`, then `qwen/qwen3-vl-8b-instruct`). An empty value turns the
tool off for every agent; a route whose provider has no key is skipped with a warning.

The path is resolved against the agent's workspace first, then the crew home, so the
master's `workspace/inbox/<file>` that a Telegram photo lands in is readable by the master
and by the agent it hands the task to. The `question` is what the vision model is asked;
without one it describes the picture. Every agent gets the tool in every mode, and an
agent's `tools` allow-list may name it without a warning when no vision route exists
(`OPTIONAL_TOOLS`). What the call cost is added to the conversation like a completion.

The master reads once to decide who the picture is for and passes the absolute path on
in the task; the specialist reads again with its own question. That is cheaper than one
long description travelling through the master's context, and the specialist gets to ask
for the fields it needs rather than the ones the master guessed at.

### PDFs

`pdf_read` resolves its path the same way `image_read` does: the agent's workspace first,
then the crew home, so a document Telegram dropped in `workspace/inbox/` is readable by
the master and by whoever it hands the task to.

A PDF holds two different kinds of page and the tool treats them differently. A typeset
page already contains its text, and pypdf hands it over for nothing. A photographed page
contains only a picture, so that page is rendered with pypdfium2 and sent down the same
`vision_routes` chain `image_read` uses, one page at a time and only for the pages that
need it. So a mixed document costs a model call per scanned page and nothing for the rest.

Pages come back under `--- Trang N ---` headings. A page that could not be read gets a
bracketed line in place of its text rather than an error, so one unreadable page never
costs you the pages that did read. With no vision route configured the tool is still
registered and typeset PDFs still work; each scanned page says it needs `vision_routes`
instead.

`pages` takes `"1-5"` or `"3"`. Leaving it out reads from the start, up to `MAX_PAGES`
(50). The text then passes through the agent's output cap like any other tool result.

### Asking the person

`ask_user` is how an agent that has hit a genuine fork gets an answer instead of guessing.
It takes a `question`, optional `options` to choose from, and a `default` to fall back on.

It reuses the approval machinery for the pause and the resume, but it is not an approval
and differs from one in three ways that matter:

- **An autonomous conversation still stops.** Autonomy means "do not ask me to authorise
  your tools", not "never speak to me". A question that auto-approved itself would be
  answered by nobody and mean nothing.
- **It closes by its own route.** A question is *answered*, not approved or denied, and
  the server refuses each route the other's rows. In the web that is the question card
  with its choices and its text box; in Telegram it is a reply to the question message,
  by number or in words.
- **Running out of time is not a refusal.** A tool nobody authorised must not run, but a
  question nobody answered still has a `default`: the agent is handed it, carries on, and
  is told to say in its reply that it decided for itself. The deadline is the shared
  `approval_ttl_seconds` (default 600), so a job that may ask while nobody is watching
  should always pass a `default`.

Because it pauses the turn, only one question can be open per conversation at a time, and
the composer stays closed while one is: the server refuses a new message while any
approval waits. The run's timeline shows the pause as its own waiting step rather than
leaving a gap that reads as an agent thinking for an hour.

### Saying what it is doing

`progress_note` is the opposite of `ask_user`: it never stops anything. An agent calls it
with one short line before a long stretch of work, and the line appears on the run's
timeline while that work is still happening, so someone watching sees "đang đọc lịch" rather
than a spinner and a guess.

It differs from every other tool in three ways:

- **It never asks.** `requires_approval` is false and nothing consults the ask list. A note
  that needed permission would arrive after the thing it was announcing.
- **Its step has its own kind.** The step is written as `note`, not `tool`, because a note
  has no duration and cannot fail — rendering it as a tool call would give the timeline a
  row that is permanently mid-flight.
- **Over-long text is shortened, not refused.** The cap is 200 characters and anything past
  it is cut. An agent that writes a paragraph gets a shorter note; it does not get an error
  in the middle of its turn.

A note is not memory. It lives on the run and dies with it, so nothing written here reaches
the next conversation — that is what `memory_write` is for.

## Providers without a key

Two of the providers need no credentials, and both exist so that something useful still
works when there is no key and no network.

`ollama` talks to a local OpenAI-compatible server at `OLLAMA_BASE_URL`, default
`http://127.0.0.1:11434/v1`. Because it needs no key it is always built, so a route like
`ollama:qwen3:8b` is available whenever ollama is actually running; nothing listening simply
falls back like any other failing route. It is the natural home for the cheap, high-volume
work — summarising long tool output, for instance, which would otherwise add a paid call to
every large result. A local model reports no price, so the run card shows the cost as
unknown rather than as zero, since those are different claims.

With `MY_AGENT_ROUTES=fake:echo` no model is called at all and a message `/tool <name>
{json}` runs that tool through the real registry and approval path. This is how the live
smoke and the browser tests drive tools without a key.

## Ai đang dùng tool nào

```
GET /api/tools → [{"name": "workspace_read", …, "agents": ["fullstack-developer", "default"], "optional": false}]
GET /api/agents/{id}/prompt → assembled system prompt this turn (includes persona, memory, skills, roster)
```

The tools union is every agent's registry, not the master's own set — a profile with a `tools`
allow-list holds fewer tools than the master, and reading one agent's registry would hide
tools the rest of the crew still uses. `agents` is who holds it, which is the answer to
"can the adviser actually edit files"; `optional` marks the tools that only exist when
their key or route is configured (`image_read`).

The `/prompt` endpoint returns the complete system prompt as assembled for the agent (useful for
debugging what the agent sees, or showing a user what the agent knows).

```
GET /api/connections → {"providers": […], "routes": […], "vision_routes": […],
                        "keys": [{"name": "OPENROUTER_API_KEY", "present": true}],
                        "telegram": [{"agent_id": "…", "token_env": "…",
                                      "configured": false, "ignored": false}]}
```

No secret's value appears in either response. A key is present or absent; a Telegram
channel is named by the *environment variable* holding its token, and the chat id is not
reported at all — enough to tell a missing key from a wrong one without putting either
into a browser tab or a screenshot. A test asserts the whole serialized body contains no
configured secret, so the property survives new fields being added. (The agent editor does
return `chat_id`, because a field nobody can see is a field nobody can edit; this view is
the one people screenshot, so it stays down to what diagnoses a connection.)

`configured` is that row's own environment variable, not whether the crew has a channel at
all — otherwise an agent whose token was never set would read as working. `ignored` marks
a `telegram` block on a non-master profile: only the master's builds a channel, so the page
says so rather than showing one that never runs.

## Adding a tool

Create a `Tool(name, description, parameters, run, requires_approval, parallel)` in a
builder next to the existing ones and add it to the list in `server/runtime.py`. Set
`parallel` only when two calls to the tool in one message may safely overlap — a read is
fine, a write to the same file is not. Description and parameter texts are shown to the model,
so write them in the prompt language (`texts.py` for Vietnamese). Set `requires_approval`
whenever the tool changes state outside the conversation. Add a row to
[testing.md](testing.md) and a test next to `test_tools_*.py`.

## Compared with openclaw

openclaw ships more tools (browser, canvas, richer messaging). Here the catalogue is fixed
and small on purpose: file, web, memory, shell. An agent's own set is narrower than the
catalogue in three ways — `tools` in its profile is an allow-list, `workspace_edit` and the
search tools only exist under `mode: work`, and `image_read` only when a vision chain was
built. `delegate` is conditional too: the master has it, a work agent has it, any profile
naming `delegates` has it, and a delegated child never does.

So a per-agent allow-list over tool names exists here as well. The real difference is what
carries the safety weight. openclaw leans on tool visibility; here that mostly separates
roles — an adviser that cannot write, a researcher that cannot run a shell — while the guard
against a dangerous call is approval, and the two pattern lists shape it from both sides.
`shell_ask_patterns` pulls a command back into asking even in an autonomous conversation;
`shell_allow_patterns` lets a routine one through even in a supervised one. Both match a
command shape rather than a tool name, which is the distinction that matters: one
`shell_run` can be anything from `ls` to `rm -rf`, so no list over tool names could ever
express "yes to tests, no to deletions".

Skills cover the rest: a skill can describe a script in its folder and the model runs it
with `shell_run`.
