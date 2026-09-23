#!/bin/bash
# Writing to Goodreads means driving the site, because the API closed in 2020. That
# needs Playwright and a logged-in browser profile, neither of which belongs in the
# server's own environment — so both live here, owned by this skill alone.
#
# Every failure leaves as one JSON line on stderr carrying the command that fixes it.
# stdout stays clean so a caller can pipe it into jq.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$(cd "$HERE/.." && pwd)"
VENV="$BUNDLE/.venv"
PYTHON="$VENV/bin/python3"
WRITER="$HERE/goodreads-writer.py"
PROFILE="$BUNDLE/.browser-data"

json_fail() {
  printf '{"ok": false, "error": "%s", "fix": "%s"}\n' "$1" "$2" >&2
  exit 1
}

if [ $# -eq 0 ]; then
  json_fail "no command" "one of: login, rate <book_id> <1-5>, shelf <book_id> <shelf>, progress <book_id> <percent>, review <book_id> <text>"
fi

if [ ! -x "$PYTHON" ]; then
  json_fail "no Playwright environment for this skill" \
    "python3 -m venv $VENV && $VENV/bin/pip install playwright && $VENV/bin/playwright install chromium"
fi

if ! "$PYTHON" -c "import playwright" 2>/dev/null; then
  json_fail "the environment exists but Playwright is not installed" \
    "$VENV/bin/pip install playwright && $VENV/bin/playwright install chromium"
fi

# `login` opens a real window and waits for a person to type a password. Under a
# scheduled job that window has nobody in front of it, so the run would sit there until
# it timed out. Refusing here is cheaper than explaining the hang later.
if [ "$1" = "login" ] && [ ! -t 0 ]; then
  json_fail "login needs a person at a terminal" \
    "run $0 login yourself in a terminal, then retry"
fi

# The profile holds a live session cookie. Nobody but its owner should be able to read it.
[ -d "$PROFILE" ] && chmod 700 "$PROFILE" 2>/dev/null

exec "$PYTHON" "$WRITER" "$@"
