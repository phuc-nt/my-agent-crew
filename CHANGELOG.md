---
layout: default
title: Changelog
---

# Changelog

All notable changes to my-agent-crew. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [SemVer](https://semver.org/). One version number for both backend and web: within a
single release, `pyproject.toml` and `web/package.json` always carry the same number.

## [Unreleased]

### Changed

- A turn started from the web now belongs to the server, not to the tab that sent the message.
  Closing the tab, reloading or opening another conversation no longer cuts the turn short: the
  server reads it to its end, and Stop is what ends it. A tab opened in the middle of a turn,
  whoever started it (another tab, Telegram, a job), now shows what the turn has written so far
  and follows it live through `GET /api/conversations/{id}/turn`, instead of showing nothing
  until the answer is stored. The text being written is kept in memory only; after a restart the
  stored conversation is the whole truth. `POST /api/conversations/{id}/stop` now also answers
  `cancelled`, and ends a turn the web started from any tab.
- When the server stops under a Telegram turn, the bot now says the turn will be carried on once
  the server is back, instead of saying it was cut off. A bot restarted while the server stays
  up still says the turn was cut off, since nothing will carry it on.
- The summary of the previous conversation and the daily notes of yesterday and today are no
  longer part of the system prompt. A turn reads them in a framed block in front of the message
  that opens it, stored with that message, and a later message carries only what changed since:
  the lines added to a note, the new text of one that was rewritten, or a line saying a note is
  gone. One `memory_save` used to change the text in front of the whole conversation, so the
  provider's cache of everything said so far was lost: on the owner's install the model call
  right after a `memory_save` had 15.1% of its prompt tokens billed as cached, against 85.5% for
  the others (4 of 334 calls in ten days). The system prompt now changes only with the date,
  and the history is a prefix that only grows. A turn learns of a note it saved itself from its
  own tool call; the conversation is told with the next message that opens a turn. A
  conversation begun before this reads the memory as it is now in front of its first message
  until its next message is stored. `GET /api/agents/{id}/prompt` also returns `opening` and
  `opening_chars`, what a new conversation's first message would be read after, and the agent
  editor shows it under the prompt; a run's trajectory carries each message's block as
  `turn_notes`. The messages the web is sent are unchanged.

### Added

- A message sent twice is said once. Each send from the web carries a `request_id`; when the
  answer to a send is lost on the way back and the same words are sent again, the server stores
  nothing new and starts no second turn. It answers with what became of the first send: the same
  place in line while the message waits, or the conversation as it stands and the turn under way.
  The name is stored in the same transaction as the message it names, is kept across a restart,
  and is left unused by a send the server refused or a message Stop handed back. `POST
  /api/inbound` takes no `request_id`.
- A turn cut by a server restart is carried on when the server is back, once. The run that was
  cut is reopened as the same run, with its timeline and what it had spent, and goes on from the
  stored conversation; whoever was reading that kind of turn reads the rest (the bot answers a
  Telegram chat, a job's answer is pushed as usual, a tab can watch and Stop any other). Two
  guards cannot be turned off: a run is marked `resumed` before its turn takes a step, so a turn
  that brings the server down again is closed at the next start instead of being tried for ever,
  and a turn carried on stays under the conversation's cost cap. A turn is not carried on when
  its conversation waits on a decision, was deleted, has had a later turn or has spent its
  budget, when it is a Telegram turn and no bot is up, or when the server runs with
  `--no-schedule`. Stop, a failed turn and a bot restarted under a running server close the run
  as before. The web says "Tiếp tục sau khi server khởi động lại" under the progress bar of a
  run that was carried on (`resumed` on a run in `/api/activity/runs`).
- Each tool says whether a call cut by a restart may be made again (`Tool.replay_safe`, off
  unless declared). The eighteen tools that only read declare it and are simply called again. A
  call to any other tool that may already have run is closed with a note saying it was cut and
  that nobody knows whether it ran, and the model decides after looking; nothing that writes,
  sends or pays is done twice unseen. A call that never ran (it still had to ask, was refused,
  or could not be run) is settled the way it always was.
- An agent may name an escalation route: one `provider:model` its turn moves to only when the
  turn is stuck (`escalation_route` in `agent.yaml`, or "Tuyến leo thang" under the routes in the
  agent editor). Off unless an agent's own file sets it, and never inherited. A turn moves when
  the loop guard is about to halt it for making the same call again and again, or when a model
  call failed on every one of the agent's routes before any text was shown; the rest of that
  turn runs on the escalation route and the next turn starts on the usual ones. A turn moves at
  most once: stuck there too, it halts or fails as it did before. Running out of steps or of
  budget never moves a turn. A route that is one of the agent's own, or whose provider has no
  key, is no way out: it is left unused at start with a warning in the log, and saving one from
  the editor is refused (422) with the reason. The move is a new event, `escalated`, with why it
  was made; the web says so above the message box, and the run's timeline gains an `escalation`
  step naming the route.
- Agents can use the tools of remote MCP servers. A server is declared once under `mcp_servers` in
  `config.yaml` (its address, a description, headers, how far its tools are let in, which of them
  only read, a timeout) and an agent is handed it by name: `mcp:` in `agent.yaml`, or the "Máy chủ
  MCP" boxes in the agent editor, which apply at once. The client speaks streamable HTTP and is
  written on `httpx`; stdio servers are not run. A server's tools are named
  `mcp__<server>__<tool>` and follow `mcp:`, not the `tools` allow-list or the mode. A server's
  name is runs of letters and digits set apart by a single `-` or `_`, at most 32 characters, so
  no two servers' tools can come to one name. Every one of them asks before it runs and is never
  made again after a restart, until the owner lists it under `read_only`; a server saying its own
  tool only reads is shown and decides nothing. The file holds no key: a header takes its value
  from the environment as `${NAME}`, the variables are set from Connections, and saving one has
  the servers that are down tried at once. An address is used and shown as it is written: one that
  names a variable stops the start, since the server would be sent those very characters in place
  of a key. A server that answers 401 with no key of its own can be signed in to from Connections
  (OAuth 2.1 as a public client: discovery, dynamic registration, PKCE), which is how the hosted
  Notion server is reached. A sign-in starts only from a browser on the machine the crew runs on,
  goes only to public `https` addresses, and its tokens are kept beside the provider keys and
  shown by no API. A refresh token is said only to the authorization server that granted it, and a
  server that comes to name another is signed out instead; the code a person comes back with is
  traded only when it comes from the place that was asked (`iss`, RFC 9207); a sign-in begun and
  left changes nothing of the one in use; and only the authorization server saying the grant is
  spent or the client unknown ends a sign-in, so one that is merely down leaves it as it was. What
  a server may send is bounded: 4 MB an answer, a thousand tools, 128 characters a tool's name and
  50,000 characters of JSON its parameters. A tool past either of the last two is left out and
  named on the server's row; a server past the thousand is not connected and says so. `timeout`
  (60 seconds, 600 at most) is what one request gets and what connecting as a whole gets; a
  sign-in request gets 15 seconds and looking for where to sign in 30. A session the server has
  forgotten is opened again, and one that could not be is opened by the next call. A server that
  is down is a row that says why, never a crew that does not start: the crew waits ten seconds for
  its servers as it starts and keeps trying the rest behind, at growing intervals. New routes:
  `GET /api/mcp`, `POST /api/mcp/{name}/reconnect`, `POST` and `DELETE /api/mcp/{name}/login`,
  `GET /api/mcp/oauth/callback`. Connections gains a card with each server's state, reason, tools
  and who uses it; the Tools matrix lists MCP tools with their server and marks an agent that has
  not been handed the server apart from every other reason.
- An agent finds the MCP tools it was not told of with `tool_search`. A server's tools are let
  in `deferred` unless the file says otherwise: the model is not told of them on every call, and
  an agent that holds any such tool is handed `tool_search` with them. It asks in a few words or
  by a tool's name; the tools it holds are ranked by BM25 over each one's name, description and
  parameters, and the answer names the best five (ten at most) on a line each. From the next
  model call on those are told to the model like any other tool, after the ones it already
  knew, so the part of a request a provider keeps from call to call stays as it was. What a
  conversation loaded is read back from its stored `tool_search` answers: it lasts the
  conversation, reaches no other, and is the same after a restart. A loaded tool still asks
  before it runs; the search asks nobody and calls no server. `GET /api/tools` marks its row
  `with_mcp`; the Tools matrix gives it a "đi kèm MCP" badge and a mark of its own for an agent
  with nothing to find, and the agent editor's allow-list leaves it out.
- An agent can call its read-only tools from a short script with `tool_script`. A turn that
  needs one tool twenty times, or three lines out of a long answer, used to pay for every call
  and every answer in context; now the model writes that work as a script, the script makes
  the calls, and only what it prints comes back. The script is a small part of Python
  (variables, `if`/`for`/`while`, functions, lists, dicts, sets, tuples, f-strings,
  comprehensions, `try`/`except`, `json`, a fixed list of functions): no imports, classes or
  attribute reads, no files and no network. It runs in a process of its own with an empty
  environment, under limits on calls (25), steps, memory, CPU seconds, time and output, and on
  macOS inside a sandbox that denies the network, every write and a second process. A script
  may call only what reads and asks nobody: the built-in tools that declare a call may be made
  again, and of a server's tools the ones the owner both listed under `read_only` and let in
  as `codemode`. Anything that writes or asks first ends the script with a line saying to
  call it directly, where the approval gate sees it; so a script never waits on a person and
  is simply run again after a restart. The tool comes with such MCP tools and goes with them
  (an agent with no `read_only` + `codemode` tool has no `tool_script`), follows `mcp:` and
  not the `tools` allow-list, and each call a script made is charged like a call made
  directly and listed under the script's step on the run card (`calls` on a tool step in
  `/api/activity/runs` and on the `tool_result` event), folded until opened.

### Fixed

- The Tools matrix no longer goes on showing who held a tool when the manage screen was opened.
  It was read once, so after an agent was edited, made or removed, or an MCP server was signed
  out of or tried again, the grid kept the old holders until the page was reloaded. It is now
  read again each time it is opened, and while it is open when a server's tools change.
- Saving an agent's own routes from the agent editor no longer fails. The editor holds a route
  as a provider and a model apart and sent it so, while the server read only the
  `provider:model` line a person writes in `agent.yaml`, and answered 500. A route sent either
  way is now saved as that one line, and anything else is refused with a 422 that says what a
  route looks like.

## [0.11.1] — 2026-10-05

### Changed

- On Telegram a `FILE:` line that names a picture in the workspace (png, jpg, jpeg, webp) now
  sends it as a photo, the way a `MEDIA:` line does. It used to be refused as a format a chat
  does not take, so an agent that reached for the wrong prefix left the person with a line
  saying the file could not be sent. The list of documents a `FILE:` line may send is unchanged.

### Fixed

- The whole app no longer slides up and leaves a blank band under it. The labels a screen
  reader hears inside a message were positioned against the frame around the thread instead of
  the thread itself, so they stayed where the unscrolled thread put them, thousands of pixels
  below the window, and made the page itself scrollable. A wheel or trackpad that ran off the
  end of another column, a long canvas above all, then dragged the page. The thread now holds
  its own labels and the page has nothing to scroll.
- The same slide could start from two other columns, and no longer does: a long list of
  conversations with unread ones below the fold, whose dot carries such a label, and the manage
  screen, where an agent's editor with its prompt opened, or the canvas library, reached past
  the window. Each of those columns now holds its own labels as well.
- An agent asked over Telegram to write a canvas and send it now sends the canvas itself. The
  result of creating or importing one told every turn that the person saw the canvas beside the
  chat and named no way to send it, so the agent exported the canvas to its workspace and sent
  that file: a note arrived without its caption, and a page or a picture was refused for its
  suffix. A turn read over Telegram, or a job's, is now told that its reader does not see the
  canvas and given the `FILE: artifact:<id>` line that sends it.

## [0.11.0] — 2026-10-05

This release adds the canvas: a versioned document that a person and an agent edit together. An
agent writes one with its tools, the person edits it in a panel beside the web chat, and each is
told what the other changed. A canvas can be markdown, code, an HTML page, an SVG drawing, a
Mermaid diagram or a picture, moves to and from workspace files, and reaches Telegram chats and
scheduled jobs as an attached file with a list of what the turn wrote.

### Added

- Agents write canvases: versioned documents kept beside a conversation, in six kinds. Markdown,
  code, HTML pages, SVG drawings and Mermaid diagrams are written by an agent or a person; a
  picture (PNG, JPEG, GIF or WebP, told by its bytes and not by its name) comes in only when a
  workspace file is imported, and `artifact_read` says it cannot read one. One version holds at
  most 512 KB of markdown, code or Mermaid, 2 MB of SVG or picture and 4 MB of HTML, and a write
  past that is refused with the size and the cap. All versions of all canvases share 1 GiB, which
  a person may fill and where an agent is refused at nine tenths. Seven tools work on canvases:
  `artifact_create`, `artifact_list`, `artifact_read`, `artifact_edit`, `artifact_rewrite`,
  `artifact_import` and `artifact_export`. Only `artifact_export` asks for approval, since a
  canvas version stays restorable and a file written over does not. A web-chat, Telegram or job
  turn, or an agent delegated from one, may write; a turn from the inbound API lists, reads and
  exports, and its system prompt says so before the model tries. The master reaches every canvas;
  another agent reaches those linked to its conversation, shared down its delegation chain or made
  by itself, and one out of reach reads as missing. A canvas is read a page at a time within the
  output cap. An edit replaces one exact passage, quotes what it changed as a diff, reports the
  canvas's new length and, when it misses, quotes the closest passage. A rewrite needs the newest
  version read whole and is refused with a diff when someone saved since. A change spread over too
  many lines to show one by one is said to be so, and the agent is sent to read the canvas again.
  A page or a write over versions the agent has not seen names who wrote them: at most the six
  newest runs of one author, a restore as a run of its own naming the version it brought back. A
  version or line number sent as `Infinity` or `NaN` is refused with a sentence naming the
  argument, and a version number too large to exist reads as a version that is gone. A turn writes
  at most 30 versions of one canvas and creates at most 30 canvases, and later turns carry a note
  of where a write went instead of the document it sent. The tool descriptions send any document
  the person will keep editing to a canvas, however short, keep answers read once and questions in
  the chat, say how an edit adds text after a passage, and give the rules of a page: a Mermaid
  canvas is the diagram's syntax alone, with no code fence around it. An agent with a `tools:`
  allow-list gets only the canvas tools it lists.
- What a person changed in a canvas reaches the agent with their next message, without a tool
  call. The message is stored with a canvas note, built in the same transaction, naming each
  linked canvas that moved since the agent last saw or was told of it: a diff of the person's own
  edits for at most three canvases, the most recently changed first, or one line asking the agent
  to read again for another agent's versions, a restore or a very long change. Each diff and the
  whole note have a size cap, and canvases that do not fit are counted in a last line. The model
  reads the note right before the message in every call of the turn that message opened, and a
  fixed stub in later turns, so the system prompt and the cached prompt prefix do not change. A
  diff from the version seen whole that shows every change counts as seeing the new version;
  otherwise the agent reads again before a rewrite. A note that fails to build leaves the message
  stored without one. Forking a conversation copies each message's note and the canvases linked by
  the fork point, with nothing seen or read, and the run trajectory carries the note with its
  secrets redacted. A web-chat message also names the canvas open in the tab that sent it, so the
  note names what that device shows even when another device opened a different canvas since, and
  quotes the passage selected there. Opening a canvas shares it with the conversation, so the
  agents it delegates to reach it too. A selected passage, in the editor or in the page being
  read, can be asked about: a bar at the foot of the panel names the lines the selection lies on
  and offers a box for a question, which goes as one message with the passage as of the version
  just saved. In the page being read, a paragraph, a list item, a table row or a code block counts
  as the whole of its source lines; a passage longer than a message is cut at a line end, and a
  selection made with a touch screen's handles or select-all counts too. Asking is off while a
  turn runs, while the conversation waits for a decision and once the budget is spent, and the bar
  says which. A question the server refuses, or that cannot be saved or reached, stays in the box
  with the reason; on a phone, where the canvas covers the chat, the canvas is put away once the
  question went through, so the answer shows. A 422 for a message that carried a selected passage
  reads as a passage that no longer matches the canvas. In the thread, a message that carries a
  note shows a chip, closed until pressed: it shows the note as text with hidden characters
  written out as marks, and a button copies the note exactly as the agent read it.
- Typing in a canvas is saved, merged and kept. A save goes out 1.5 seconds after the last key, at
  once on Cmd/Ctrl+S, when the tab hides, when the canvas closes and before a message is sent from
  the chat, and names the version it was made on. A version saved elsewhere meanwhile merges with
  the typing when the two change different lines, and otherwise raises a conflict bar with a diff:
  keeping mine saves over it, and loading theirs can be undone. Typing not yet saved stays in a
  draft on the device, reopened with the canvas and dropped after 30 days or beyond the ten
  newest. A draft the device refuses first frees the drafts of other canvases, oldest first; when
  that makes no room the typing stays in the tab's memory, the panel says so, and the browser asks
  before the tab is closed. A failed save is tried again after 2 to 60 seconds. A read unanswered
  for 30 seconds counts as lost, and so does a save once 30 seconds and the time its size takes at
  50 KB a second have gone by; each save in a row that goes unanswered doubles the time for its
  size, up to eight times. The header says where the save stands, from saving and saved to waiting
  for a network, a slow network, the server not answering, too large (naming the kind's cap), the
  server full (naming the largest canvases) or deleted. The composer keeps a message's words
  read-only until the save has landed and the server has answered, then empties, or leaves the
  words in place when the message was refused. The wait for the save ends 5 seconds past the
  deadline the save was first given, with "Đang lưu canvas…" shown from 300 ms on; a message that
  goes before the save landed goes with the last saved version, and the chat says so. The history
  lists every version, newest first, with its author, age and size, compares one with the version
  before it or with the oldest, and restores one as the newest once the typing is saved. Opening
  another conversation saves the typing and closes the canvas; a save that fails after the switch
  is told in the chat until dismissed or saved after all, saying whether the typing is kept in the
  draft on the device or only in the tab. A canvas deleted elsewhere keeps its text to read and
  copy.
- The web chat opens canvases beside the conversation. A Canvas button leads the conversation
  header with the number of canvases linked to it and opens their list, newest first, each with
  its kind, version and last change; a button there makes an untitled canvas of the kind picked
  beside it (markdown unless changed) and opens its name to type over. A new HTML or SVG canvas
  starts as an empty page or drawing, and a Mermaid one as a flowchart of two boxes. From 1101 px
  wide the canvas takes a column, in a tab beside the activity, whose edge widens or narrows it by
  dragging or with the arrow keys; it is never narrower than 360 px and keeps its width for the
  next visit. Narrower, it covers the chat column, and Escape or "← Chat" closes it and gives
  focus back to the button. A canvas opens to edit when a person wrote its newest version and to
  read when an agent did, a picture always to read, and switches between the two without losing
  the typing. Reading shows markdown as the thread does, code as text, an HTML or Mermaid canvas
  as its page and an SVG or a picture as a picture; bidi and zero-width characters show as visible
  marks with a notice, while copy and download keep the text as it is. A canvas renames in place
  and downloads its newest version. The dock remembers which canvas it opened in each
  conversation, and entering a conversation on a wide screen opens again the canvas the server has
  open there, without taking focus from the composer. In the thread, a canvas write shows as a
  card for the canvas it touched: its title, what was done to which version, and a button that
  opens it. An import shows the same way, as "Đã nhập" or "Đã nhập lại"; an export, and a write
  that failed, was refused, was stopped or waits for approval, keep the plain tool card, and a
  card never shows arguments or content. A canvas the server no longer has says so and offers no
  button. A canvas the agent creates, or imports as a new one, during a turn the tab is showing
  opens beside the thread on a wide screen without taking the keyboard, unless the person is
  typing in a canvas or has the keyboard anywhere in the canvas column; the card still opens a
  canvas held back this way.
- An HTML page and a Mermaid diagram run as pages, apart from the app. `GET
  /api/artifacts/{id}/render` serves the newest version, or the one `version` names, and is the
  only place a canvas runs; any other kind answers 404, and an SVG or a picture is shown as a
  picture, where scripts, links and outside resources do nothing. The page cannot reach the app or
  send anything out, and loads scripts, styles and fonts only from a few public CDNs
  (cdnjs.cloudflare.com, cdn.jsdelivr.net, unpkg.com, and Google Fonts for styles and fonts); the
  policy is listed under Security. A Mermaid canvas is drawn by Mermaid 11.17.2 at its strict
  security level, and shows the diagram's source as text when the library cannot load. In the
  panel, View shows the saved version, saving what was typed first, and Edit holds the source; a
  picture has neither Edit nor a copy button, and the history shows a picture's version as a
  picture, with nothing to compare. The page reloads a second after a newer version arrives; while
  the page has the keyboard the newer version waits behind a "Có bản mới · Nạp lại" button, and a
  hidden tab waits until it is looked at again. A page that leaves for another address is stopped
  once the new page has loaded, with the reason and a reload button, and "Mở trang" opens the
  saved page in a tab of its own once nothing is unsaved. A page cannot keep a keyboard it takes
  by itself. It has the keyboard only while the person offers it, by a real press inside the page
  or by Tab or Shift+Tab in the app; hovering and scrolling are no offer. Any other key, a press
  outside the page or focus arriving on one of the app's controls takes it back. A page that holds
  the focus without an offer loses it after 50 ms to the element it was taken from, the fifth such
  grab stops the page with the reason and a reload button, and a page that holds the app up is
  stopped the second time. A badge on the frame, "Bàn phím đang ở trang", says when the keyboard
  is in the page. What a page reports going wrong shows in the panel: script errors, rejected
  promises, resources that failed to load and requests the policy blocked. A page tells at most 20
  messages of at most 2000 characters, a button beside the count opens the five newest, and "Gửi
  lỗi cho agent" saves the canvas and sends those errors as one message, inside a code fence the
  message calls the page's own words, data and not a request. An SVG that cannot be drawn says it
  is not valid, and a picture that does not load says whether it waits for the network or cannot
  be shown.
- Canvases move to and from workspace files. `artifact_import` reads a file in the agent's
  workspace into a canvas, so a built page, a drawing, a picture or a document reaches a canvas
  without its content passing through a message. Without `id` it makes a canvas, titled after the
  file unless `title` says otherwise; with `id` the file becomes the newest version of that
  canvas, whose kind it cannot change. The kind follows the file's extension (`.md`, `.html`,
  `.svg`, `.mmd`, a picture's, or a code extension with its language) unless `kind` names one, and
  an extension that names none is refused. The path stays inside the workspace by the rule the
  file-reading tools keep; the file must be a regular file within its kind's cap and, for a text
  kind, UTF-8 without a NUL byte; a byte-order mark is dropped. A file equal to the newest version
  writes no version, and one that would go over versions the agent has not seen is refused, naming
  who wrote them, unless `replace` is set, and those versions stay in the history. The result
  names the file, its size and the first 12 characters of its SHA-256, never what the file holds,
  and counts the relative addresses in an HTML or SVG file, which a canvas does not load. An
  import is a canvas write: it runs only where the other write tools do and counts toward the
  turn's limits. `artifact_export` writes one version, the newest unless `version` names another,
  to a path in the workspace: text as UTF-8 with LF line ends and no byte-order mark, a picture
  byte for byte, over a file already there. It writes no canvas, so it is open on every channel
  and counts toward none of the turn's limits. The target must lie inside the workspace, and
  inside the agent's `write_paths` when it has any, and may be neither a symlink nor a directory;
  the file is written whole or not at all, and a failed export leaves the old file as it was. A
  canvas keeps where it was imported from: the workspace file, or the link the import gave as
  `source_url`, an http or https address of at most 2000 characters. The panel names that source.
  A link shows as its host and opens in a new tab; a workspace source shows the agent and the path
  beside "Nhập lại", which saves the typing, reads the file again and says whether a new version
  was made or the file had not changed, and the history marks such a version "Nhập từ tệp". `POST
  /api/artifacts/{id}/reimport` does the same over REST, on the version the body names as
  `base_version`: a canvas with no workspace source answers 422, a source file or agent that is
  gone 410, a path outside the workspace 403, a file over the cap 413, a version saved since 409,
  and a file that cannot be read as the canvas's kind 422. Kit hooks hear of the two tools as the
  workspace tools they act as: a hook that names `Read` or `workspace_read` is asked about
  `artifact_import`, and one that names `Write` or `workspace_write` about `artifact_export`, with
  the real name in `tool_name`, `Read` or `Write` as `tool_alias` and the file path in
  `tool_input.path`.
- The manage screen has a Canvas section (`#/manage/canvas`): a library of every canvas, whatever
  conversation it was written in. It lists the 200 most recently changed, each with its kind,
  newest version, who made it, when it last changed and the size of all its versions, under a line
  with the number of canvases and the space they take against the limit; when there are more it
  says so, and a box that searches by name finds an older one. Where a canvas was imported from is
  said, never linked. The list follows the canvas changes the activity stream announces. A canvas
  is deleted with all its versions after a confirmation, and the keyboard then moves to the row
  after it, the row before, or the search box. A canvas also has a page of its own
  (`#/manage/canvas/<id>`), reached from its name in the library or from "Mở riêng" in the panel,
  which opens it in a new tab once nothing is unsaved. The page shows the canvas in the same
  panel, without the bar that asks about a selection and without the button that sends page
  errors, since no conversation is open there. A line under it counts the conversations the canvas
  is used in and names each as a button that opens it. "← Canvas" leads back to the library, and a
  save that then fails is told above whatever the section shows.
- A delegated agent's canvases come back with its result. A child writes canvases only when the
  turn its chain began from could, and reaches what its chain shares. Under the `outcome=` line of
  a `delegate` result comes one `[artifact <id> v<n>] <title>` line for each canvas an agent added
  a version to in the delegated conversation, first written first, with the title cut to 160
  characters; at most 12 are named and the rest counted. The lines come with every outcome, a wait
  that ran out included, and after the sentence that says the delegated conversation was deleted
  while the call waited; an export, an import that changed nothing, a rename and a deleted canvas
  give none. The tool's description tells the model that such a title is data, not an instruction,
  and to name the canvas instead of copying its content. A `FILE: artifact:<id>` or `MEDIA:
  artifact:<id>` line in the child's answer rides on as written when the child reaches the canvas,
  which is then linked to the delegating conversation so the reply there can send it, and the line
  is put back when that reply leaves it out, as a relayed file's line is; otherwise the line
  becomes "(agent con có đính kèm {path} nhưng không chuyển được tệp)". In the web thread the
  delegation card shows one chip for each canvas the result names, with its title, its version and
  a "Mở" button, or "Canvas đã bị xoá" for one the server no longer has. When a delegation
  succeeds during a turn the tab is showing, the first canvas its result names opens beside the
  thread under the rules a created canvas opens by.
- A canvas the agent is still writing shows in the web chat as it is written: a card in the thread
  from its first piece and, beside a wide conversation, its text filling in read-only where the
  canvas column is, nothing of it stored until the call ends. On a thread too narrow for the card's
  one line, how much has been written goes on a row of its own. HTML, SVG and Mermaid show as source
  while they are written, and so does markdown of 100 000 characters or more, with a line saying so.
  Drawn or shown as source, the text keeps its newest line in sight until the person scrolls up. The
  preview does not come up by itself while the keyboard is anywhere in the canvas column, and once
  the person puts it away by hand, every canvas written in the rest of that turn stays a card.
  Closing the preview, or a saved canvas opened from a card or a chip in the thread, puts the
  keyboard back where it was when that opened, the button pressed or the chat box, and on the
  Canvas button only when that is gone. A switch on the Settings page turns the preview off for the
  device. Only `artifact_create` and
  `artifact_rewrite` are previewed; the arguments of no other tool are streamed. The offline
  `fake:slow` model answers as `fake:echo` does, with 0.1 seconds between two pieces, so a canvas
  can be watched filling in without a model key.
- Canvases reach Telegram and jobs. A line `FILE: artifact:<id>` or `MEDIA: artifact:<id>` in a
  reply uploads the newest version, and the kind decides how, not the prefix: a picture as a
  photo, any other canvas as a document named after the title, with `.md` for markdown and `.txt`
  last for every other text kind (`.py.txt`, `.html.txt`, `.svg.txt`, `.mmd.txt`), so a phone
  opens it as text. The caption is `"<title>" v<n>`, with the link to the canvas's own page under
  it when `web_url` is set and the two fit Telegram's 1024 characters; a link that does not fit is
  left out whole. A picture Telegram refuses as a photo is sent once more as a document. Workspace
  files go first, then canvases, each once however often it is named. A reply sends only what the
  agent's canvas tools would let it read in that conversation; a canvas out of reach, one over 20
  MB, a failed upload and a miswritten id each get a one-line notice in the chat and do not stop
  the next attachment. A text canvas imported from a workspace file of a type a `FILE:` line would
  not send is not sent either. After a Telegram turn or a job's brief, a message headed "Canvas
  vừa ghi:" follows the reply with one line `• "<title>" v<n>` for each canvas the turn wrote,
  what a delegated agent wrote included, at the newest version written and only when the agent
  still reaches it. Under each comes the link to its page when `web_url` is set; without it the
  message ends "Mở web UI để xem.". At most ten are listed and the rest counted. A write that
  changed nothing, a read and an export name nothing, and a job that answers `OK` sends no list. A
  turn that wrote canvases and said nothing is answered by the list, a turn that broke or a run
  that stopped early still names what it wrote, and each reply of a turn that waited for approval
  names what was written on its own stretch. In the web chat the same attachment line shows as a
  chip that names the canvas and opens it with "Mở". `web_url` in `config.yaml`, or
  `MY_AGENT_WEB_URL`, which wins, is the address people open the web UI at, and the links read
  `<web_url>/#/manage/canvas/<id>`. It must be a plain http or https address with a host, an
  optional port and a plain path, with no user name, password, query or fragment; any other value
  stops the settings from loading, with an error that names the key and never the value. A final
  slash is dropped.
- Canvases over REST and on the streams. `GET/POST /api/artifacts` lists (newest first, by
  conversation or title) and creates the five text kinds, and `GET/PUT/PATCH/DELETE
  /api/artifacts/{id}` reads, saves, renames and deletes one. A save names the version it was made
  on, and a save on an older version is refused with 409 and the newest version's number, author
  and text. `GET …/versions[/{n}]` lists the history and reads one version, `POST …/restore`
  writes an old version back as the newest (a version number too large to exist is a version that
  is gone: 404 on a read or a restore, the conflict of a stale save on a save), `GET …/raw` serves
  a version as text, as a picture or as a download named after its title, and `GET
  /api/artifacts/usage` reports the number of canvases, the bytes their versions take, the ceiling
  they share and the bytes of each. `GET/PUT /api/conversations/{id}/canvas` reads and sets the
  canvas open in a conversation, with the passage selected in it; a selection the note would drop,
  or one cut through a character, is refused with 422 and changes nothing. Every write over REST
  is the person's: no body names an author or a conversation for it. A refusal from the store
  answers with its own status (404, 409, 413, 422, 507) and a structured body, never a 500, and
  text holding half of a surrogate pair is refused with 422 naming the part of the request that
  holds it. The activity stream announces every canvas change as an `artifact` event with the
  conversations linked to the canvas. The stream a web-chat message is answered with carries two
  new events, neither stored nor sent on the activity stream. `user_context` opens a turn with the
  note stored with the message, when it has one, so a tab that merely watches the conversation
  never receives a passage someone quoted. `tool_call_delta` carries a piece of the arguments of
  an `artifact_create` or `artifact_rewrite` call, with `index`, `name`, `chunk` and `attempt`:
  the first piece as soon as the call is named, later ones at most once every 3 seconds, and an
  event with an empty `name` calls off an attempt that was given up. The whole call still comes
  with `assistant_message`.
- Behaviour evals can work on a canvas between two messages, as the person would in the web panel
  and over the same routes: `create_canvas`, `edit_canvas` (replaces one exact passage and saves
  on the version it read) and `select_canvas` (the next message carries the selection's lines). A
  step that cannot be done fails the run before the next message. New expectations judge the
  canvases linked to the conversation when the run ends: `canvas_count`, `canvas_contains`,
  `canvas_not_contains`, and `canvas_not_in_chat`, which fails when the agent's messages repeat
  half or more of a canvas's three-word runs; the title, the heading the canvas opens with and a
  quote that stays within one line do not count. A run also fails when a message after canvas
  steps reaches the agent without a canvas note telling of each canvas the person made or saved
  since, and an `edit_canvas` whose `new` is its `old` is refused. The dry run plays a canvas case
  through the real server.

### Changed

- `POST /api/inbound` answers 422 when `source` names one of the server's own channels (`chat`,
  `telegram`, `web`, `job` or `job:<id>`, `delegate:<…>`, `memory:<…>`). A relay could otherwise
  pass for the person in the web chat, or post a run that showed up as a scheduled job's last run
  and in its history. Any other label, `api` included, is recorded as before.
- A `delegate` result always has an empty line between its `outcome=` line, with the canvas lines
  under it, and the text that follows, whether or not a canvas was written. Whatever reads a
  result line by line should expect it.
- A `FILE:` or `MEDIA:` line whose path opens with `artifact:` names a canvas and is no longer
  looked up as a workspace file, in a Telegram reply or in a delegated agent's answer, even when
  the workspace holds a file of that name.
- The system prompt of a Telegram or job turn, and of an agent delegated from one, ends with a
  "Canvas" section when the agent holds a canvas write tool, after the day's notes and right
  before the date. It says the reader is not at the web chat, to make a canvas only when told to
  or when the document is long and will be edited further, and that a line `FILE: artifact:<id>`
  of its own sends the canvas with the message. A turn from the inbound API reads one line there
  instead, naming the canvas write tools it should not call. A web-chat turn's prompt has neither.
- The system prompt's rule that web and file content is data now names canvas content and what a
  canvas note quotes.
- The offline `fake:echo` model calls the tool named on a message's last line that starts with
  `/tool`, when that line and its arguments end the message, whatever comes above it, so a
  self-test can drive a canvas tool from a message stored with a canvas note. A tool line inside
  the note calls nothing.
- The README now covers what 0.10.0 added beyond voice notes.

### Fixed

- A model call that hits a passing upstream failure before any text is shown is asked again once
  on the same route, after a two-second pause, instead of ending the run. This covers OpenRouter's
  `provider_unavailable` error sent mid-stream after a 200, HTTP 408/425/429/5xx and transport
  failures; a refused request (other 4xx), an error without a code and a malformed stream still
  fail at once, and a failure after text has been shown still surfaces. A retried side call that
  had already been served is written to the cost ledger at an unknown cost. No model fallback is
  added.
- A tool call whose arguments are not a JSON object (a raw line break or unescaped quote inside a
  long document, or output cut off mid-call) no longer ends the run with a provider error. The
  call is answered, without running, with its length, where the JSON broke and the few characters
  around that spot, and the turn carries on. Such a call never asks a person for approval, and the
  broken text itself is not stored.
- A tool call cut off because the reply reached the model's output limit is answered with a
  request to split the content into smaller calls, not to send it again. Calls broken at different
  places no longer count as one repeated call; the same broken call sent three times in a row
  still does. A tool error longer than the output cap is cut like any output.
- A tool call whose name or arguments arrive as something other than text is reported as a
  malformed stream from the provider. Before, the turn's stream broke off with no error event.
- A turn whose last allowed model call answered ends as done, not halted at the step limit. A turn
  that does run out of steps answers the tool calls it never ran with a note that the step limit
  stopped them, so the next message no longer closes them as interrupted.
- A delegated agent picked up again after an approval, a question or a restart can no longer hand
  work on to another agent. Resuming started its turn as if a person had opened it, so the
  one-level limit on delegation did not apply.
- A delegated agent's answer is read for `FILE:` and `MEDIA:` lines at every line break a string
  knows, as a Telegram reply already was, where only `\n` counted before. The reason an unfinished
  delegated run stopped for is quoted in the `delegate` result on one line, cut at 160 characters,
  so a provider's error can add no lines of its own to the result.
- A Telegram notice about an attachment that could not be sent no longer stops the attachments
  named after it when the notice itself cannot be sent; it is logged instead.
- Deleting a conversation is all or nothing. A delete that failed midway is rolled back, where the
  next unrelated write used to finish it and take the messages of a conversation reported as still
  there.
- An agent id that ends in a line break is refused. `coder` followed by a newline passed the check
  and named a directory.
- The web app ignores a stream event of a kind it does not know. A tab older than the server broke
  on the first such event; a tab still open from 0.10.0 has this fault until it is reloaded.
- An image from another site, which waits for a tap before it loads, asks again when its address
  changes. One agreed image used to let any later image in the same place load unasked.
- A message the server queued, because the conversation was busy somewhere the web tab could not
  see, no longer comes back to the composer while a chip stands for it. A message the server
  refused now gives its words back and takes its bubble back. A send cut off on purpose, by Stop
  or by leaving the conversation, counts as sent, not as failed.
- The conversation no longer stops following its newest line while a reply arrives. A reply that
  came in a burst, or a turn whose start removed the fork buttons above the view, could read as
  the reader scrolling up, and the answer sat below the screen. Only a move up lets go of the
  newest line now; a reader who has scrolled back keeps their place.
- A tool call that failed stays failed when the conversation is read back. The web drew every
  stored call that was not denied as done, with the error only inside the result. That holds now
  for every way a call fails: a tool that raised, a tool that does not exist, a hook's block,
  arguments that were not valid JSON or were cut off, the step limit, a repeated call, an approval
  given to another call, a branch away, a call cut short, and a handed-off task whose wait ran
  out.
- A link whose address holds an escape that cannot be read, `#/manage/crew/%` for one, no longer
  opens the web app on a blank screen. The part that cannot be read is taken as not there, and the
  section opens on its list.
- Each behaviour eval run starts from the server as the first run found it. The runs share one
  server, so a later run was judged on the conversations, canvases and notes an earlier one left.
  Before every run the runner deletes every canvas and conversation, checks none is left and puts
  the memory files back, never outside the run dir and without following a link; when it cannot,
  the eval stops. What a deleted conversation's turns cost still counts toward the budget. Each
  run also leaves a JSON transcript of its conversation, child conversations, canvases and
  approvals in `results/transcripts/`; it can hold what the agents know, so delete it by hand.
- An eval expectation pinned to a turn counts turns by the messages the case sent. A note the
  server stores as the person's message, the loop guard's above all, started a turn of its own, so
  a tool called after it was judged as the next turn's. A conversation that does not hold every
  message the case sent now fails the run.

### Security

- A file in an agent's workspace no longer opens as a page of the app. `GET
  /api/agents/{id}/files` served each file with the type its extension suggested, so an HTML or
  SVG file an agent wrote, opened from its link, ran its scripts with the app's origin and could
  call every API route. Now only raster images, PDF and plain text open in place, and any other
  file downloads as `application/octet-stream`. Every response but a PDF's is sandboxed with no
  scripts, and every one carries `X-Content-Type-Options: nosniff` and
  `Cross-Origin-Resource-Policy: same-origin`. The types are pinned in code, not read from the
  machine's MIME table.
- A browser request to the API that says it comes from elsewhere is refused. The local guard
  judged a browser request by its `Origin` header alone; it now also reads `Sec-Fetch-Site` and
  answers 403 to a request under `/api/` whose value is anything but `same-origin` or `none`. A
  request without the header, as `curl` or another program that is no browser sends, passes as
  before, and a canvas's render page is the one address such a request still reaches.
- The web app can no longer be shown in a frame on another site. Every response, an unhandled
  error's included, carries `Content-Security-Policy: frame-ancestors 'self'`.
- A canvas page runs under a policy of its own. The render route answers with `sandbox
  allow-scripts` and never `allow-same-origin`, so the page has an origin that is not the app's.
  Scripts, styles and fonts come inline or from the three CDNs (styles and fonts also from Google
  Fonts), images and media only from `data:` and `blob:` addresses, and the policy allows no
  `fetch`, `XMLHttpRequest` or WebSocket, no form target and no `<base>`. The response may be
  framed by the app alone and is sent with `nosniff`, no referrer, DNS prefetching off and
  `no-store`. Mermaid is loaded under an integrity hash. The raw route serves a version with no
  scripts, and an HTML page, an SVG drawing and HTML code download as `.html.txt` or `.svg.txt`,
  so opening the file shows the code.
- What the runtime itself says in a Telegram chat goes out as it stands and is no longer read for
  `FILE:` and `MEDIA:` lines: the answer to a slash command, `/status` with the conversation's
  title among them, that an approval ran out, why a run was cut short or did not finish, that a
  reply was empty, and the error a turn broke with. A line of such a sentence shaped like an
  attachment line used to send the file it named. What the agent said before a turn broke is still
  read for the files it names.
- A canvas sent to Telegram passes the secret filter the run trajectory uses: secrets the server
  knows are covered in the text, the caption, the file name and the titles in the list of written
  canvases. A picture's bytes go as they are.
- A source link with a user name or a password in it is refused by `artifact_import`, since it
  would be stored and shown to everyone the canvas is. In the panel only a plain http or https
  address on another origin than the app's becomes a link.
- The export log names where a write was going with the place quoted and any line break in it
  escaped, so a folder's name cannot start a log line of its own.
- The bench and eval servers get only what a program needs to run from the caller's environment
  (`PATH`, `HOME`, the locale, `TERM`, `TMPDIR`, `USER`, `LOGNAME`, `SHELL`, `TZ`) and
  `OPENROUTER_API_KEY`. Before, they got the rest of the operator's shell but for a short list of
  dropped names, and so did every hook they ran.

### Upgrade notes

- The database gains four tables (`artifacts`, `artifact_versions`, `conversation_artifacts`,
  `canvas_focus`) and three columns (`messages.context`, `conversations.root_id`,
  `conversations.root_source`), all added on start and empty for existing rows. Nothing is
  rewritten or removed, but back up `agent.sqlite3` before the first start.
- Agents with their own `tools:` list in `agent.yaml` get no canvas tool until its name is added
  to that list; agents without a list get all seven on start.
- `web_url` (`MY_AGENT_WEB_URL`) is empty by default, and without it Telegram messages carry no
  link to a canvas. A host that is neither `localhost` nor an IP address must also be listed in
  `MY_AGENT_ALLOWED_HOSTS`, or the server refuses the request the link leads to.
- Reload browser tabs left open from 0.10.0. The old page breaks on the stream events this version
  adds, and the update bar only offers the reload.
- The system prompt of a Telegram or job turn gains a "Canvas" section for an agent that holds a
  canvas write tool, and a turn from the inbound API gains one line telling it not to call them. A
  web-chat turn's prompt is unchanged.
- A `FILE:` or `MEDIA:` line whose path opens with `artifact:` is no longer a workspace file.
  Rename a workspace file or folder of that name.
- A `delegate` result always has an empty line before the answer. Anything that reads the result
  line by line should expect it.
- `POST /api/inbound` answers 422 for a `source` of `chat`, `telegram`, `web`, `job`, `job:<id>`,
  `delegate:<…>` or `memory:<…>`. A caller that sent one of these needs another label.
- A workspace file that is not a raster image, a PDF or plain text now downloads from its link
  instead of opening in the browser. This includes HTML and SVG files.
- A browser request to `/api/` from another origin, another local port included, gets 403. A
  browser tool served from elsewhere that called the API no longer can; programs that are no
  browser are not affected.
- The eval and bench servers no longer inherit the caller's `MY_AGENT_*` variables or any key but
  `OPENROUTER_API_KEY`. A hook or a case that relied on another variable will not find it.
- A delegated conversation opened before the upgrade has no record of the channel its chain began
  from, so an agent resumed in it cannot write canvases. A new delegation can.
- `write_paths` now also holds `artifact_export`: an agent with the key exports only inside the
  paths it lists.

## [0.10.0] — 2026-09-30

The crew now works more like people who share a desk. A message sent while an agent is busy
waits its turn, and one that starts with a slash command steers the turn already running;
Telegram turns run in the background so the bot keeps answering, and a voice note is
transcribed, with the transcript echoed back, before the master sees it. What was said stays
findable: an agent searches its own past conversations and the master the whole crew's, and a
conversation can be forked at an earlier message to try it another way. Memory keeps itself
current: each line carries the day it was last confirmed, and a rewrite that drops or rewords
a line waits for a person. An agent can propose its own repeating job, which runs only after a
person approves the verbatim prompt, and a tool output cut short stays readable in full
through `tool_output_read`. Every model call, including the side calls for titles, summaries
and memory, now lands in the cost ledger, and a run's trajectory downloads as JSON or Markdown.

### Added

- A tool result that was shortened for being over the output cap can now be read back in full.
  The original is kept under `spill/<conversation>/` in the home, the shortened text ends with
  a line naming the call id, and the new `tool_output_read` tool (`id`, `offset`, `limit`)
  returns it in segments that always fit the cap. It reads only the conversation it is called
  from and refuses an id that more than one result shares. Once old tool results are stubbed
  out of the prompt, the stub names the id to read them back with. Only agents whose tool list
  includes `tool_output_read` (every agent without an allow-list, and the kongming and
  researcher templates) get the spill and the pointer; an agent with a narrowed list is
  unchanged. Spill files go away with their conversation, a fork gets its own copy, and a daily
  sweep removes anything older than seven days.
- Every line in `MEMORY.md` can now carry the day it was last confirmed. On the next
  consolidation, an undated line or one older than ninety days goes back to the model for an
  explicit keep, fix or drop with a reason, and a newer note wins over an older line it
  contradicts. The reasons show on the proposal card before anyone decides. A master's
  consolidation also reviews the shared user facts and may propose forgetting or updating one
  that new notes contradict or nobody has confirmed in a while; those proposals always wait for
  a person, since every agent reads the facts. The facts list on the memory screen flags a fact
  nobody has confirmed in over ninety days.
- A button under a saved user message forks the conversation there: the server copies every
  message before it into a new conversation, closes any tool call still open at the cut without
  running it, and resets cost, approvals and autonomy to the agent's own defaults. The composer
  opens on the fork prefilled with the cut message's own text; the source conversation, its spend
  and its approvals are untouched. The header names where a fork came from and links back to it.
- A voice note (or audio file) sent on Telegram is transcribed by its own `audio_routes` chain
  before the master ever sees it. The channel replies "Đã nghe: …" with the transcript so the
  sender can catch a mishearing, then hands that text to the master as an ordinary message —
  never as a slash command or a `/steer`, whatever it starts with. A note over 300 seconds, over
  10 MB, or in a format none of `mp3/m4a/ogg/wav/flac/aac` covers is refused before download.
  Transcription cost is recorded under a new `transcribe` purpose in the cost ledger, and the
  connections page lists the configured audio route the same way it already lists vision routes.
- The costs page splits the whole ledger by what each call was for: the turns' own calls, and
  the ones made beside them — a conversation's title, a session recap, a long tool output
  summarised, a picture or a scanned PDF page read, memory consolidation, the wiki compile.
- A tool that asked a model itself shows the price on its row of the run timeline.
- A turn that keeps making the same tool calls is stopped before it burns its step limit. At
  the third identical call in a row the agent is told it is repeating itself, naming the tool
  and nothing a tool returned; three more identical calls halt the turn with the reason "loop",
  and the call that would have been the sixth is answered with a refusal instead of running.
  Repeats with a change in between ("run the tests, fix, run them again") are left alone.
- `scripts/run_evals.py` plays written cases against your own agents and the real model. A case
  is a short conversation with one agent plus what must, and must not, happen in it: the tools
  it calls, what it asks approval for, what it says, whom it delegates to and what it costs.
  Every case is played several times and passes when two runs in three do. It runs on a copy of
  your home in a throwaway folder, so nothing touches the live crew: the copy has no schedule,
  no Telegram bot, no secrets file, no shell allow list and no login files, and a command that
  names a path of the live home or a workspace is refused even when the case approves. Money
  spent is read from the usage ledger and capped by `--max-usd`. `--dry-run` swaps in the fake
  model to check the plumbing. Cases live in `<home>/evals/`; see docs/testing.md.
- `--no-schedule` starts the server with no scheduler and no channels.
- A delegation's result says what the handed-off task came to, on its second line, not only how
  the child's run ended: `outcome=done`, `done_with_concerns`, `blocked`, `needs_context` or
  `failed`, with a reason when it is not done. The runtime's facts come first: a run that
  errored, halted or outlasted the wait failed, and a child whose last tool approval was refused
  or lapsed is blocked; a question answered after that does not lift it. Otherwise the child's
  closing `Status:` line decides, however a model writes it (a bold key, a heading, a value with
  spaces or hyphens, in backticks), and a child that declared nothing is done, as before. A
  `Status:` line inside a code block is something the child is showing, such as a task list or
  a ticket, and counts only when there is none outside one. The tool tells the agent that
  delegated to say plainly when a task is not done, and why.
- The delegation card on the web names the outcome in words, marks one that is not done, and
  shows the reason beside it, in words too: how the child's run stopped, a wait that ran out, a
  tool approval refused or lapsed.
- An eval case can require what a delegation came to: `delegates_to: {agent, outcome}`.
- A schedule, or the master's `telegram:` block, may say how long an approval in the
  conversation it opens waits for a person: `approval_ttl_seconds`, whole seconds from 60 to
  43200. A job that asks at night can wait for the morning instead of expiring in ten minutes.
  The conversation keeps its wait for every later approval, after a restart too, a delegated
  child copies its parent's, and the parent waits on the child that long plus five minutes.
  Without the key the global `approval_ttl_seconds` applies as before. The web editor keeps the
  key through edits of other rows and of the chat id, but has no box for it.
- A run downloads from its own page as JSON or Markdown
  (`GET /api/activity/runs/{id}/trajectory?format=json|md`): its record, the messages of that
  run alone, every tool call with its arguments and result, and the transcript of each child it
  delegated to. A new run notes where its conversation stood when it began, so its messages stop
  where the next run's begin; a run recorded before that is sliced by its start and finish time
  and says so. Secrets are covered on a best-effort basis: the values of the server's
  environment variables named like a key, token, secret, password or credential, and common key
  shapes (`sk-…`, `Bearer …`, JWT). An environment value is also covered where the run's record
  holds only part of it: a title or preview cut partway through it, a summary kept from partway
  through it, a copy escaped inside JSON, or an argument's name. A secret from anywhere else is
  not, so the file and the page both say to read it before sharing. A tool result is cut at
  2,000 characters unless `full=1` is asked for. In the Markdown, a title stays on one line and
  a code block a message left open is closed before the next message begins.
- A message sent while its conversation is busy waits its turn instead of starting a second
  turn beside the running one. A plain message waits in the conversation's line; once the
  running turn is over, everything that waited is answered by a turn of its own, as one message
  in the order it was sent. A message that starts with `/steer <text>`, or with a command from
  the agent's kit, goes into the running turn instead: the agent reads it once the tool it is
  running returns, before its next model call, the run shows it as a step, and the same turn
  answers it. One that arrives after the turn's last look waits in line like any other message.
  With nothing running, `/steer X` is simply the message X, and a bare `/steer` is refused (422)
  either way. A line holds 20 messages; the 21st is refused (429) with the reason. The line lives in
  the database, so what waits is answered after a restart too (a server started with `--no-schedule`
  starts nothing on its own and leaves it for the conversation's next turn), and it goes with its
  conversation when that is deleted. A conversation waiting on a person's decision still refuses new
  messages (409).
- `GET /api/conversations/{id}` lists what waits under `queued`, and
  `POST /api/conversations/{id}/stop` hands it back as `cleared`, empties the line and stops the
  turn the line started, if one runs (`cancelled`). A turn a browser tab is reading, one the
  Telegram bot runs for a message it just got, or a job's, is not the line's to stop.
- The composer no longer locks while its conversation is busy: typing and Enter still send, only
  where the message goes changes. A plain message becomes a chip reading "Đã xếp hàng, chạy sau
  lượt này" and is sent by a POST of its own, never touching the running turn's stream or its
  `AbortController`; a `/steer` message or a kit command becomes a chip reading "Sẽ chèn vào lượt
  đang chạy", and once the server folds it in, the chip turns into a user message in place and the
  run draws an empty dot on its timeline for the step, so a person's steer reads apart from the
  agent's own work. Stop is the only way to take a message back: it calls the server first, within
  three seconds, so the line has a chance to be cleared in order before the tab aborts its own
  turn, then returns every cleared chip's text to the composer in the order it was sent. Stopping
  with nothing left to clear says nothing; clearing chips from a turn the server could not cancel
  (Telegram, a job, another tab) says so instead of clearing them silently. A conversation's chips
  survive a reload: they come from `queued` on the conversation's own record, not from anything
  kept only in the tab.
- A run first seen already running while its tab still shows a queued chip is reloaded right away,
  instead of waiting for a status change that a turn finishing between polls, or one halted on its
  own budget, may never produce — the chip could otherwise outlive the turn it was queued behind.
- A message sent to `POST /api/inbound` while its conversation is busy is answered at once with
  `status` `queued`, `queued: true`, no steps and a notice as its text; the answer itself is read
  back from the conversation. Every reply carries `queued`.
- The Telegram bot reads the chat while a turn runs: the turn runs in the background, `/status`
  answers mid-turn with how many messages wait, a plain message waits in the conversation's line
  and is answered by a turn of its own, and `/steer <text>` (or a kit command) is steered into
  the running turn. The chat stays in its conversation until the turn and its line are done, even
  past midnight, and `/new` waits for them. A stop waits for every running turn before cutting it
  off, and a "typing…" indicator Telegram does not answer no longer holds the turn.
- A new `conversation_search` tool finds what was said in an older conversation, across a full
  FTS5 index of every message body. An agent searches its own conversations; the master can name
  another agent or search the whole crew. Typing without accents still reaches an accented word
  (`đ`/`Đ` are folded to `d`/`D` before indexing, on top of SQLite's own accent-insensitive
  tokenizer), results are capped at three per conversation so one long thread cannot crowd out
  everything else, and the conversation a call runs from is left out of its own search. The
  sidebar's own search box, once it is showing, now searches message content the same way and
  lists "Trong nội dung" hits below the title matches, each naming the agent it came from and
  opening straight into that conversation on a click, over a new `GET /api/messages/search`.
- A new `schedule_create` tool lets an agent propose a recurring job itself instead of waiting
  for `agent.yaml` to be hand-edited: a name, a prompt, exactly one of `cron` or `every`, and an
  optional list of skills. It always stops for a person, even in an `autonomous` conversation,
  even when the tool sits in `auto_approve`, even when it sits in the agent's own allow list —
  no setting in `agent.yaml` or `config.yaml` can wave this one through, because approving it
  means handing the agent an unattended future turn. The approval card spells the schedule out in
  words the same way the jobs tab already does ("Mỗi ngày 07:00"), lists the next three times it
  would run (approximate for an interval, which counts from the approval), and shows the
  verbatim prompt that will run every time after that. A proposal outside the limits — under
  15 minutes apart, an interval over a year, no run within the next year, a cron over 100
  characters, an empty name or prompt, one over the length cap, an unknown skill, an agent that
  already has 20 such schedules — still produces an honest card whose reason is the error
  itself; the cap is checked once more when the approved call runs, since another approval can
  land in between. Once approved, the schedule runs
  without a server restart and survives the next one; the jobs tab labels it "tạo từ chat" beside
  the ones written by hand and offers a delete button only for this kind, since a hand-written
  one needs its file edited instead. It has no edit button either: the agent editor holds only
  the schedules from `agent.yaml`, so changing one means deleting it and proposing it again.

### Changed

- The web approval card no longer offers "Luôn cho phép" on a request that stopped for a
  reason — a shell command matching the ask list, or a proposed schedule. Always-allowing the
  tool from there never waived that pause; it only quietly let the same tool's other calls run
  unasked, which is not what a card about one flagged call suggests. Other cards keep the
  button.
- Whether a memory rewrite applies on its own is decided by code from the old and new text, not
  by the model, and this changes what an `autonomous` agent does: a rewrite that only adds lines
  or updates dates still applies at once, but one that drops or rewords a line, or brings a
  date found in neither the old memory nor the notes it read, now waits for a person. A new
  rewrite proposal replaces any older one still pending for the same agent.
- A halted run says why in words on Telegram and in the reply of an API turn (the cost cap, the
  step limit, the same call over and over) instead of the loop's code, as the web already did.
- Only a task that came to `done` is handed straight to the person. A child that needs more
  context, finished with concerns or was blocked goes back to the agent that delegated, which
  reports it. The check reads the child's closing `Status:` line instead of looking for the word
  BLOCKED anywhere in its answer, so that word in the prose of a finished task no longer holds
  the answer back.
- An approval nobody answered tells the model that the action did not run and nothing changed,
  and not to redo it or reach the same end with another tool, but to tell the person what is
  waiting so they can ask again.

### Fixed

- Approving a memory rewrite after `MEMORY.md` changed since it was proposed is refused (409) and
  the proposal is marked superseded, instead of overwriting what was written in between; a
  rewrite applied on its own checks the same way. A superseded proposal shows in the history
  with no undo, since none of it was ever applied.
- `fetch_url` no longer returns an empty result. A server that answers 202 (accepted, nothing to
  read yet) is reported as not ready, and a page with no readable text (an empty body, or one
  drawn only by JavaScript) is reported as such instead of reading as a page that says nothing.
  A blank scrape from firecrawl falls back to fetching the page itself, as an empty one did.
- A delegation that outlasts its wait still names the child's conversation, so its card can
  open it, and reads as failed.
- The fake model gives every tool call an id of its own, as a real provider does. Two
  conversations that delegated at the same point used to share an id, and the second was handed
  the first one's child.
- Model calls made beside a turn now reach the usage ledger. Titles, recaps, tool-output
  summaries, picture and scanned-page reads, consolidation and the wiki compile were billed by
  the provider but missing from the day and model totals. Each is now written down with its
  purpose, provider, model, tokens and price, never its prompt; a call abandoned mid-answer is
  written down at an unknown price instead of being lost.
- A run's total includes what its tools paid a model (a picture, a scanned page, a summary), so
  the run, its conversation and the ledger agree.
- A tool-output summary whose provider gave no price counts as a call of unknown cost instead of
  a free one, and a session recap that came back empty is still charged to its conversation.
- Grouping the ledger by model keeps one model name served by two providers as two rows.
- Runs that began in the same second keep the order they were created in. A run is saved again
  at every step, and each save used to move it ahead of the others in the activity list.
- Two turns no longer run at once in one conversation. A message sent while a turn was running
  started a second turn beside it, both writing into the same history.
- A decision holds its conversation from the moment it is taken. A message sent right after it
  waits for the turn the decision resumes instead of being refused or running beside it; a
  second decision on the same request, sent before that turn began, is refused (409) instead of
  racing the first; and the sweep that expires unanswered approvals leaves it alone.
- A tool call a turn left without a result — the turn was stopped, or the server went down
  mid-call — no longer runs again when the next message arrives, with its result landing after
  that message. It is closed before the message: with the decision taken on it when there was
  one, otherwise with a note that it was interrupted and may or may not have run, so the model
  checks before trying again. A call still waiting on a person is left open.
- Finding a cron schedule's next run no longer walks the calendar minute by minute: it jumps to
  the next day, hour or minute that can match instead, so a yearly schedule whose next run is
  months away resolves in a handful of steps rather than several hundred thousand.
- A tool call id that a provider left out is now a unique generated id instead of one derived
  from its position, so two such calls in one conversation no longer share an id.
- A reused call id whose stored approval names a different call is refused instead of being
  run under that approval.
- A delegated child conversation is found only through its own parent's call, so a call id
  from another conversation can no longer open it.

### Upgrade notes

- The database gains a `side_calls` table, created on start. Calls from before the upgrade
  stay as they were: the ledger is complete from this version on.
- The database gains a `queued_messages` table, created on start.
- The database gains a `messages_fts` full-text index over message bodies, built and filled on
  the first start; with a long history that start takes longer, once. A Python whose SQLite has
  no FTS5 module stops at startup with a message saying so.
- The `conversations.forked_from` and `memory_proposals.reasons` columns are added on start,
  empty for existing rows.
- The database gains a `created_schedules` table, created on start, holding the schedules an
  agent proposed through `schedule_create` and a person approved.
- The `conversations.approval_ttl_seconds` and `runs.after_seq` columns are added on start,
  empty for existing rows. A conversation without its own wait uses the global
  `approval_ttl_seconds` as before; a run from before the upgrade exports its trajectory by its
  start and finish time instead of by message sequence.
- Agents with their own `tools:` list in `agent.yaml` do not get `conversation_search`,
  `schedule_create` or `tool_output_read` until those names are added to that list; agents
  without a list get all three on start.
- Voice notes are transcribed through `audio_routes`, which defaults to
  `openrouter:google/gemini-2.5-flash-lite`: the key that already enables image reading enables
  this too. Set it empty to turn transcription off.
- A tool output too long for its cap is kept whole under `spill/` in the home, at most 5 MB a
  file. The server sweeps files older than seven days on start and once a day, and deletes a
  conversation's folder with the conversation.

## [0.9.2] — 2026-09-28

A one-fix release: a delegated answer that ended on a bare chart line reached the person as the
chart alone. The advice it illustrated now arrives with it.

### Fixed

- A delegated agent that writes its answer next to a tool call and ends on a bare `MEDIA:` line no
  longer hands on only the chart. The child's answer is the last thing it said before the
  attachment lines, with them added, so a relayed reply carries the advice as well as the picture.

### Upgrade notes

- No migration and no new configuration. Restart the server to load the fix.

## [0.9.1] — 2026-09-28

A follow-up to 0.9.0 that closes what its reviews left open: the manage screen says when it lost
the server, images from other sites wait for a tap, failed requests read as sentences, every phone
control is big enough for a finger, and an autonomous wiki compile no longer races a decision made
on the web.

### Added

- **The manage screen says when it stopped following the server.** Its lists and counts come from
  the live stream, so a dropped stream now puts a notice at the top of every section with a retry,
  a browser gone offline says that instead, and the crew is read again once the stream is back.
- **An image from another site loads only when asked.** A reply or wiki page that links one shows
  a button naming the host in its place, so opening a conversation no longer tells a third party
  it was read.

### Fixed

- Every control on a phone has a touch area of at least 40px.
- A failed request is put in words (no network, a server error, gone, refused) instead of the
  server's validation dump or the browser's own error.
- A reconnect looks for a newer build only when no look since the drop has reached the server.
- A phone's activity strip stays up when a retry finds the conversation never ran, so the focus
  handed to its line does not vanish with it.
- Exporting a conversation closes raw HTML a reply was cut off in, so it cannot swallow the turns
  after it.
- An expired request still open on the server is read less often the longer the server's sweep
  keeps it.
- The restart reason for a schedule reads right for a removed schedule too, and each side keeps
  one copy of it.
- The approval history is read again when a decided request's run goes on to wait on its next
  tool, not only when a run settles.
- An autonomous agent's wiki compile writes under the same one-decision-at-a-time rule as the web,
  and leaves alone a proposal someone decided first; it and the memory rewrite wait for that rule
  off the event loop, so a decision still writing no longer stalls the server.

### Upgrade notes

- No migration and no new configuration. Restart the server to serve the new bundle; an open
  page offers the reload itself.

## [0.9.0] — 2026-09-28

This release is about acting where the person already is. A waiting request is approved, denied
or answered from the manage screen's Duyệt page, a spent cost cap is raised from the chat, the
agent editor saves schedules, and a tool call's arguments can be read whole before it is allowed.
The chat stops a turn honestly, follows runs other channels start in it and says when its live
stream is down; replies can be copied, shared and exported, and the conversation list groups by
day with unread dots and drafts. Run history, jobs, memory proposals and wiki pages read as
sentences, diffs and rendered pages instead of raw codes, an open page offers a reload once the
server runs a newer build, and a run paused for approval survives a server restart.

### Added

- **Raise or lift a conversation's cost cap from the chat.** The budget pill's card and both
  budget notices carry an editor for the cap: +$0.50 and +$1 steps, or a typed amount where 0
  lifts the cap. A spent budget now locks the composer and says so, since the server would halt
  the turn before it started; a raise unlocks it without a reload and puts the keyboard back on
  the composer. Only one notice offers the raise at a time, a halted turn's notice then says the
  new cap is saved and to send the message again, and a refused save says why.
- **Approve, deny or answer waiting requests from Duyệt (approvals).** Every request waiting on
  the person is listed above the approval history, with its approval bar or question card inline
  and a "còn m:ss" countdown, so it is decided without opening the chat. Deciding reads the resumed
  turn to its end; the row then leaves, or shows the next request when the turn pauses again, and
  the history below reads again whenever a request may have settled. At the deadline the row
  disables, says it expired and keeps reading the request until the scheduler's sweep closes it.
  The tab title carries the number of waiting requests as "(N)", the installed app's badge shows
  it where the browser allows, and the manage screen opens on Duyệt while one waits.
- **The agent editor saves schedules.** A row is one timing (a cron or an interval) and one action
  (a prompt or a command), and only the keys chosen are sent, so a new schedule is no longer
  refused for the derived `kind` and empty keys it carried. A cron, interval, prompt or Telegram
  chat id that cannot be sent is named beside its box and holds the save, a valid timing is read
  back in words, and a new row takes an id no kept row carries. Memory consolidation's cron is
  editable, and emptying it removes the key. The jobs list opens the editor on an agent's
  schedules, and the way back returns to that job's row. A save no longer breaks the form it came
  from, because the answer now carries `declared` (see Changed); against an older server that
  leaves it out, the editor reads the crew again instead.
- **A tool call's full arguments, before deciding it.** The one-line summary cuts every value at
  sixty characters. A closed "Xem đầy đủ" under the approval bar, each tool card and each approval
  history row now shows every argument whole: a command, file content, an edit's old and new text
  and any other value spanning lines as wrapped text, the rest as JSON. It is offered only when the
  summary hides something, and the chat's request card scrolls within 55% of the screen's height,
  so its buttons stay in view on a phone. The approval history also reads a question as what was
  asked, the options offered and the answer, and pages with "Xem thêm" from 50 to 200 to 500 rows.
- **Stop is honest, the thread stays fresh and a dropped stream says so.** Stop also cuts the
  stream of a decision or an answer, drops what the cut stream still delivers and says the turn
  stopped; a call left spinning when a turn ends, or when the live stream reports nothing running,
  reads as stopped. A run another channel such as Telegram starts in the open conversation,
  including one already going when this tab sends, shows its progress in the thread, which reloads
  once when that run ends or pauses; a message sent while the thread reloads is kept. The status
  line says when the live stream is connecting, lost or offline and offers a retry once the browser
  has given up, and runs that ended while the stream was down are caught up on when it returns.
- **Copy, share and export replies; see the files sent through Telegram.** Each agent reply has a
  copy button, and a share button where the platform has a share sheet, both taking its raw
  markdown; each fenced code block has a copy corner that takes only the code. Where the clipboard
  is missing or refuses, as on the LAN address over plain http, the text opens selected in a box to
  copy by hand, and the agent editor's prompt copy now falls back the same way. The conversation
  options export `<title>.md`: a heading per turn, times that name their time zone, and each
  message kept inside its own turn, down to the headings and code blocks in its lists and quotes.
  A file the person sent through Telegram shows in their bubble
  as a thumbnail or a named download chip served from the agent's files route, and a fence with no
  language renders as a code block.
- **The conversation list groups by day, marks unread and keeps drafts.** Rows fall under Hôm nay,
  Hôm qua and Cũ hơn on the viewer's calendar and say how long ago each changed, kept current while
  the tab idles. A row that changed since this browser last had it open gets an unread dot: a first
  visit counts everything as read, tabs merge what each has seen, and delegated conversations never
  get one. The status dot's tooltip is Vietnamese, and the dot pulses while a run is live. The
  composer keeps an unsent draft per conversation across switches and reloads; sending clears it
  and deleting the conversation drops it. Refused storage leaves both working for the page's life.
- **Slash commands from the composer.** A "/" at the start of the box lists the commands the
  agent's kits declare, narrowed by prefix and then by substring as the name is typed; arrows with
  Enter or Tab, or a tap, put "/name " in the box, and Esc closes the list. A "/" button beside Send
  opens it too. The list shows only while the composer has the focus, and an agent without
  commands shows neither.
- **Stored run history with filters.** An open conversation's activity loads its stored runs,
  delegated children included, under the live ones, so runs from before the page opened show, and
  each delegate sits under the turn that asked for it. The activity log loads its own history: the
  agent chip asks the server for that agent's runs, the status and source chips narrow what is
  loaded and are remembered by the browser, and "Xem thêm" reaches back 100, 200 and then 500
  runs. On a phone the chips fold behind one "Lọc" toggle. A history still loading, or one that
  failed to load, says so, with a retry.
- **Tokens, cache hits and time to first token.** A finished model step shows its route, the wait
  for its first token, its prompt tokens with the part the provider served from its cache, and
  whether it thought first. The costs page gains today and seven-day tiles on the viewer's calendar
  that flag unpriced calls, a cache column with its share per model, a cache-by-agent card counted
  over the same runs as the spend by agent, and a label on every card saying what it counts; it
  fits a phone at 390px.
- **Memory proposals are reviewed as diffs and exact facts.** A rewrite shows the lines it drops
  beside the ones it adds; a forget names the fact it removes and asks before approving; a fact
  that overwrites a saved one shows what it replaces, matched whatever case the agent wrote the name
  in, and saved facts that could not be read are said to be unknown rather than absent. A wiki
  compile shows one card per page, tagged new or updated. Both buttons disable while a decision is
  in flight, a proposal decided elsewhere says so in place and the list reloads, and a failed undo
  is reported.
- **Wiki pages read as pages.** A page opens as rendered markdown. Each [[link]] is slugged as the
  server slugs titles and opens its page at the title; a link to a page nobody has written is drawn
  as missing, and related pages are chips. "Đánh dấu ổn" marks a page fine with a status-only PUT.
  The vault header lists every page's open questions, each leading to the page that asked it, and
  today's note on the viewer's own date. Leaving an unsaved edit, or closing today's note over an
  unsaved line, asks first. Starting a compile or a consolidation shows a chip that follows its
  run, across a dropped stream too, then says how it ended and reloads what it may have changed.
- **Jobs read at a glance.** Common cron shapes (daily, weekdays, weekends, a set of weekdays,
  hourly, every N minutes or hours, a day of the month) and the `every` shorthand read in
  Vietnamese with the cron beside them. The next run counts down and the last run says how long
  ago, each followed by its clock time on the viewer's clock and kept current, also when the tab
  comes back; a paused or switched-off job says so where the next run goes. The last run shows its
  status and summary with a link to its replay, and the Lịch chạy (jobs) entry in the nav carries a
  red count, read out as a sentence, only while some job's last run failed.
- **A reload is offered when the server runs a newer build.** An open page, an installed app above
  all, compares the hashed entry script it runs with the one the server's index serves, on focus,
  when the tab comes back and after the live stream reconnects. When they differ, a floating
  "Có bản mới" bar offers a reload and can be put away until a later look still finds another
  build; a failed look shows nothing, and the dev server never shows it. Settings names the
  server's build and, once a look finds the server serving the page's own entry, the page's too,
  asking again each time it opens.
- **Why a run stopped reads as a sentence.** The server ends some runs with a code: `budget` or
  `max_steps` on a halt, `interrupted` on a turn nobody kept reading. The timeline and the
  attention center read each as a sentence, only under the status that writes it, so a reply that
  happens to be the word "budget" still reads as the reply.

### Changed

- **Duyệt and Hoạt động split what needs the person.** Duyệt's badge counts only the requests
  waiting on a decision. Hoạt động (activity) counts the failures and halts until each is marked
  "Đã xem", which the browser remembers, and its live count leaves out runs that only wait. Each
  page points to the other when that one has something for the person.
- **Saving an agent answers with the agent as the crew list shows it.** `POST /api/agents` and
  `PATCH /api/agents/{id}` return `profile` in the shape of a `GET /api/agents` entry: it gains
  `declared`, `editable`, `tools` and `skills`, and its `delegates` is who the agent can reach,
  with what its file names under `declared.delegates`.
- **A profile edit's new or changed schedules must be ones the clock can run.** The edit routes
  answer 422 when a schedule the edit adds or changes has a cron or interval the scheduler cannot
  read, or shares its id with another schedule, the consolidation job's included; before, the
  second job on an id silently replaced the first. Rows the agent already runs with are not checked
  again, so a hand-written profile holding such a row still takes unrelated edits, and boot still
  takes a file as it is.
- **`/api/stats` totals each agent's prompt cache.** `cache_by_agent` gives each agent's
  `prompt_tokens` and `cached_tokens` over the same runs as `by_agent`, from the calls that reported
  both, and `unknown_cache_calls` counts the calls that reported prompt tokens but no cache figure.
  The costs page's cache card reads them instead of fetching the 500 newest runs itself.
- **A pending request read back says why it paused.** `pending_approval` in
  `GET /api/conversations/{id}` carries `reason`, the line naming the ask pattern that stopped a
  shell command, worked out again from the stored call and the agent's ask list as for the live
  event; it is empty when no ask pattern played a part. The chat and the Duyệt row now show it for
  a run that paused while nobody was watching.
- **A memory proposal decision answers by what went wrong.** `POST /api/memory/proposals/{id}`
  answers 409 "proposal already decided" only for a proposal no longer pending,
  404 "proposal not found" for an unknown id, and 404 "agent not found" for a pending proposal
  whose agent has left the crew, which used to be a 409 although the proposal can still be
  rejected. Decisions are taken one at a time, so of two sent together the second gets the 409.

### Fixed

- **A run paused for approval survives a server restart.** Deciding its request after a restart
  continues that same run instead of opening a second one beside it, while the old paused row
  stayed waiting for good and every screen that counts runs kept counting it. A paused run nothing
  can continue any more, because its request was settled while no process held it or its
  conversation was deleted, is closed as interrupted, and a tool step resumed after a reboot never
  reports a negative duration.
- **Deleting a conversation paused on an approval ends its run at once.** Its request goes with it,
  so `DELETE /api/conversations/{id}` closes that run as interrupted instead of leaving it waiting.
  Naming a new conversation waits for its first turn to end, and one deleted or renamed by hand
  meanwhile is no longer named by a paid model call; a delegating agent waiting on a deleted child
  reads that the person deleted it, instead of a bare "KeyError".
- **The agent editor's pinned bar sits flush against the top of the page.** It stopped at the
  page's top padding, 32px down on a wide screen and 16px on a phone, and the form scrolled past
  visibly in the strip above it.
- **A run waiting for approval reads as waiting, not running.** The sidebar's status dot, the
  chat's manage button, the status line, the master's card and the crew page each took a paused
  run for a busy one, so the one state in which the person has to act read as the agent working.
  When a conversation holds two open runs, the one waiting on the person sets its dot.
- **A question that pauses while the page is open reads as a question.** The page's live copy of
  the run called it a permission request named ask_user until the list was read again; it now says
  the agent is asking, as the server does.
- **A decision someone already took elsewhere reads as handled.** In the chat, a decide or answer
  that meets a 409, because another tab, Telegram or the expiry sweep settled the request first,
  reads the conversation again and says the request was handled, not that the agent is busy, and
  no longer marks the resumed call as stopped. The note stays when the thread is read again for the
  run that decision resumed or for a live stream that reconnects; a new turn, a new request or
  opening another conversation clears it.
- **A slow load of the conversation just left no longer lands on the one opened.** Its messages,
  approval bar and spend showed under the other conversation's heading; each opening now takes only
  the loads, refused decisions and notes made for it.
- **A memory proposal is decided once.** An approval arriving after the proposal was decided, from
  a stale tab or a second click, wrote the memory before learning it was no longer pending, so a
  rejected fact was written or an agent memory line appended twice, and an approval and a rejection
  sent together from two devices could both find it pending. The status is now checked before
  anything is written, and one lock holds the check, the write and the resolve together.
- **An agent's runs are no longer crowded out by a busier agent's.** `GET /api/activity/runs` with
  `agent_id` cut the whole crew's newest runs to `limit` before narrowing, so a quiet agent showed
  few runs or none; the narrowing now happens in the query, and `limit` counts that agent's runs.
- **Background bookkeeping no longer dates a conversation as new.** The recap written when the
  next conversation opens, and the model's title with its cost, moved `updated_at`, so the old
  thread jumped above the new one; they now leave it alone, and every other write still moves it.
- **The agent editor shows the server's restart reasons as the sentences they are**, after the
  saved note, instead of setting each inside a sentence of its own as if it named a changed key.
- **On a phone, the current manage section's pill stays in view** when the badge counts arrive
  after the first paint and widen the row. A row the person has scrolled the pill out of stays
  where they left it, so a count arriving mid-swipe no longer slides another section under their
  finger.
- **Runs that started in the same second are listed the same way everywhere.** Start times are
  whole seconds, and each list put such runs in whatever order its sort happened to leave them,
  or in the order the store last saved them: the chat's activity line could name one run as the
  last while the card under it showed another, the chat's cards and line moved on to another run
  once the stored history arrived, and a request just decided on Duyệt dropped below another
  request from the same second while its turn resumed, sliding that request's buttons under the
  pointer. Of runs that share a second, one still going now comes first, then the one that ended
  later; the rest keep the order the page heard of them, newest first, and a decided request
  stays where it was listed.

### Upgrade notes

- **No migration needed.** The SQLite schema, `config.yaml` and `agent.yaml` keep their shape, and
  no API route is added or removed; upgrading is pulling the new code and restarting the process.
  The web bundle is committed, so running the server needs no npm step.
- **The first start closes the paused runs nothing can continue.** Rows an earlier version left on
  `awaiting_approval` across restarts are closed as failed with the summary `interrupted`, except
  the newest paused run of each conversation whose request still waits, which a decision now
  continues.
- **Reload pages opened before the upgrade once.** A page or installed app from an earlier version
  cannot notice a new build; after one reload it offers the next one itself.
- **Check clients other than the bundled web against Changed.** A saved agent's `delegates` now
  lists who it can reach, a proposal decision answers 404 "agent not found" where it answered 409,
  and a profile edit can be refused with 422 over a schedule it adds or changes.
- **Contributors running e2e from two checkouts** give each its own port with
  `E2E_PORT=<port> npm run e2e`; on one port the second run reuses the first one's dev server and
  quietly tests the other checkout's code. Vitest and Playwright both run in the Asia/Ho_Chi_Minh
  time zone, so a test about days is written in that zone and sets no `TZ` of its own.

## [0.8.0] — 2026-09-26

This release is about the interface. The web UI is redesigned end to end on one scale of tokens,
with bundled Inter, line icons and a brand mark that is also the installed app's icon; it installs
as an app, and on a phone the conversation takes the whole screen with the list in a modal drawer.
It also makes the activity view tell the truth about a run: a run that just started or resumed
after an approval no longer crashes the page, a route that fails over leaves no model step open,
and a run stopped for approval says it waits for the person.

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
  platform. A brand mark heads the sidebar and the welcome screen, and each agent has an initial on
  a tile of its own stable hue in the sidebar's master card, the conversation header, the thread,
  delegate cards, the crew and jobs lists and the agent editor. Each reply in the thread is headed
  by the agent's name and avatar instead of "Agent", and your own messages no longer carry a
  visible "Bạn" label. Dark mode follows the operating system on every surface.
  Text on the primary button, filled badges, channel tags and sunken surfaces holds 4.5:1 in both
  modes, which is why the button and badges keep the brand blue as their fill in dark mode too;
  checkboxes, switches and fields keep a visible focus ring. A browser test measures both. Most
  fields, the composer and the memory editor included, stay at 16px so an iPhone does not zoom
  into them.
- **On a phone the conversation takes the whole screen.** The conversation list slides in over it
  from a menu button and closes on Escape, on a tap outside or once a conversation is picked,
  handing focus back to the button. While open it is modal: the chat under it is inert, and
  Escape closes the list without also collapsing the activity strip beneath. ⌘K opens it at the
  search box, and the menu button's name says how many runs are waiting, as its dot does. The
  manage screen's sections become a row of pills that brings the current one into view. On a
  touch screen, where nothing can hover, every conversation row shows its delete button.
- **Empty and quiet states say where the person is.** Empty activity, approvals, costs and jobs
  sections show their own icon; the "Cần bạn xử lý" card stays grey until something waits; an
  expired approval is grey rather than amber, which is kept for a refusal and for a request still
  waiting.
- **The agent editor's pinned bar now shows the agent's avatar** next to its name. The unsaved
  count and the save controls sit together as one group, with Save styled as the primary button,
  and the group moves onto a second line on a phone. The tools matrix is a card with two-line
  descriptions and a coloured legend.
- **A section that fails to render no longer takes the manage screen with it.** Each page has its
  own error boundary, so the navigation stays and moving to another page leaves the failure
  behind; the failure itself is a card with the error and a reload button. The chat screen has a
  boundary too, so a crash outside its thread and activity column shows that card instead of a
  blank page.
- **The composer names the agent it writes to and grows with the message.** Once the agent is
  known, the empty box reads "Nhắn cho <agent>…" and no longer spells out the Enter / Shift+Enter
  keys. It starts at one line and grows to about ten lines before it scrolls. Send and Stop are
  round icon buttons that keep their names for screen readers. An input method commits a word
  with Enter instead of sending half of it, including the Enter that Safari delivers just after
  the composition has ended.

### Fixed

- **A route that fails over no longer leaves a model step open on a run that recovered.** The
  step the request opened stayed ahead of the fallback, so a finished run showed a model that
  never answered. The failed attempt's wait is now the fallback's duration, the model step times
  the next route, and when every route fails no model step is left waiting. A run stored before
  this shows such a step as "Mô hình", where 0.7.0 labelled it "?". The live page keeps the same
  order.
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
  was running; it now reads "Đang chờ bạn duyệt" and drops the shimmer. Its card no longer wears
  the "Đang chạy" pill beside its own "chờ duyệt" either.

### Upgrade notes

No migration needed. The SQLite schema, `config.yaml` and `agent.yaml` keep their shape, and no API
route changes: upgrading is pulling the new code and restarting the process, which picks up the
run-step fixes. Runs stored before the upgrade keep the steps they were recorded with (see Fixed).
The web bundle is committed, so running the server needs no npm step. A contributor who rebuilds it
runs `npm ci` in `web/` first, because the bundled Inter font comes from the new
`@fontsource-variable/inter` dependency.

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

[0.11.1]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.11.1
[0.11.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.11.0
[0.10.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.10.0
[0.9.2]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.9.2
[0.9.1]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.9.1
[0.9.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.9.0
[0.8.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.8.0
[0.7.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.7.0
[0.6.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.6.0
[0.5.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.5.0
[0.4.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.4.0
[0.3.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.3.0
[0.2.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.2.0
[0.1.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.1.0
