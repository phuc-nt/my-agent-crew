# Agents

An **agent** is one folder under `MY_AGENT_HOME/agents/<id>/` with an `agent.yaml` and a
few Markdown files. Every agent runs the same loop (`agent/loop.py`); the profile only
changes its inputs: persona, memory, workspace, skills, model routes, budget and schedules.
The Telegram channel belongs to the master alone. Source of truth: `agents/profile.py`,
`agents/channels.py`, `config.py`.

## Folder layout

```
MY_AGENT_HOME/                      ~/.my-agent-crew by default
├── config.yaml                     global, non-secret keys (see below)
├── agent.sqlite3                   conversations, messages, runs, job state
├── agent.yaml                      the master's profile, incl. its `telegram` block (optional)
├── workspace/                      sandbox of the master; `inbox/` takes Telegram attachments
├── skills/                         skills of the master
├── telegram.offset                 poll offset of the master's bot
├── users/owner/                    what the crew knows about the person (see memory.md)
│   ├── USER.md                     read by every agent, every turn
│   └── facts/<name>.md  INDEX.md   one fact each, plus the generated index
├── .agents/                        a kit (also `.claude/`, `.opencode/`), see Kits below
│   ├── agents/<id>.md              one crew member per file, front matter + persona
│   ├── commands/**/*.md            slash commands, `commands/mk/plan.md` is `/mk:plan`
│   ├── skills/                     skills for every agent
│   └── settings.json               `hooks.PreToolUse` / `PostToolUse` command hooks
└── agents/
    └── <id>/
        ├── agent.yaml              the profile (fixed key set, no secrets)
        ├── AGENTS.md  SOUL.md      persona files, read every turn
        ├── IDENTITY.md  USER.md
        ├── MEMORY.md               durable memory, read every turn
        ├── memory/YYYY-MM-DD.md    daily notes, today + yesterday read every turn
        ├── workspace/              default tool sandbox (overridable)
        ├── skills/                 always on the skill path
        └── .agents/                this agent's own kit (optional)
```

`ensure_agent_dirs` creates the agent dir, workspace and `memory/` at startup, so a
profile plus persona files is enough. The agent id is the folder name; `default` is
reserved for the top-level settings (see below).

## `agent.yaml`

Only these keys are accepted; anything else raises `ValueError` at startup so a typo never
silently disables a setting.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `name` | string | the id | display name; also the `[Name]` prefix on a brief delivered to Telegram |
| `description` | string | `""` | shown on the agent's card in the crew tab and in the master's roster |
| `mode` | `assistant` or `work` | `assistant` | `work` adds the coding tools and moves three defaults, see [Work mode](#work-mode) |
| `routes` | list or comma string of `provider:model` | global `routes` | tried in order; a route that fails before producing output falls through to the next |
| `workspace` | path | `workspace` | sandbox for `workspace_*` and `shell_run`; relative paths resolve against the agent dir, `~` expands |
| `persona_files` | list of file names | `AGENTS.md, SOUL.md, IDENTITY.md, USER.md` | read from the agent dir into the system prompt each turn; missing files are skipped |
| `persona_names` | read-only | — | list of persona file names actually present (returned by `GET /api/agents/{id}` and `GET /api/agents/{id}/prompt`) |
| `skills_dirs` | list of paths | `[]` | extra skill folders; `<agent dir>/skills` is always first |
| `cost_cap_usd` | number ≥ 0 | global | budget per conversation, `0` = unlimited |
| `max_steps` | int ≥ 1 | global | model calls per turn before a `halted` |
| `autonomous` | bool | global `autonomous_default` | new conversations skip tool approval |
| `shell_ask_patterns` | list of strings | global | shell commands that ask anyway when autonomous, see [tools.md](tools.md#shell); declaring it replaces the defaults, `[]` turns the guard off |
| `tool_output_chars` | int ≥ 1 | global | characters of one tool result the model sees before the cut; raise it for an agent whose scripts print long reports |
| `schedules` | list | `[]` | jobs, see [Schedules](#schedules) |
| `memory_consolidate` | cron string | none | rewrite `MEMORY.md` from the daily notes on this schedule, see [memory.md](memory.md) |
| `telegram` | map | none | `token_env` + `chat_id`; read on the master's `agent.yaml` only, ignored with a warning elsewhere, see [channels.md](channels.md) |
| `delegates` | list of agent ids | `[]` | agents this one may hand a task to; an id that names no agent is a startup error. Empty on the master means every other agent, see [The master agent](#the-master-agent) |
| `tools` | list of tool names | `[]` | when set, the only tools this agent gets; empty means everything its mode brings. An unknown name is a warning, so a profile written for a newer version still starts |

Every value that is not set falls back to the global settings, which come from env vars
and `config.yaml`:

| Env var | `config.yaml` key | Default |
|---|---|---|
| `MY_AGENT_HOME` | — | `~/.my-agent-crew` |
| `MY_AGENT_ROUTES` | `routes` | `openrouter:deepseek/deepseek-v4-flash` |
| `MY_AGENT_COST_CAP_USD` | `cost_cap_usd` | `0.5` |
| `MY_AGENT_MAX_STEPS` | `max_steps` | `12` |
| `MY_AGENT_AUTONOMOUS` | `autonomous_default` | off (`1`, `true`, `yes`, `on` turn it on) |
| `MY_AGENT_APPROVAL_TTL_SECONDS` | `approval_ttl_seconds` | `600`; must be ≥ 1. An approval nobody answers within this window is refused and the turn goes on |
| `MY_AGENT_SHELL_ASK_PATTERNS` | `shell_ask_patterns` | the list in [tools.md](tools.md#shell); the env value is `;`-separated and an empty one turns the guard off |
| `MY_AGENT_TOOL_OUTPUT_CHARS` | `tool_output_chars` | `8000`; must be ≥ 1 |
| `MY_AGENT_LANGUAGE` | `language` | `vi` (prompt frame language; `en` is the other option) |
| `MY_AGENT_TIMEZONE` | `timezone` | the machine zone; an IANA name (`Asia/Ho_Chi_Minh`) sets the zone that schedules, "today" in prompts and memory notes, `/status` and the stats are read in. An unknown name fails at start |
| `MY_AGENT_VISION_ROUTES` | `vision_routes` | `openrouter:google/gemini-2.5-flash-lite, openrouter:qwen/qwen3-vl-8b-instruct`; the chain `image_read` sends pictures to, see [tools.md](tools.md#images). An empty value turns image reading off |
| `OPENROUTER_API_KEY` | — | enables the OpenRouter provider |
| `BRAVE_API_KEY` / `TAVILY_API_KEY` | — | enables `web_search` |
| the name in `telegram.token_env` | — | the bot token; unset = that channel is disabled |

Env wins over `config.yaml`; `config.yaml` accepts only the keys above. Secrets never
go into YAML: profiles carry env-var **names**, and the settings drawer shows key presence,
never values.

## Work mode

`mode: assistant` is the product's normal shape: one agent that chats, asks before it
touches anything, and works within a chat-sized budget. `mode: work` is the same loop
pointed at a repository. It adds `workspace_edit`, `workspace_grep` and `workspace_glob`
(see [tools.md](tools.md#the-tools)) and moves three defaults:

| Key | Assistant | Work | Why |
|---|---|---|---|
| `autonomous` | global default (off) | `true` | a coding agent that stops for approval on every file read never finishes a task |
| `cost_cap_usd` | `0.5` | `20.0` | a real task runs dozens of steps; the chat cap would halt it halfway |
| `max_steps` | `12` | `120` | read, edit, run tests, read the failure, edit again — that is already more than 12 |

Anything the profile states itself still wins, so `mode: work` with `autonomous: false`
is a work agent that asks. These are defaults, not a locked bundle.

## Templates

Nine profiles ship with the package so a working crew is a copy rather than nine files
written by hand. A template is plain data — an `agent.yaml` and the persona files beside
it — so anything it can express, a hand-written profile can too.

```bash
python -m my_agent_crew agent list-templates        # id, mode and description of each
python -m my_agent_crew agent add coder             # one role, at the master's disposal
python -m my_agent_crew agent add dev               # the lead and the eight peers it names
python -m my_agent_crew agent add coder --id backend  # same template under a different id
python -m my_agent_crew agent add coder --workspace ~/src/app  # pinned to one repository
```

Adding a template brings the peers it delegates to, because the server refuses to start
when a `delegates` entry names an agent that is not there — so `agent add dev` gives a
whole crew in one command, while `agent add scout` gives one agent. A peer that already
exists is left as it is. Every manifest points `workspace` at `../../workspace`, the home's
shared workspace, so a fresh install works without editing; `--workspace` writes an
absolute path into the template and every peer it brings.

The same install runs over HTTP, which is what the crew tab in the web UI calls:

```
POST /api/agents/install {"template": "coder", "agent_id"?: "…", "workspace"?: "…", "force"?: false}
→ 201 {"installed": ["coder"], "live": ["coder"], "needs_restart": false}
```

`installed` is what was written, `live` what the running server loaded on the spot (the
master can delegate to it at once), and `needs_restart` is true when an installed agent has
`schedules`: jobs only start at boot. 404 for an unknown
template, 409 when the id is taken (`force` overwrites).

| id | mode | What it is for |
|---|---|---|
| `dev` | work | the lead: no tool allow-list, delegates to the other eight |
| `scout` | work | finds the files and regions that matter; read-only, no shell |
| `planner` | work | reads code and writes a plan; no shell, so planning cannot become doing |
| `coder` | work | writes and edits code, runs the commands it needs |
| `reviewer` | work | reads a diff and reports; no `workspace_edit`, so it cannot fix what it flags |
| `tester` | work | writes and runs tests |
| `debugger` | work | reproduces and diagnoses; edits but does not write new files |
| `git` | work | `shell_run` alone: stage and commit, never rewrite history |
| `researcher` | assistant | reads the web and writes a report; never touches the repo |

Each manifest points `skills_dirs` at `../../skills`, so the six shared skills are
installed once at the top of the home directory and every role reads the same copy.
Adding a template twice refuses rather than overwriting, since by then the profile may be
your edit and not ours; `--force` says you meant it. An agent added with the CLI is read
at the next start; one added through the install API or the crew tab joins the running
crew at once.

The allow-list in a template is the point of the role, and it caps `delegate` as well: a
work agent that names its tools without naming `delegate` cannot hand work on, which is
what stops a crew from growing a second layer behind the lead's back.

## Sửa agent từ web/API

A crew that can only be changed by editing files and restarting is a crew most people
never change. These endpoints write the same `agent.yaml` a person would write by hand,
and bring the result into the running server.

```
POST   /api/agents           {"agent_id": "coder", "profile": {…}}
PATCH  /api/agents/{id}      {"profile": {…}}   → {"profile": {…}, "restart_required": […]}
DELETE /api/agents/{id}                         → {"removed": "coder", "kept_at": "…"}
PUT    /api/agents/{id}/files/{name}  {"content": "…"}
GET    /api/agents/{id}/prompt                  → system prompt assembled this turn
POST   /api/agents/reload                       → {"added": ["…"]}
```

**A patch names only what it changes.** A key left out keeps its value; clearing one is
asked for with an explicit `null`. This matters because the web sends one section at a
time — a form that posted its whole model would erase every key the form has no field for.

**The file keeps its shape.** Writes are round-trip (ruamel), so comments, key order and
keys this version of the server does not know about all survive an edit made from a
browser. The manifest is written through a temp file and moved into place, so a crash
mid-write cannot leave a profile that no longer parses.

**Validation is the same code that reads a hand-written file** (`parse_profile`), run
*before* anything is written. A profile the server would refuse to start with is a 422 and
changes nothing — not the file, not the running agent. `delegates` is checked against the
crew as it would be after the edit, so you cannot point at an agent that is not there.

The order is validate, then wire, then write. Building the agent is the last step that can
fail on a profile that parsed cleanly, and a file written before that point would claim a
change the answer had refused — then apply it at the next restart. The write comes last so
the refusal is the whole story. A write that fails after a successful wire leaves the crew
briefly ahead of the file; the file is what boot reads, so that direction corrects itself.

**Paths in an edit stay under the crew home.** `workspace`, `skills_dirs` and
`persona_files` are checked after they resolve, so `~`, an absolute path or enough `..` to
leave the home is a 422. A persona file is read into the system prompt and travels to the
model on the next turn, and the workspace is what every file tool is scoped to — neither
is something a request should be able to aim anywhere on the machine. The check is on this
edit path only: a kit names its markdown by absolute path, and `agent add --workspace`
points an agent at a repo elsewhere on purpose, both of which still work.

`shell_ask_patterns` must be a list. A bare string is iterable, so `"rm"` would otherwise
become the patterns `r` and `m` and the guard that asks before a destructive command would
quietly stop meaning anything. An empty list still turns the guard off, as documented in
[tools.md](tools.md#shell) — that is a choice someone can make, silently shredding the list
is not.

**A manifest that no longer parses is reported, not overwritten** (422, naming the parse
error). A patch names a few keys; writing it over a file that broke would drop everything
else the person still had in there.

**Removing keeps the files.** `DELETE` moves `agents/<id>` to `agents/.trash/<id>-<stamp>`
and reports where it went; nothing is deleted. Conversations that agent held stay put and
fall back to the master. It refuses (409) for the master, and for an agent another agent
still names in `delegates` — removing it would leave that profile invalid and the server
unable to start next time.

**`restart_required` is only ever about schedules and Telegram.** Routes, tools, persona,
name, budget and delegation are all rebuilt live. The clock and the channel are built once
at boot, so changing `schedules`, `memory_consolidate` or `telegram` needs a restart and
says so. Nothing else does, which is what keeps the notice worth reading.

**Agents from a kit are read-only here** (409, naming the markdown file they came from):
their profile lives in a project someone else maintains, and writing an `agent.yaml` beside
it would shadow the kit rather than edit it.

`PUT …/files/{name}` writes persona files by name, and the name is matched against
`AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md` — the path never comes from the request.

## The master agent

The `default` agent always exists and is the top-level settings: dir = `MY_AGENT_HOME`,
workspace = `MY_AGENT_HOME/workspace`, skills = `MY_AGENT_HOME/skills`, persona and memory
files read from `MY_AGENT_HOME` itself. A fresh home therefore needs no profile at all.
`load_profiles` returns it first, then `agents/<id>/agent.yaml` sorted by id.

It is also the *master*: the one agent the person talks to — in the web UI and on
Telegram — and the one that hands work to the rest. `AgentProfile.is_master` is true for
it alone. An optional `MY_AGENT_HOME/agent.yaml` shapes it with the same keys as any
profile (`name`, `description`, `autonomous`, `cost_cap_usd`, `max_steps`, `routes`,
`delegates`, `telegram`, …); without the file it is the plain default agent, and
`PATCH /api/agents/default` writes that file, creating it on the first edit. It cannot be
deleted. Two things set it apart from a work lead:

- **It reaches everyone.** With `delegates` empty, the master may hand a task to every
  other agent in the home, in id order (`agents/roster.py: delegate_targets`). Installing
  an agent is enough to put it at the master's disposal; naming a `delegates` list narrows
  that to the ids given. Any other agent reaches only what it lists.
- **It always has `delegate`.** The tool is wired for the master, for work agents, and for
  any profile with a `delegates` list; a `tools` allow-list still caps it.

Each turn the master's system prompt carries a roster section (`crew_roster_section`): one
line per agent it may reach, with id, name, mode, description and workspace, followed by the guidance
on when to do a thing itself and when to hand it off. An agent that can reach nobody gets
no roster. A child turn opened by `delegate` never sees one, since it cannot delegate.

The assistant agents of the example home (`pong`, `health-coach`) are reached the same way
from the phone as from the browser: the master's bot takes the message and the master
delegates. Their schedules run as before and their briefs still land in the chat, under
their name ([channels.md](channels.md#scheduled-delivery)). Tests: `test_crew_roster.py`,
`test_api_agents_install.py`.

## Persona files

Persona files are plain Markdown; the loop concatenates each one as a `## <file name>`
section of the system prompt, after the fixed frame (`agent/prompt.py`) and before the
skills. Conventions that have worked:

| File | Put here |
|---|---|
| `AGENTS.md` | how to work: what to do at the start of a turn, which scripts to run, how to write memory |
| `SOUL.md` | tone, values, what the agent refuses |
| `IDENTITY.md` | name, role, one-line self description |
| `USER.md` | this agent's own angle on the person: what *it* needs to know to do its job |

The shared `users/owner/USER.md` ([memory.md](memory.md)) is the one every agent reads and
the place a general fact about the person belongs. An agent's own `USER.md` is a persona
file: keep it to what only that agent cares about, and point at the shared one rather than
copying it, or the two drift apart.

Each section is capped at 24 000 characters (`MAX_SECTION_CHARS`); longer files are cut
with a trailing `…`, so keep them short and move history into [memory](memory.md).
Persona files are personal data and live in `MY_AGENT_HOME`, never in this repo.

## Kits (`.agents/`, `.claude/`, `.opencode/`)

A **kit** is the folder the other harnesses keep their configuration in: Claude Code's
`.claude/`, opencode's `.opencode/`, the cross-harness `.agents/` that Codex and others read.
my-agent-crew reads all three (`agents/kit.py`, `KIT_DIRS`, in that order) so a person who
already has one can copy it in and keep their agents, commands, skills and hooks:

```
cp -r ~/.claude ~/.my-agent-crew/.agents      # or leave it named .claude, both are read
```

Two places are searched, and a later kit shadows an earlier one by name:

| Kit | Where | Brings |
|---|---|---|
| home | `MY_AGENT_HOME/.agents` (`.claude`, `.opencode`) | agents, skills, commands, hooks — for the whole crew |
| agent | `MY_AGENT_HOME/agents/<id>/.agents` | the same, for that agent only |

A kit inside an agent's **workspace** is never read, and neither is the `AGENTS.md` at its
root. The repository an agent works in (a health database, a ledger, a codebase) is a data
source: the agent runs its scripts and reads its files, but the `.claude/` there belongs to
whoever develops that repository, and its hooks and subagents were written for another
harness. What shapes a crew agent is only what sits in `MY_AGENT_HOME`.

What each part maps to:

| In the kit | Here |
|---|---|
| `agents/<id>.md` — front matter `name`, `description`, `tools`, `model`, plus our `mode`, `delegates`, `workspace`; the body is the persona | a crew member with that id (slug of `name`, else the file stem). Its memory and workspace live under `MY_AGENT_HOME/agents/<id>/` like any other; only the persona is read from the kit. A `model` written as `provider:model` becomes its `routes`; harness aliases (`sonnet`, `inherit`) mean the crew's routes. An `agents/<id>/agent.yaml` with the same id wins, so a kit never replaces an agent configured by hand |
| `tools:` in that front matter | mapped by name: `Bash`→`shell_run`, `Read`→`workspace_read`, `Write`, `Edit`/`MultiEdit`→`workspace_edit`, `Glob`, `Grep`, `LS`→`workspace_list`, `WebFetch`→`fetch_url`, `WebSearch`→`web_search`, `Task`/`Agent`→`delegate`; our own names pass through, harness-only names (`TaskCreate`, `NotebookEdit`) are dropped. Memory, `skill_read` and `image_read` are always kept. An agent that may edit is `mode: work` unless the front matter says otherwise |
| `commands/**/*.md` (front matter `description`, body the prompt) | a slash command `/name`, nested as `/dir:name`. `$ARGUMENTS` and `$1`…`$9` are filled from the message, otherwise the arguments are appended. Works in the web chat and on Telegram, where the built-in commands (`/new`, `/status`, …) keep their names; the master's prompt lists them |
| `skills/` (or opencode's `skill/`) | one more skill directory after the agent's own |
| `settings.json` → `hooks.PreToolUse` / `hooks.PostToolUse`, `type: command` entries | tool hooks, see below. Other hook kinds and events are skipped |

**Hooks** run the command with the same JSON on stdin the harnesses send:
`hook_event_name`, `tool_name`, `tool_alias` (the harness name, `Bash` for `shell_run`),
`tool_input`, `agent_id`, `cwd`, and `tool_response` after the call. The matcher is a regex
over both names, so a hook written for `Bash` fires for `shell_run`. Exit code 2, or JSON
with `decision: block` / `permissionDecision: deny`, blocks the call and the model sees the
reason; `additionalContext` is appended to the result; anything else — exit 1, a timeout
(`timeout` seconds, default 30), a missing binary — passes, because a guard that fails
must not take the agent's hands away. Commands run from the kit's parent directory with
`CLAUDE_PROJECT_DIR` and `MY_AGENT_PROJECT_DIR` set to it. Scheduled `command` jobs go
through the scheduler, not the tool registry, so hooks do not see them.

The crew tab shows, per agent, how many commands and hooks it carries and which kit roots
they came from; `GET /api/agents` returns `commands`, `hooks` and `kits`.

## Skills

A skill is a Markdown file with front matter (`name`, optional `description`, `always`,
`requires`, `cliHelp`), either `name.md` or a folder `name/SKILL.md` whose siblings
(scripts, references) the model reaches by the absolute path given in a `SKILL_LOCATION`
line. Skills load from the builtin dir (`cite-sources`), then `<agent dir>/skills`, then
each `skills_dirs` entry; a later skill with the same name overrides an earlier one.
Skills are instructions for the model, [tools](tools.md) are functions it can call.

### Front matter

| Key | Meaning |
|---|---|
| `name` | the name used everywhere; defaults to the file or folder name |
| `description` | the one line shown in the index, so the model can tell whether to read the body |
| `always` | `true` puts the whole body in every prompt |
| `requires.bins` | command-line programs the skill drives, `[gws, jq]` or a single `jq` |
| `cliHelp` | the one command that prints the real syntax, e.g. `gws --help` |

`requires.bins` is checked against the machine at load. A skill whose program is missing
is **kept**, not dropped: the index line carries `[thiếu: gws]` and the body opens with a
warning, so an agent that cannot do the job knows why instead of failing halfway through.
`cliHelp` is appended to the index line, and the system prompt carries one standing rule:
read a command's `--help` once rather than trying a third syntax. Both exist because of a
real run that burnt sixteen steps guessing flags for a program it had never seen.

```yaml
---
name: gws-shared
description: Đọc lịch và thư qua CLI gws
requires:
  bins: [gws]
cliHelp: gws --help
---
```

A skill reaches a prompt by one of three routes:

- `always: true` — its full text rides on every prompt.
- attached to the conversation, from the settings drawer or a schedule's `skills:` list —
  full text again, for the conversation the job opens.
- neither — only its name and description appear under `## Kỹ năng có sẵn`, and the model
  calls `skill_read` to pull the rest when it decides the work needs it. Above 40 indexed
  skills the descriptions are dropped so the index stays scannable.

A scheduled job that needs a skill should name it in the schedule. If it does not, one
fallback applies: a prompt that spells out a skill's hyphenated name (`gws-shared`) gets
that skill attached anyway. Only hyphenated names count, because a one-word name like
`ledger` turns up in prompts that have nothing to do with the skill.

## Schedules

Each entry in `schedules` becomes a job `<agent id>/<schedule id>` in the scheduler
(20 s tick, cron fields read in the `timezone` of `config.yaml`, the machine zone by default).

| Key | Meaning |
|---|---|
| `id` | default `job-<index>`; used in the job name and in `POST /api/jobs/{agent}/{id}/run` |
| `name` | default the id; shown in the UI |
| `cron` **or** `every` | exactly one: five-field cron, or `30m` / `2h` / `1d` |
| `prompt` **or** `command` | exactly one: a prompt opens a fresh autonomous conversation and runs a turn; a command runs through `shell_run` in the workspace and records only that step |
| `enabled` | default `true`. An enabled schedule can be paused and resumed from the jobs tab (`PATCH /api/jobs/{agent}/{id}/state`); that switch is stored in the `job_state` table and survives a restart. A schedule disabled here can only be turned on by editing the yaml |
| `skills` | list of skill names attached in full to the conversation a prompt job opens; default empty, and a name that no skill provides is logged as a warning at startup. A hyphenated skill name written in the `prompt` is attached too |

### One script per job

A prompt job that gathers data from several places should call **one** script that returns
one JSON blob, not drive each command from the model. A job doing its own orchestration
spends most of its step budget on shell syntax and can hit `max_steps` before it writes a
word of the answer; a script spends one step. Keep the script outside the repo when it
carries account ids or paths. `docs/examples/job-data-script.sh` is the shape: every
command guarded so one failure records an error and the rest of the data still arrives.

A `memory_consolidate` cron becomes a job of the same shape, `<agent id>/memory-consolidate`,
with no prompt or command of its own.

After a prompt job the scheduler calls `Runtime.deliver`, which pushes the last reply to
the master's Telegram chat when there is one, under the agent's name (a morning brief lands
in Telegram; see [channels.md](channels.md)). Delivery failure is logged, never retried.

## Example

```yaml
name: HLV sức khoẻ
description: Đọc dữ liệu Garmin, gửi bản tin sáng
routes: [openrouter:z-ai/glm-5.3-flash, openrouter:z-ai/glm-5]
workspace: ~/workspace/my-health-coach
skills_dirs: [~/workspace/shared-skills]
autonomous: true
cost_cap_usd: 0.3
telegram:
  token_env: TELEGRAM_BOT_TOKEN
  chat_id: 123456789
schedules:
  - id: morning-brief
    name: Bản tin sáng
    cron: "0 7 * * *"
    prompt: |
      Chạy scripts/health-sync.py --json rồi viết bản tin 4-6 dòng.
      Kèm ảnh bằng dòng `MEDIA: data/charts/sleep.png`.
  - id: backup
    cron: "20 2 * * *"
    command: ./scripts/backup-to-drive.sh
memory_consolidate: "30 3 * * 1"
```

## Compared with openclaw

openclaw keeps agents in one JSON config with per-agent overrides; here each agent is a
folder, so copying an agent is copying a directory. openclaw's workspace files
(`AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md`, `MEMORY.md`, `memory/`) have the same
names and roles, which is deliberate: an openclaw workspace can be dropped into
`agents/<id>/` and used as is. Not carried over: per-agent model parameters beyond the
route list, sandboxing modes, and multi-user identity. Tests: `test_agent_profiles.py`,
`test_agent_context.py`, `test_skills.py`, `test_config.py` (map in [testing.md](testing.md)).
