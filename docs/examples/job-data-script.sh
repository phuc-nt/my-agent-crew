#!/bin/zsh
# Shape for the data script behind a scheduled prompt job: gather everything the job
# needs, print one JSON object, exit 0.
#
# Why one script instead of letting the model run the commands: a job that drives five
# CLIs itself spends most of its step budget on syntax and can hit max_steps before it
# writes an answer. One `shell_run` step leaves the whole budget for the thinking.
#
# Copy this next to the agent's home (e.g. ~/.my-agent-crew/scripts/) and fill in the real
# commands there. Account ids, folder ids and paths belong in that copy, never in the repo.
#
# In the schedule, the prompt is then one line:
#   prompt: "Chạy ~/.my-agent-crew/scripts/<tên>.sh rồi viết bản tin từ JSON trả về."

set -uo pipefail   # no `-e`: one dead source must not lose the other four

# Each section records its own error instead of aborting, so a stale token on one service
# still leaves the job with the rest of the data and a reason to tell the user.
section() {
  local name="$1"; shift
  local out
  if out="$("$@" 2>&1)"; then
    print -r -- "{\"ok\":true,\"data\":$(print -r -- "$out" | jq -Rs .)}"
  else
    print -r -- "{\"ok\":false,\"error\":$(print -r -- "$out" | jq -Rs .)}"
  fi
}

calendar=$(section calendar example-cli calendar today)
mail=$(section mail example-cli mail unread --limit 20)
tasks=$(section tasks example-cli tasks list)

jq -n \
  --argjson calendar "$calendar" \
  --argjson mail "$mail" \
  --argjson tasks "$tasks" \
  --arg date "$(date +%F)" \
  '{date: $date, calendar: $calendar, mail: $mail, tasks: $tasks}'
