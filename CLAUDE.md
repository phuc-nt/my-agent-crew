# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

One general-purpose agent (tool loop + skills) behind a FastAPI server that also serves the React
web UI. No teams, roles, routers or task graphs — those were the parts of my-crew that did not
earn their complexity. Read [docs/design.md](docs/design.md) before changing architecture.

## Rules

- **Tests track features.** Every behaviour change ships with its test in the same commit; never
  loosen an assertion to make a suite pass. [docs/testing.md](docs/testing.md) maps features to
  tests — update it when you add one.
- **English identifiers everywhere.** Vietnamese (or any user language) appears only in
  `my_agent_crew/texts.py` and `web/src/i18n/vi.ts`.
- **≤200 lines per source file**, enforced by `tests/test_file_size_budget.py`. Split by concern
  rather than raising the limit.
- **Secrets only from environment variables.** `config.yaml` is whitelisted non-secret keys; never
  read `.env*` files in code or tests, never commit them.
- **The web bundle is committed** (`my_agent_crew/server/static/`). After touching `web/src`, run
  `npm run bundle` and commit the result; CI fails on a stale bundle.
- **Approval is a product feature, not a setting.** Tools that change state declare
  `requires_approval`; hard denials (workspace escape, private network) live in code and cannot be
  toggled.
- Conventional commits, no attribution lines, no plan or phase identifiers in code or commits.

## Commands

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
cd web && npm run typecheck && npm test && npm run e2e && npm run bundle
MY_AGENT_ROUTES=fake:echo uv run python -m my_agent_crew   # local run without a model key
```
