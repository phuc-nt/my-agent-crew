#!/bin/bash
# Runs `gws` on behalf of an agent and turns its failures into something a model can act on.
#
# Two jobs, and only two:
#   1. Refuse the commands that would break the shared credentials for everyone.
#   2. Turn a non-zero exit into one JSON line saying what to do, because a model that
#      only sees "exit 1" retries the same command until it runs out of steps.
#
# It deliberately does not parse gws output. A read command's stdout is passed through
# byte for byte so the callers that pipe it into jq keep working.

set -uo pipefail

LOG_DIR="$HOME/.my-agent-crew/logs"
LOG_FILE="$LOG_DIR/gws-run.log"

# Every `+` helper this wrapper has been taught about. A helper outside both lists is one
# a newer gws added, so it gets logged for review rather than passing unnoticed — the ask
# patterns that hold writes back are written against names, and a name nobody knows about
# is exactly the one that would slip through them.
KNOWN_WRITES="send reply reply-all insert append upload write"
KNOWN_READS="agenda triage"

json_fail() {
  # $1 status, $2 fix. Both are ours, not user input, so plain interpolation is safe.
  #
  # This goes to stderr, not stdout. A read command's stdout is piped into jq by the job
  # scripts, and appending a JSON object to a table of calendar events would turn a clean
  # failure into a parse error somewhere else.
  printf '{"ok": false, "status": %s, "fix": "%s"}\n' "$1" "$2" >&2
}

note() {
  mkdir -p "$LOG_DIR" 2>/dev/null
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >>"$LOG_FILE" 2>/dev/null
}

# --- Refusals ---------------------------------------------------------------------
# `gws auth login` opens a browser. Under a job there is no one to click it, so the
# process hangs until the run's timeout kills it and the agent learns nothing.
if [ "${1:-}" = "auth" ] && [ "${2:-}" = "login" ]; then
  note "REFUSED auth login"
  json_fail 2 "khong tu login. Chay \`gws auth status\` o terminal roi bao nguoi dung re-auth."
  exit 2
fi

# Pointing the CLI at another credentials file overrides the working one for every later
# call in the same environment, and the symptom is a 401 somewhere else entirely.
for arg in "$@"; do
  case "$arg" in
    GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=* | *--credentials-file*)
      note "REFUSED credentials override: $arg"
      json_fail 2 "khong doi credentials. Dung auth dang chay; loi 401 thi bao nguoi dung."
      exit 2
      ;;
  esac
done

# --- Unknown write helpers get recorded --------------------------------------------
for arg in "$@"; do
  case "$arg" in
    +*)
      helper="${arg#+}"
      case " $KNOWN_WRITES $KNOWN_READS " in
        *" $helper "*) : ;;
        *) note "helper la vi chua biet, ra soat khi nang gws: $arg" ;;
      esac
      ;;
  esac
done

# --- Run ----------------------------------------------------------------------------
gws "$@"
code=$?
[ $code -eq 0 ] && exit 0

note "exit $code: $*"
if [ $code -eq 401 ]; then
  json_fail 401 "token het han. Bao nguoi dung chay \`gws auth status\` o terminal; khong tu login."
else
  json_fail "$code" "gws that bai. Chay \`gws <service> --help\` xem cu phap truoc khi thu lai."
fi
exit $code
