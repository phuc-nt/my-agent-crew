# Channels

A channel lets an agent talk somewhere other than the web UI. Today that is Telegram
(`channels/`). Turns that come from a channel run through the same loop and the same
activity tracking as the web UI, with source `telegram`, so the rail and the conversation
list show them.

## Configuration

```yaml
telegram:
  token_env: TELEGRAM_BOT_TOKEN   # NAME of the env var holding the bot token
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
  mentioned or current agent: `@coach /status` reports on the coach. `/new` is the one
  exception — a bare `/new` cuts every agent on the bot, because the chat is one window
  and a fresh start means the window, and the bot itself confirms it, unprefixed;
  `@coach /new` cuts only the coach and the coach confirms.
- Each agent keeps **its own per-day conversation** on the chat, so histories do not mix.
- **Each agent reads the last 10 lines the others exchanged in the chat today**, as a
  read-only prompt section, so asking the coach about what Pong was just told does not
  draw a blank. It is context, not history: the agent cannot reply into it and nothing is
  written back. See [memory.md](memory.md).

With a single agent on the bot none of this applies: no mention parsing, no prefix, and
nothing shared — a private bot has only one agent to read.

## Conversations

Each text message becomes a turn of the agent's conversation for today on the channel
`telegram:<chat_id>` (title `Telegram · YYYY-MM-DD`, opened on first use each day, or with
`/new`). While the turn runs the chat shows "typing…" (`sendChatAction` every 4 s). The
reply is every assistant text of the turn joined in order, including text written next to
a tool call, plus halt, error and approval notices. A turn that ends without a single word
says so with the step count instead of sending nothing: silence is indistinguishable from
a dead bot, and the same holds for a delivered brief whose run finished empty. Replies go
out as plain text in
4 096-char chunks; a `MEDIA:<path>` line becomes `sendPhoto` from the agent workspace.

A new conversation does not start blank: the summary of that agent's previous conversation
on the same channel is carried into the prompt as a **Cuộc trước** section
(`previous_for_channel`), so `/new` and the first message of a new day pick up where the
last one left off without replaying its messages.

## Commands

Answered by the channel without a model call, and registered with `setMyCommands` once per
process so the client shows them.

| Command | Effect |
|---|---|
| `/new`, `/reset`, `/start` | open another conversation — for every agent on the bot, or for one when addressed with `@id` |
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
current agent. When the last turn ended without any assistant text (a run halted at
`max_steps`, a provider error, an approval left pending) the channel sends
`texts.TELEGRAM_RUN_UNFINISHED` with the run's summary instead of staying silent, so a
scheduled job never disappears without a trace. When an approval in that turn timed out
(`approval_ttl_seconds`), the delivery first sends `texts.TELEGRAM_APPROVAL_EXPIRED` naming
the refused tool, so the reply that follows is read as one shaped by a guard, not by the
person.

A run that stopped early but *did* leave text behind is the trickier case: the half-finished
answer reads like a complete one. So after sending the text, a run whose status is `halted`
or `error` gets a second message, `texts.TELEGRAM_RUN_CUT_SHORT`, naming the reason and what
the run spent. Either way the scheduler logs one line per prompt job —
`job <id>: delivered=<bool> conv=<id> status=<status>` — so the log distinguishes a job that
answered from one that stayed quiet. A failed delivery is logged, not retried.

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
