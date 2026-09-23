#!/usr/bin/env bash
# Every gate CI runs, in CI's order, in one command.
#
# The gates live in .github/workflows/ci.yml, and keeping a second list of them in a human's
# head is how one gets skipped: `ruff format --check` went unrun for a whole milestone because
# `ruff check` passing felt like the formatting was fine. Run this before pushing and there is
# no list to remember.
#
# Usage:  ./scripts/gates.sh
# Stops at the first failing gate and names it.

set -euo pipefail

cd "$(dirname "$0")/.."
root=$(pwd)
gate=0

# Run one gate, and on failure say which one by name — `set -e` alone would exit silently and
# leave the reader scrolling back through the output to find where it stopped.
run() {
  local name=$1
  shift
  gate=$((gate + 1))
  printf '\n\033[1m[%d/7] %s\033[0m\n' "$gate" "$name"
  if ! "$@"; then
    printf '\n\033[31m✗ Cổng "%s" đỏ. Sửa rồi chạy lại.\033[0m\n' "$name" >&2
    exit 1
  fi
}

run "ruff check"            uv run ruff check .
run "ruff format --check"   uv run ruff format --check .
run "pytest"                uv run pytest -q

cd "$root/web"
# `npm ci` is CI's way of getting a clean tree from the lockfile; here we only want the
# dependencies present, and reinstalling from scratch every run would cost more than the gates.
[ -d node_modules ] || npm install

run "typecheck"             npm run typecheck
run "vitest"                npm test
# Playwright needs its browser once per machine; CI installs it every run because CI is new
# every run. Locally, install it only when it is missing.
npx playwright install chromium >/dev/null 2>&1 || true
run "playwright e2e"        npm run e2e
run "bundle"                npm run bundle

cd "$root"
# The bundle is committed so `python -m my_agent_crew` works from a clone. Rebuilding it above
# and finding a diff here means the committed copy is stale — CI fails on exactly this.
printf '\n\033[1m[bundle đã commit khớp source?]\033[0m\n'
if ! git diff --exit-code --stat -- my_agent_crew/server/static; then
  printf '\n\033[31m✗ my_agent_crew/server/static lệch so với web/src. Commit bundle vừa dựng lại.\033[0m\n' >&2
  exit 1
fi

printf '\n\033[32m✓ Cả tám cổng xanh. Đẩy được.\033[0m\n'
