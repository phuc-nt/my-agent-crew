# Testing

**Phiên bản**: 0.5.0 (+ chưa phát hành) · **Cập nhật**: 2026-09-24

Three tiers, one rule: **every feature ships with a test in the lowest tier that can see it.**
The test files themselves are the inventory; this page only says what each tier is for and
how to run it. Counts and file names are not kept here — run the commands.

| Tier | Runs with | What it can see |
|---|---|---|
| pytest (`tests/`) | `uv run pytest -q` | the loop, tools, store, providers, profiles, scheduler, channels, the HTTP API and its SSE streams — everything the server does, with the model replaced by `MY_AGENT_ROUTES=fake:echo` |
| vitest (`web/`) | `cd web && npm test` | parsers, reducers, the API client, single components, and the whole App against an in-memory fake server |
| Playwright (`web/e2e/`) | `cd web && npm run e2e` | a real browser on a real Vite dev server, `/api` answered by a mock in the test; used for flows that only break in a browser (SSE reconnect, layout at phone width, keyboard) |

Prefer the lowest tier: a rule of the loop belongs in pytest, a reducer in vitest, and
Playwright only for what the DOM alone can show. A behaviour that crosses tiers (an approval
pauses the loop *and* the bar appears) gets one test on each side of the boundary.

## Guard tests

A few tests protect the repo rather than a feature:

- a **file-size budget**: no source file over 200 lines, so modules stay readable in one screen;
- the **bundle** in `my_agent_crew/server/static` is present and served at `/`, with `/api/*`
  404s staying JSON;
- CI rebuilds the bundle and fails on `git diff --exit-code`, so a web change is never
  committed without its bundle.

## Running the gates

`./scripts/gates.sh` runs every CI gate in order and stops at the first red one; see
[code-standards.md](code-standards.md#4-cổng-phải-chạy-trước-khi-commit). The list of gates
is `.github/workflows/ci.yml`.

## Live smoke (manual)

`MY_AGENT_ROUTES=fake:echo` against a throwaway `MY_AGENT_HOME`, then through the UI or curl:
chat → `/tool workspace_list {"path":"."}` → `/tool workspace_write {...}` → approve → file exists
in `MY_AGENT_HOME/workspace`. With an agent profile that has a schedule: `POST /api/jobs/<agent>/<schedule>/run`
must produce a run on `/api/activity/runs` and a card in the rail. With at least one other
agent installed: `POST /api/inbound {"text": "Nhờ kongming …"}` must answer with the master's
summary and leave a child run whose `source` is `delegate:<conversation id>` on
`/api/activity/runs`. This is the check to repeat before tagging a release.
