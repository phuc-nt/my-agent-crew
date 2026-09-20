# Agents

An **agent** is one folder under `MY_AGENT_HOME/agents/<id>/` with an `agent.yaml` and a
few Markdown files. Every agent runs the same loop (`agent/loop.py`); the profile only
changes its inputs: persona, memory, workspace, skills, model routes, budget, schedules and
channels. Source of truth: `agents/profile.py`, `agents/channels.py`, `config.py`.

## Folder layout

```
MY_AGENT_HOME/                      ~/.my-agent-crew by default
├── config.yaml                     global, non-secret keys (see below)
├── agent.sqlite3                   conversations, messages, runs, channel state
├── workspace/                      sandbox of the default agent
├── skills/                         skills of the default agent
├── channels/                       offset files of bots shared by several agents
└── agents/
    └── <id>/
        ├── agent.yaml              the profile (fixed key set, no secrets)
        ├── AGENTS.md  SOUL.md      persona files, read every turn
        ├── IDENTITY.md  USER.md
        ├── MEMORY.md               durable memory, read every turn
        ├── memory/YYYY-MM-DD.md    daily notes, today + yesterday read every turn
        ├── workspace/              default tool sandbox (overridable)
        ├── skills/                 always on the skill path
        └── telegram.offset         poll offset of a bot this agent has to itself
```

`ensure_agent_dirs` creates the agent dir, workspace and `memory/` at startup, so a
profile plus persona files is enough. The agent id is the folder name; `default` is
reserved for the top-level settings (see below).

## `agent.yaml`

Only these keys are accepted; anything else raises `ValueError` at startup so a typo never
silently disables a setting.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `name` | string | the id | display name; also the `[Name]` prefix on a shared Telegram bot |
| `description` | string | `""` | shown in the UI agent switcher |
| `routes` | list or comma string of `provider:model` | global `routes` | tried in order; a route that fails before producing output falls through to the next |
| `workspace` | path | `workspace` | sandbox for `workspace_*` and `shell_run`; relative paths resolve against the agent dir, `~` expands |
| `persona_files` | list of file names | `AGENTS.md, SOUL.md, IDENTITY.md, USER.md` | read from the agent dir into the system prompt each turn; missing files are skipped |
| `skills_dirs` | list of paths | `[]` | extra skill folders; `<agent dir>/skills` is always first |
| `cost_cap_usd` | number ≥ 0 | global | budget per conversation, `0` = unlimited |
| `max_steps` | int ≥ 1 | global | model calls per turn before a `halted` |
| `autonomous` | bool | global `autonomous_default` | new conversations skip tool approval |
| `schedules` | list | `[]` | jobs, see [Schedules](#schedules) |
| `telegram` | map | none | `token_env` + `chat_id`, see [channels.md](channels.md) |

Every value that is not set falls back to the global settings, which come from env vars
and `config.yaml`:

| Env var | `config.yaml` key | Default |
|---|---|---|
| `MY_AGENT_HOME` | — | `~/.my-agent-crew` |
| `MY_AGENT_ROUTES` | `routes` | `openrouter:deepseek/deepseek-v4-flash` |
| `MY_AGENT_COST_CAP_USD` | `cost_cap_usd` | `0.5` |
| `MY_AGENT_MAX_STEPS` | `max_steps` | `12` |
| `MY_AGENT_AUTONOMOUS` | `autonomous_default` | off (`1`, `true`, `yes`, `on` turn it on) |
| `MY_AGENT_LANGUAGE` | `language` | `vi` (prompt frame language; `en` is the other option) |
| `OPENROUTER_API_KEY` | — | enables the OpenRouter provider |
| `BRAVE_API_KEY` / `TAVILY_API_KEY` | — | enables `web_search` |
| the name in `telegram.token_env` | — | the bot token; unset = that channel is disabled |

Env wins over `config.yaml`; `config.yaml` accepts only the five keys above. Secrets never
go into YAML: profiles carry env-var **names**, and the settings drawer shows key presence,
never values.

## The default agent

The `default` agent always exists and is the top-level settings: dir = `MY_AGENT_HOME`,
workspace = `MY_AGENT_HOME/workspace`, skills = `MY_AGENT_HOME/skills`, persona and memory
files read from `MY_AGENT_HOME` itself. A fresh home therefore needs no profile at all.
`load_profiles` returns it first, then `agents/<id>/agent.yaml` sorted by id.

## Persona files

Persona files are plain Markdown; the loop concatenates each one as a `## <file name>`
section of the system prompt, after the fixed frame (`agent/prompt.py`) and before the
skills. Conventions that have worked:

| File | Put here |
|---|---|
| `AGENTS.md` | how to work: what to do at the start of a turn, which scripts to run, how to write memory |
| `SOUL.md` | tone, values, what the agent refuses |
| `IDENTITY.md` | name, role, one-line self description |
| `USER.md` | who the user is, preferences, timezone, recurring context |

Each section is capped at 24 000 characters (`MAX_SECTION_CHARS`); longer files are cut
with a trailing `…`, so keep them short and move history into [memory](memory.md).
Persona files are personal data and live in `MY_AGENT_HOME`, never in this repo.

## Skills

A skill is a Markdown file with front matter (`name`, optional `description`, `always`),
either `name.md` or a folder `name/SKILL.md` whose siblings (scripts, references) the
model reaches by the absolute path given in a `SKILL_LOCATION` line. Skills load from the
builtin dir (`cite-sources`), then `<agent dir>/skills`, then each `skills_dirs` entry;
a later skill with the same name overrides an earlier one. `always: true` skills ride on
every prompt; the others are attached per conversation from the settings drawer.
Skills are instructions for the model, [tools](tools.md) are functions it can call.

## Schedules

Each entry in `schedules` becomes a job `<agent id>/<schedule id>` in the scheduler
(20 s tick, machine local time, no timezone field).

| Key | Meaning |
|---|---|
| `id` | default `job-<index>`; used in the job name and in `POST /api/jobs/{agent}/{id}/run` |
| `name` | default the id; shown in the UI |
| `cron` **or** `every` | exactly one: five-field cron, or `30m` / `2h` / `1d` |
| `prompt` **or** `command` | exactly one: a prompt opens a fresh autonomous conversation and runs a turn; a command runs through `shell_run` in the workspace and records only that step |
| `enabled` | default `true` |

After a prompt job the scheduler calls `Runtime.deliver`, which pushes the last reply to
the agent's channel when it has one (a morning brief lands in Telegram; see
[channels.md](channels.md)). Delivery failure is logged, never retried.

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
  token_env: HEALTH_COACH_TELEGRAM_BOT_TOKEN
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
```

## Compared with openclaw

openclaw keeps agents in one JSON config with per-agent overrides; here each agent is a
folder, so copying an agent is copying a directory. openclaw's workspace files
(`AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md`, `MEMORY.md`, `memory/`) have the same
names and roles, which is deliberate: an openclaw workspace can be dropped into
`agents/<id>/` and used as is. Not carried over: per-agent model parameters beyond the
route list, sandboxing modes, and multi-user identity. Tests: `test_agent_profiles.py`,
`test_agent_context.py`, `test_skills.py`, `test_config.py` (map in [testing.md](testing.md)).
