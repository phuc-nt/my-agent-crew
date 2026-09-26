---
layout: default
title: Changelog
---

# Changelog

All notable changes to my-agent-crew. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [SemVer](https://semver.org/). One version number for both backend and web: within a
single release, `pyproject.toml` and `web/package.json` always carry the same number.

## [Unreleased]

### Added

- **The web UI installs as an app.** The page links a web manifest, an SVG favicon and PNG icons
  (192, 512, a maskable 512 and an apple-touch icon), all drawn from the one brand mark by
  `npm run icons`. The browser chrome takes the page's own background in light and in dark.
- **The README opens with a picture of the interface**, a desktop conversation beside a phone in
  dark mode (`docs/images/web-ui.png`).

### Changed

- **The web UI is redesigned end to end, keeping its blue and its layout.** One scale of type,
  spacing, radius and shadow tokens replaces ad-hoc values; Inter is bundled (no CDN) with its
  Vietnamese subset; one set of line icons replaces emoji, which drew differently on every
  platform. A brand mark heads the sidebar, and each agent has an initial on a tile of its own
  stable hue in the conversation header, the welcome screen, the thread, delegate cards, the crew
  and jobs lists and the agent editor. Dark mode follows the operating system on every surface.
  Text on the primary button, filled badges, channel tags and sunken surfaces holds 4.5:1 in both
  modes, which is why the button and badges keep the brand blue as their fill in dark mode too;
  checkboxes, switches and fields keep a visible focus ring. A browser test measures both. Fields
  stay at 16px so an iPhone never zooms into one.
- **On a phone the conversation takes the whole screen.** The conversation list slides in over it
  from a menu button and closes on Escape, on a tap outside or once a conversation is picked,
  handing focus back to the button. While open it is modal: the chat under it is inert, and
  Escape closes the list without also collapsing the activity strip beneath. ⌘K opens it at the
  search box, and the menu button's name says how many runs are waiting, as its dot does. The
  manage screen's sections become a row of pills that brings the current one into view.
- **Empty and quiet states say where the person is.** Empty activity, approvals, costs and jobs
  sections show their own icon; the "Cần bạn xử lý" card stays grey until something waits; an
  expired approval is grey rather than amber, which is kept for a refusal and for a request still
  waiting.
- **The agent editor keeps Save within reach.** Its bar, with the agent's avatar, the unsaved count
  and the save controls, stays pinned while the sections scroll, and wraps to a second line on a
  phone. The tools matrix is a card with two-line descriptions and a coloured legend.
- **A section that fails to render no longer takes the manage screen with it.** Each page has its
  own error boundary, so the navigation stays and moving to another page leaves the failure
  behind; the failure itself is a card with the error and a reload button. The chat screen has a
  boundary too, so a crash outside its thread and activity column shows that card instead of a
  blank page.
- **The composer names the agent it writes to** and lets an input method commit a word with Enter
  instead of sending half of it, including the Enter that Safari delivers just after the
  composition has ended.

### Fixed

- **A route that fails over no longer leaves a model step open on a run that recovered.** The
  step the request opened stayed ahead of the fallback, so a finished run showed a model that
  never answered. The failed attempt's wait is now the fallback's duration, the model step times
  the next route, and when every route fails no model step is left waiting. A run stored before
  this names such a step "Mô hình" rather than "Đang suy nghĩ". The live page keeps the same
  order, and counts an answer a snapshot caught mid-call by the whole of its text.
- **The activity panel no longer crashes on a run that just started.** The "run started" payload
  shared the run's live step list, so by the time a watcher serialised it the model call that opened
  next was already in it: half-built, with an internal clock field and no cost. The page then added a
  second model step when the answer landed, and drawing the first one failed on its missing cost. A
  run is now sent as a copy without the builder's private keys. The page also completes a model call
  that a snapshot caught mid-answer rather than duplicating it, shows it as "Đang suy nghĩ" until the
  answer lands, and, like the server, adds no model step for a child's answer that was relayed whole.
- **Opening a run whose tool result arrived without its call no longer breaks the page.** A turn
  that resumes after an approval receives the result while the call was recorded on the run that
  paused, so the server opens that step with no arguments. Expanding such a run, on the activity
  list or its own page, read the missing arguments and took the screen down; the step now shows "—"
  where the arguments would be.
- **A run stopped for approval says so in its progress header.** The model step before the pause
  had answered, so the header fell through to "Đang suy nghĩ" and kept its shimmer while nothing
  was running; it now reads "Đang chờ bạn duyệt", as a run waiting on a child's approval already did.
  Its card no longer wears the "Đang chạy" pill beside its own "chờ duyệt" either.

## [0.7.0] — 2026-09-26

This release is about the time between a question and its answer. Model calls are timed from the
request and the prompt cache hit is visible per message and per day; the stable part of the system
prompt stays stable so that cache holds; a delegated answer reaches the person in the child's own
words without a model call to retell it, and a child is told to conclude before it runs out of
steps. A benchmark script measures candidate models on the real agent loop, on an isolated server.

### Added

- **Model calls are timed from the request, and the cache hit is visible.** A run's model step opens
  when the request leaves and records `first_token_ms` when the first chunk of any kind arrives, so a
  tool-only answer no longer shows as 0 ms. Each assistant message keeps the prompt tokens the provider
  served from its cache (`cached_tokens`, a new column), and `/api/stats` sums them per day and per model.
- **Pin the upstream behind OpenRouter.** `openrouter_providers` (or `MY_AGENT_OPENROUTER_PROVIDERS`)
  names the providers to try in order and `openrouter_provider_fallbacks: false` forbids any other, so a
  prompt cache built on one upstream is not lost to a silent switch.

- **`scripts/llm_bench.py`** benchmarks candidate models on the agent loop itself: each model gets a
  throwaway home, its own server and port, no Telegram token and no live routes; five tasks (a bare
  reply, write-then-read, a shell command, a delegation, a document summary) are scored and timed.
- **A delegated answer is handed on whole.** When a turn was one `delegate` call and nothing else and
  the child finished, the child's answer becomes the reply, with its charts and files, instead of
  costing one more model call to retell it. The relayed message carries no provider or model and adds
  no model step to the run. The delegator can keep the last word with `relay: false` on the call; a
  child that stopped short, answered nothing or reported `BLOCKED` still goes back through the
  delegator, as do turns with more than one tool call.
- **A delegated child is told to conclude before it runs out of steps.** From its 25th model call
  (or one before its own `max_steps`, whichever is lower) the child gets a wrap-up note and no tools,
  so what comes back is an answer rather than a halted fragment. The note is stored in the child's
  conversation. A turn the person started keeps its tools to the hard cap as before.
- **The frame asks for independent tool calls in one turn.** Two reads or two lookups that do not
  depend on each other cost one model round-trip when the model batches them; the system prompt now
  says so, in Vietnamese and English.

### Changed

- **The prompt prefix stays the same between turns.** Everything that changes from one turn to the
  next — the previous conversation's summary, the daily notes and the date — now closes the system
  prompt instead of sitting among the persona and memory sections, so a provider's prompt cache keeps
  the stable part. A delegated child is not told about its master's previous conversation, and stale
  tool outputs are stubbed a block of ten at a time rather than one per step, so the set of stubs
  changes once per block instead of on every step. A new web chat looks past delegated children when
  it picks the conversation to recap.
- **`fetch_url` gives up sooner.** The connection gets 5 seconds and each read 10, and the body is read
  only up to 512 KB before the socket closes, instead of one 20-second budget and a whole download.

- **Everything but the model call got faster.** SQLite runs in WAL mode with `synchronous=NORMAL`, the
  hot queries have indexes, and writes read their own row back in one statement, so appending a message
  costs one commit instead of five statements and an fsync. The activity hub no longer writes the run and
  wakes every watcher on each streamed token; runs are stored and broadcast at step boundaries, and a
  watcher that stops reading is cut off instead of growing without bound. Wiki pages are parsed once per
  change on disk rather than once per system prompt, `/api/stats` is recomputed only after a write, and
  the PDF libraries load on first use instead of at start-up. The web bundle is split into React, vendor
  and app chunks with content hashes, served gzipped with an immutable cache header, so a release that
  only touches app code leaves the other two cached.

### Upgrade notes

- **`messages` gains a `cached_tokens` column**, added automatically at start-up like every schema
  change so far. Back the database up before the restart that applies it, as usual.
- **A single delegation now answers in the child's words.** A master persona that told the model to
  "summarise what the specialist said" no longer gets that call; write the child's persona so its
  last answer reads well for the person (the delegated-turn frame already says so), and use
  `relay: false` on the call where the master must keep working after the child returns.
- **A delegated child stops taking tools at its 25th model call** (or one before its own `max_steps`).
  A child that legitimately needs more should get a higher cap only if its `max_steps` is above 26,
  since the soft cap is the lower of the two.

## [0.6.0] — 2026-09-25

This release lets an agent work unattended inside someone's repository without being able to change it, makes
the master hand work to the crew the way one would to a person — the question as asked, no invented paths, no
borrowed permissions, and the result (charts included) carried back whole — and moves connection keys and the
model route into the web UI.

### Added

- **Per-agent reasoning effort.** `reasoning: minimal | low | medium | high` in an agent profile goes to
  every route the agent may fall back to and reaches OpenRouter as `reasoning.effort`. While the model thinks,
  the web status says so, the run's model step counts the silent part, and messages keep the reasoning token
  count without the thoughts themselves.
- **Manage connections from the web.** Manage → Connections sets, replaces, tests and removes API keys, host
  addresses and the Telegram bot token; written to `<home>/env` and applied immediately, no restart.
  A change that would leave the crew unable to run is rejected before it is written.
- **Edit the shared model route on the Connections page**, saved to `config.yaml` with comments
  preserved. Read-only while `MY_AGENT_ROUTES` is set, because the variable wins over the file. `fake` is not
  added to a crew that does not already use it; a new row defaults to the first real provider.
- **Test Tavily and Brave keys.** Tavily asks `/usage` (free, and reports the number of calls used);
  Brave runs one search for 1 result, and the button says plainly that it costs one call. Quota exhausted (429) is
  reported differently from a wrong key.
- **`write_paths` in an agent profile** confines `workspace_write` and `workspace_edit` to the listed
  paths inside the workspace. A write elsewhere is refused with an error naming the allowed paths, and no
  directory is created. Meant for autonomous agents whose workspace is a git repo.
- **`shell_deny_patterns` in an agent profile**: commands containing one of the listed fragments (case-insensitive
  substring, like `shell_ask_patterns`) are refused outright, with no approval asked, since nobody may be there to
  grant one in a delegated or scheduled turn. Meant for keeping an agent that works in someone's repo away from
  DDL, raw SQL writes and inline interpreters (`create table`, `python3 -c`). A soft guard like the ask list.

### Changed

- **Domain records go to the agent that keeps them.** The master's crew roster says a fact the person
  reports in a crew agent's domain (a meal, a drink, an illness, a payment, a document), or asks to be saved,
  is handed to that agent to record, and a question about its cause is handed back with the new fact rather
  than answered by guesswork. `memory_save` and `user_memory_save` say they are not a substitute for that
  agent's records.
- **Delegation hands over intent, not method.** The `delegate` tool and the master's crew roster ask for the
  person's words and today's date, never an invented file, folder or table; the roster no longer lists each
  agent's workspace. A delegated turn's system prompt says the task was written by the coordinating agent
  and that the agent's own conventions win, so a path named in the task is not a file to create.
- **A delegated task grants no permissions.** The tool description, the roster and the delegated turn's prompt
  all say a question is asked and answered, not acted on, and that a new table, a schema change, code or
  config needs the person's explicit consent — a permission the task grants itself is not theirs. The
  always-on `delegation` skill now teaches the same contract; its per-file split applies only to coding work.
- **`shell_write_paths` confines an agent with the network on, too.** Set, every `shell_run` command runs under
  `sandbox-exec` writing only there and in temp, and without `open`/`launchctl`/`osascript`, so an agent can fetch
  and record data but cannot edit the code, scripts or config around it. `shell_network: false` still adds the
  network denial; without either key nothing changes.
- **Refusals tell the agent to report back.** A sandbox-denied write, a denied command and a `write_paths`
  refusal all say the change needs the person's consent: stop, say what is needed and why, and end a delegated
  turn with `Status: BLOCKED`. The master's roster and the `delegation` skill say a consent block goes to the
  person — never done by the master itself or handed to another agent.
- **An unfinished delegate reports what it already did.** When the child halts, errors or is interrupted,
  the result says so and lists its successful tool calls, so the delegator does not redo or escalate work
  that already landed.
- **A task is sized to the question asked.** The `delegate` tool, the roster and the `delegation` skill say to
  pass only what the person asked, and to pass a record-this request as just that; a master that put its
  remembered conclusions into the task turned a one-line question into a re-audit several times as expensive.
- **The Telegram bot reports when a message was cut off** because the bot restarted for more than 30 seconds, so the
  person resends instead of waiting for an answer that never arrives.
- **The host guard's 403 names the host** and the `MY_AGENT_ALLOWED_HOSTS` variable that needs it added; the log records
  it once per name (a wrong Origin is not logged). The docs state plainly that the server has no login — do not expose it through a public tunnel.
- **Refusing to remove the last key** names the route in `provider:model` form and how to detach it.

### Fixed

- **Charts a delegated agent attaches reach the person.** A child's `MEDIA:`/`FILE:` lines named paths in the
  child's workspace and the parent's retelling dropped them, so a coach's charts never arrived. The delegate
  tool now copies each attachment into the parent's workspace under `delegated/<child>/` and rewrites the line;
  a file that cannot be carried over becomes a sentence, and any relayed line the retelling left out is appended
  to the final reply.
- **Scheduled jobs are quieter and report correctly.** A check job told to answer OK when nothing is due no
  longer pushes that OK to the chat (the run still shows in the UI); each job's last run is looked up by its
  own source instead of inside the two hundred newest runs; a scheduled memory consolidation records its run
  under the job; and Telegram messages drop table dividers and join table cells on one line per row, so a
  table the model writes stays readable as plain text.
- **Conversation recaps carry absolute dates.** A recap written at night said "tối nay" and was read the next
  morning as the new day. Transcript lines now start with the day and time in the person's zone, the recap
  prompt asks for concrete dates, and the next conversation's section title says when the previous one ended.

### Upgrade notes

- **An agent with `shell_write_paths` and the network on is now sandboxed.** Before, the key was ignored unless
  `shell_network: false`; check that such an agent's commands only write where the list says.
- **Refresh `<home>/skills/delegation.md`.** Installing a template does not overwrite shared skills, so an
  existing home keeps the old file-list version; copy `my_agent_crew/agents/templates/_shared_skills/delegation.md`
  over it.
- **Set `ExitTimeOut` in the launchd plist** (the template in `docs/deployment-guide.md` uses 45).
  The bot waits 30 s for the running turn before reporting "message cut off", but launchd's default is only 20 s,
  so without this key a `kickstart -k` in the middle of a long turn will SIGKILL before it can report.

## [0.5.0] — 2026-09-23

This release gives agents more ways to work with people — ask back, say what they are doing, send files — adds
wiki-style memory, and a real guard at the operating-system layer for agents holding data that must not
leave the machine.

### Added

- **Memory wiki: one page store per agent** at `memory/wiki/`, split into three directories `entities`,
  `concepts`, `syntheses`. Daily notes are written by date — right at the time of writing, wrong at the time of
  asking: "when is the Eco deadline" is scattered across eleven notes. A page gathers those fragments
  under the name of the thing itself, so the question has one place to be answered. The compile prompt spells
  out how the three directories differ — has a proper name, a recurring concept, or a conclusion that spans
  many things — because merely listing their names in the JSON template makes the model dump everything into `entities`.
- **Every page must declare its sources.** `sources` records `note:YYYY-MM-DD` or `conv:<id>`;
  `wiki_apply` rejects a page without sources. This is not input validation but the whole point of
  the store: a page that cannot say where it came from is a made-up page, and letting one such page
  through makes every remaining page less trustworthy.
- **Only part of the file belongs to the machine.** The link block between two markers is rewritten after each
  compile; the rest belongs to whoever — person or model — wrote it and is returned
  intact. Without that boundary the store either freezes or cannot be trusted.
- **`[[Page name]]` links** build a bidirectional graph, rewritten after each compile
  or each page edit via the web — editing one link changes what *other pages* say about
  where they are pointed to from.
- **Compile from notes** runs right after `memory_consolidate`, with no separate cron, because
  both read the same set of notes. The result is a **proposal** carrying the whole batch of pages together with the
  old content for one-step undo; `autonomous` agents apply it themselves. A broken compile does not break the memory
  cleanup turn that already finished before it.
- **Lint and two tracking tables.** A store degrades quietly: a page loses its last source, a
  link points to a page nobody has written, a page stops being updated. Lint reads the whole store in one
  pass and reports four kinds: `unsourced`, `dangling`, `review`, `stale` (over 90 days, or no
  updated date — treating missing evidence as fresh is how a store starts lying).
  Nothing is deleted: a dangling link is usually a page that *should* exist, i.e. work for the next
  compile. The two files `wiki/reports/open-questions.md` and `stale.md` are rewritten in full
  each time, because a table that accumulates keeps reporting errors fixed months ago.
- **Three tools for agents**: `wiki_get`, `wiki_search`, `wiki_apply`.
- **Wiki tab in the manage screen** and the endpoints
  `GET/PUT/DELETE /api/agents/{id}/memory/wiki…`: browse the store by group, search, open a page, edit,
  delete, view the lint report, and run a compile right away without waiting for the nightly job.
- **`web_search` runs on every machine** — added a DuckDuckGo source that needs no key, last in the
  list so there is always at least one source. Order of attempts: firecrawl → Brave → Tavily → DuckDuckGo;
  a broken source is skipped and logged, and only when all of them fail does the tool report that the service
  could not be reached. Previously the whole crew lacked this tool because no machine had a search key set.
- **`fetch_url` reads pages as markdown via firecrawl** — keeps headings, lists and tables instead of
  raw text, limit raised from 6,000 to 20,000 characters. If firecrawl fails it falls back to raw text.
- **Two new environment variables** `FIRECRAWL_BASE_URL` and `FIRECRAWL_API_KEY`. The key is only sent when
  set, so a self-hosted host needs no key and a mistyped base url does not carry the key anywhere.
- **The Connections page shows the search source order** and the firecrawl host in use, enough to tell
  "not enabled" from "misconfigured".
- **A skill can declare the commands it needs** — `requires.bins: [gws]` and `cliHelp: "gws --help"`
  in the front matter. On a machine missing the command, the skill stays in the list with the label
  "missing: gws", and the skill body opens with a warning line — the agent knows why it cannot do the
  job instead of failing midway. The Settings tab shows the same label.
- **One rule in the system prompt**: for a command whose syntax is uncertain, run `--help` once,
  and do not try more than two new syntaxes for the same job. Added because one scheduled run burned 16
  steps guessing the parameters of a program it had never seen.
- **Scheduled jobs auto-attach skills the prompt names** — hyphenated names only (`gws-shared`),
  because a one-word name like `ledger` shows up in prompts that have nothing to do with it.
- **Data-gathering script template for jobs** at `docs/examples/job-data-script.sh`: one command returns one
  JSON block, and each failing source records its own error instead of breaking the whole run.
- **Overlong tool results are condensed intelligently instead of truncated.** JSON is reduced by
  structure: every top-level key stays, arrays lose their tail, long strings lose their middle, and the returned
  string still parses. Numbers, booleans and null are never rewritten — ledger figures and
  health data travel this path. Plain text keeps the first 40% and last 20% verbatim, the
  middle is summarised by the agent's own route, with a label saying plainly which part is a summary. A summary that fails,
  is slow or comes back empty falls back to plain truncation; the tool always answers.
- **Provider `ollama`** (OpenAI-compatible, `OLLAMA_BASE_URL`, default
  `http://127.0.0.1:11434/v1`). Needs no key so it is always built; on a machine not running ollama the
  route falls through to the next one. The Connections page shows the address being probed, enough to tell "not running"
  from "wrong host".
- **The run card says plainly that the model read a condensed version** — the label records the condensing kind and the original length, so
  a short answer built on a pruned source is not misread as the full picture.
- **`ask_user` tool: the agent asks back instead of guessing.** At a point it cannot know on its own — which deadline,
  which account, whether to continue — the agent stops the turn and asks one question, with a list of options
  if there are any. It differs from a tool approval in three ways, so do not read it as an approval: an agent with
  `autonomous: true` still stops, because the question exists precisely so it does not decide alone; the question closes through
  its own path, and `/approve` and `/deny` are rejected on it; and a timeout is not a
  refusal — the agent receives the `default` value and moves on, silence is read as "go with the default".
  Each conversation has at most one open question. Answer on the web with the question card, or on Telegram
  with the very next message — type a number to pick, type text and it is taken verbatim.
- **The run timeline has its own waiting state.** A stop for a question used to show
  as nothing at all, reading like an agent thinking for hours. Now it is a separate step carrying the
  question text, the card title reads "Waiting for your answer" and the running animation is off — the job only
  moves when someone types, so it promises no other progress.
- **`pdf_read` tool.** Text pages are read straight to text; scanned pages go through the vision route
  like images, one call per page, so reading a long scan is expensive. Default 50 pages, `pages`
  picks a range (`'1-5'`, `'3'`). A machine without a vision route still builds the tool: text pages read
  normally, scanned pages report as unreadable instead of breaking the whole turn.
- **`shell_allow_patterns`: a supervised agent can still run everyday work on its own.**
  `shell_ask_patterns` pulls a command toward asking even when `autonomous`; the new list does the
  opposite, letting familiar commands run straight through even when *not* `autonomous` — so
  a careful agent can still run its own tests or `git status` without stopping at every
  command. The order is fixed: questions always ask, then the ask list, then the allow list, then
  autonomy; declaring a command in both means ask. Settable in `config.yaml`, in each agent's `agent.yaml`,
  or via `MY_AGENT_SHELL_ALLOW_PATTERNS` (semicolon-separated). Patterns under
  two characters, and patterns that merely *look* like wildcards (`*`, `.*`, `.`, `-`, `--`, `/`,
  `&&`, `||`, `;`, `|`) are dropped: matching is substring matching, so `.*` matches only the literal `.*`
  while the author reads it as "allow everything" — that very misreading is what is
  dangerous. A broken pattern is dropped on its own rather than breaking the whole list, and dropping is the safe
  direction because the command then falls back to asking.
- **`progress_note` tool: see what the agent is doing while it is still doing it.** Before a
  long stretch of work, the agent says one short sentence and it appears immediately on the timeline, so the
  viewer reads "reading the calendar" instead of watching a spinner and guessing. It never stops
  anything: no approval, no touching the ask list — a note that needs approval would arrive after the very work
  it announces. The step written out has its own kind `note` rather than `tool`, because a note has no
  duration and cannot fail; drawing it as a tool call would leave a line forever
  unfinished. Over 200 characters it is cut rather than erroring mid-turn. This is not
  memory: the note lives with the run and dies with it.
- **The `FILE:` line sends the real file instead of a path.** Telegram recompresses images, which is right for
  a chart and ruinous for a CSV — so `MEDIA:` remains `sendPhoto`, while `FILE:` goes through
  `sendDocument`, preserving bytes and file name; the web shows a download link instead of an embedded
  image. Limit 20 MB and seven formats (`pdf`, `csv`, `md`, `txt`, `xlsx`, `json`, `zip`).
  This list guards the answer, not the workspace: the agent can write whatever it likes into its own
  directory, so restricting to the workspace alone still leaves one sentence enough to send out a key
  file or a `.env` that an earlier step copied in. A path outside the workspace, a file that does not
  exist, a wrong format or an oversized file are all reported into the chat rather than thrown — the text part has
  already gone out, so an exception only leaves a promise of a file with no word on why the file never arrived.
- **Runnable skill examples in `docs/examples/skills/`**, with tests keeping them real. When a
  skill wraps a command-line program, two fields decide whether it lives or dies:
  `requires.bins` so a missing program gets labelled instead of breaking mid-turn, and
  `cliHelp` so the model reads the real syntax instead of guessing flag names. The test requires both for every
  bundle with a `scripts/` directory, and scans every file for email addresses and long id strings — an example
  that carries a real id off its author's machine is worse than no example at all.
- **A second skill example, `goodreads`**, for a service that no longer has an API. Reads via the public RSS,
  writes via its own browser session. Two things worth copying elsewhere: the account id lives
  in `scripts/goodreads.json` next to the script rather than as a parameter, so the read command has
  nowhere for the model to fill in wrongly; and an **empty response is treated as an error**, because Goodreads blocks
  scraping by returning 202 with an empty body instead of an error — the client throws nothing, and the
  all-`null` record produced from that reads exactly like a real answer. That is the dangerous kind of failure.
  Write commands: `rate`, `shelf`, `progress`, `review`. The buttons on the book page only appear after
  JavaScript has finished running, so the writer waits for them instead of looking as soon as the HTML arrives.

- **`shell_network: false`: cut an agent's shell commands off from the network at the operating-system layer.** Every
  `shell_run` of that agent runs inside macOS `sandbox-exec`: no outbound connections, including
  `127.0.0.1` and DNS, no listening ports; `open`, `launchctl`, `osascript`, `shortcuts`,
  `pbcopy` are blocked because they ask a process outside the sandbox to do the work. File writes are only allowed under
  `shell_write_paths` and the temp directory — a line inserted into a script that a networked job will run is
  a scheduled command, so blocking the network while leaving writes free blocks nothing. Unlike pattern
  lists, this guard holds for both `$(…)` and a script the model just wrote itself. On a machine without
  `sandbox-exec` the command is refused rather than run bare. Meant for agents holding private data
  such as a financial ledger; it only restricts *commands*, while the agent's answer still goes to the provider and
  to the recipient.

### Changed

- **Nine coding templates merged into three**: `fullstack-developer` does a whole software job
  (survey, plan, write, test, self-review, commit following the shared skills), `kongming` is a read-only
  advisor for hard decisions — no write tools, no `delegate`, its own cost ceiling — and
  `researcher` looks up any topic, has `pdf_read` and a ≥ 3 sources checklist. Removed `dev`, `scout`,
  `planner`, `coder`, `reviewer`, `tester`, `debugger`, `git`: every delegation is an empty context
  that knows only the brief, and for a personal crew that is not code-focused, the lost context costs
  more than the parallelism gains. Agents already installed from the old templates keep running unchanged; only `agent add` changes.
- `web_search` is no longer in the optional tool group: it is always built, so an agent declaring
  `web_search` in `tools:` no longer silently loses the tool.
- **`docs/tools.md` spells out the consequence of `shell_run` filtering environment variables**: a script that runs
  in your terminal can still break when the job runs, because every variable outside the allowlist
  disappears. A script that needs a non-secret value should read it from a file, not rely on environment
  variables — widening the allowlist hands the API keys to every command the model writes. The filtering behaviour
  is unchanged; it is now pinned by a test.

- **Activity details become a right-hand column of the chat pane on wide screens.** From 1101px, the runs
  of the open conversation live in an always-open 380px column, which keeps its space even when there are no
  runs yet so the chat pane does not jump when work starts. Narrower screens keep the one-line strip below
  the message stream as before.

### Fixed

- **Truncated tool results no longer exceed the `tool_output_chars` ceiling.** The "truncated" label line
  used to be appended after the ceiling was already spent, so the returned version was always a few
  dozen characters over the ceiling. Now the label is paid for out of that same budget. The old test measured with a `+ 40` margin so
  it did not see it; there is now a test sweeping several ceilings and several data shapes to pin this invariant.
- **The `researcher` template respects the search ceiling the asker sets** ("at most 2 searches") and
  requires a **Sources** section with URLs. Before this, a report could cite no source at all even though the persona
  said to record them.
- **The `fullstack-developer` template reports point by point whether it followed `kongming`'s advice**, with
  reasons. Before this, it could say "followed the advice" while the code did the opposite.
- **The Goodreads writer waits for the page to render the buttons** before clicking, and uses the right shelf labels; the first
  real write failed at both spots.

### Upgrade notes

No manual migration needed. The `approvals` table gains three columns (`kind`, `options`, `answer`), added
automatically on startup with default values for old rows. All new keys in
`agent.yaml` (`shell_network`, `shell_write_paths`, `shell_allow_patterns`) are optional and default
to the old behaviour. Agents already installed from the nine old coding templates keep running; only
`agent add` switches to the three new templates.

## [0.4.0] — 2026-09-22

This release rebuilds the web UI around one idea: **see what the agent is doing**, and manage the whole crew
right on the web instead of editing YAML by hand.

### Added

- **Replies render as markdown** — headings, lists, tables, syntax-highlighted code blocks, replacing a
  block of raw text. Links open in a new tab; raw HTML is not rendered.
- **Conversation titles set automatically** from the user's first message, running in the background after the turn
  ends so it does not slow the answer. Manual renaming still works and always wins over the automatic title.
- **Run progress right inside the chat pane**: calling the model or running a tool, which step, how much
  spent so far — visible while waiting, no need to open another tab.
- **Manage area separated from chat**, navigated by hash route `#/manage/<section>` with nine tabs:
  Activity, Approvals, Crew, Tools, Schedule, Memory, Costs, Connections, Settings. Reloading the page
  stays on the same tab.
- **Open a single run** with `#/manage/activity/<run_id>` — shareable, survives reload,
  and also opens old runs the activity list no longer keeps.
- **Manage agents on the web**: add, edit, delete agents (master and child agents alike), edit the persona files
  (`AGENTS.md`, `SOUL.md`), view the assembled system prompt to know what the model actually reads.
- **Tool matrix** — which tools the whole crew uses, which agent uses what, in one table.
- **Connections page** — API keys, Telegram, vision route, see what is configured and what is not.
- **Agent management HTTP API**: `POST /api/agents`, `PATCH /api/agents/{id}`, `DELETE /api/agents/{id}`,
  `PUT /api/agents/{id}/files/{name}`, `GET /api/agents/{id}/prompt`, `POST /api/agents/reload`,
  `GET /api/tools`, `GET /api/connections`.
- **`scripts/gates.sh`** — runs all nine CI gates with one command, in the exact order of `ci.yml`, stopping at
  the first red gate and naming it (~22 seconds). Alongside it, a test keeps the version number in its five
  declared places from drifting apart.

### Changed

- **The "Activity" column now belongs to the open conversation**, inside the chat pane, instead of a
  shared bar showing activity from every conversation. Crew-wide activity moves to the Activity tab of the
  manage area.
- The Crew, Schedule, Approvals, Memory, Costs tabs are reclassified by scope: what is shared
  across the crew lives in the manage area, what belongs to one conversation lives inside the chat pane.
- A tool step's `arguments` are recorded as a name → value mapping (previously the whole thing was forced into
  one string, displayed as one row per character). The reading side tolerates both shapes so runs
  recorded before this release can still be viewed.

### Fixed

- An empty reply turn is no longer treated as a finished turn — the web UI stayed silent with no report.
- A run that ends while being viewed now shows the right status and end time: the page's in-memory
  copy lacked that timestamp, so the page re-reads exactly once on the frame where the status changes.
- Six Python files brought back to proper `ruff format` formatting; the `ruff format --check` gate in CI
  now runs in every development cycle, not just `ruff check`.

### Upgrade notes

No migration needed. The SQLite schema only adds tables, all `CREATE TABLE IF NOT EXISTS`; the
`config.yaml`, `agent.yaml` files and the home directory keep their shape. Upgrading is pulling the new code and
restarting the process.

## [0.3.0] — 2026-09-21

- Claude Code-style `.agents/` kit: commands, agents, skills, hooks.
- Image reading via vision route; Telegram albums merged into one turn; the user's time zone.
- Three-file persona; Vietnamese documentation set with five animated diagrams, published to GitHub Pages.

## [0.2.0]

- Multiple agents, `delegate` for the master to hand work to other agents, Telegram channel.

## [0.1.0]

- One agent, `run_turn` loop with a tool approval gate, web UI, memory on disk.

[0.7.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.7.0
[0.6.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.6.0
[0.5.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.5.0
[0.4.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.4.0
[0.3.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.3.0
[0.2.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.2.0
[0.1.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.1.0
