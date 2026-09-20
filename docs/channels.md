# Channels

A channel lets an agent talk somewhere other than the web UI. Today that is Telegram
(`channels/`). Turns that come from a channel run through the same loop and the same
activity tracking as the web UI, with source `telegram`, so the rail and the conversation
list show them.

## Configuration

```yaml
telegram:
  token_env: HEALTH_COACH_TELEGRAM_BOT_TOKEN   # NAME of the env var holding the bot token
  chat_id: 123456789                           # the only chat the bot answers
```

Both keys are required; `chat_id` is an int. The token itself lives in the server's
environment (for launchd, a file sourced by the run script). When the env var is unset the
server logs `agent <id>: env var <NAME> is not set; telegram channel disabled` and starts
without that channel. Updates from any other chat are ignored and logged.

## One bot, several agents

Telegram allows exactly one poller per bot token, so agents whose profiles name the same
`token_env` are grouped into **one** `TelegramChannel` at startup (`build_channels`).
They must also name the same `chat_id`; otherwise startup fails with
`agents [...] share the bot <NAME> but not its chat_id`. The log shows
`telegram channel enabled for health-coach, pong`.

On a shared bot:

- **`@<agent id>` at the start of a message** picks the agent for that message and the
  ones after it. `@pong` alone only switches and answers `Đang nói chuyện với Pong (@pong).`
  without a model call. `@nobody` lists the agents. The id is matched case-insensitively.
- **The pick is remembered per chat** in the `channel_state` table, so a restart keeps it
  and a scheduled brief from another agent never switches the agent behind the user's
  back. Before any pick, the first configured agent answers.
- **Every agent reply is prefixed** with `[Agent name]` on its own line, including
  delivered briefs, so the chat always says who is talking.
- **`/agents`** lists the agents with `▶` on the current one; `/help` includes that list.
  Both are answered by the bot itself, without a prefix. The other commands apply to the
  mentioned or current agent: `@coach /new` opens a new conversation for the coach.
- Each agent keeps **its own per-day conversation** on the chat, so histories do not mix.

With a single agent on the bot none of this applies: no mention parsing, no prefix.

## Conversations

Each text message becomes a turn of the agent's conversation for today on the channel
`telegram:<chat_id>` (title `Telegram · YYYY-MM-DD`, opened on first use each day, or with
`/new`). While the turn runs the chat shows "typing…" (`sendChatAction` every 4 s). The
reply is every assistant text of the turn joined in order, including text written next to
a tool call, plus halt, error and approval notices. Replies go out as plain text in
4 096-char chunks; a `MEDIA:<path>` line becomes `sendPhoto` from the agent workspace.

## Commands

Answered by the channel without a model call, and registered with `setMyCommands` once per
process so the client shows them.

| Command | Effect |
|---|---|
| `/new`, `/reset`, `/start` | open another conversation for the agent |
| `/help` | the command list (and the agent list on a shared bot) |
| `/agents` | the agents on this bot, current one marked |
| `/status` | turns, spend vs cap, routes, pending approval, last run |
| `/tools` | the agent's tool names |
| `/approve`, `/deny` | resolve the pending approval and stream the rest of the turn back |

`/status@botname` works; `/usr/bin` or a sentence starting with `/` is not a command and
goes to the model. A message while a tool waits for approval gets a reminder instead of a
turn.

## Scheduled delivery

After every prompt job the scheduler calls `Runtime.deliver(agent_id, conv_id)`, which
forwards the assistant text of that conversation's last turn to the agent's channel when
it has one. On a shared bot the delivery carries the agent's prefix and does not change the
current agent. A failed delivery is logged, not retried.

## Offsets and restarts

The `getUpdates` offset is written to disk before each update is handled, so a message
that crashes the handler is not replayed forever:

| Bot | Offset file |
|---|---|
| one agent | `agents/<id>/telegram.offset` |
| shared | `MY_AGENT_HOME/channels/telegram-<token_env lower-cased>.offset`, seeded once from the highest member offset so joining an existing bot replays nothing |

A `409` from Telegram means another process still polls the bot (an old server, another
tool); the channel logs `another poller holds this bot` and retries every 5 s.

## Secrets

The token never reaches logs: API errors are redacted to `<token>` before they are raised,
and a logging filter scrubs it from `httpx` request lines. Profiles hold env-var names
only, the settings drawer shows key presence only, and `agents/` is personal data outside
this repo.

## Adding a channel

A channel is a class with `start()`, `stop()` and `deliver(conv_id) -> bool`, built in
`channels/build_channels` from a profile block and mapped from each agent id it serves
(`Runtime.unique_channels` dedupes for start/stop). Keep secrets as env-var names in the
profile and add rows to [testing.md](testing.md). Tests: `test_channels_telegram.py`,
`test_channels_telegram_shared.py`, `test_app_wiring.py`.

## Compared with openclaw

openclaw's gateway supports many channels (Telegram, Discord, WhatsApp, …) with
per-channel routing rules, group handling and mention gating. Here there is one channel
type, one chat per bot and one user; the `@id` switch is the whole routing surface. That is
enough for the case at hand (one person, a few agents, one phone) and keeps the code under
four short modules.
