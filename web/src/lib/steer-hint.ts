// What sending this text while the conversation is busy will do to it, so the composer's
// send button can say "Chèn" instead of "Xếp hàng" without asking the server.
//
// The server alone decides which kind a message becomes (`steer_text`, `find_command` in
// `my_agent_crew/agents/kit_commands.py`); this only guesses the label. A guess that lags
// behind a not-yet-loaded command list only shows the wrong word on the button, never the
// wrong queue behaviour — the server still applies its own rule to the text that is sent.
import type { CommandInfo } from "../api/types";

const STEER_COMMAND = "steer";

// A path like "/tmp/x" or "/Users/a/b" has a "/" right after the name, which this regex
// requires whitespace or the end of the string instead — the same shape as the server's
// `_INVOCATION`, so a path reads as ordinary text here exactly as it does there.
const INVOCATION = /^\/([\w:.-]+)(?:@\w+)?(?:\s|$)/;

export function steerHint(text: string, commands: CommandInfo[]): "steer" | "queue" {
  const match = INVOCATION.exec(text.trim());
  if (match === null) return "queue";
  const name = match[1];
  if (name === STEER_COMMAND) return "steer";
  return commands.some((c) => c.name === name) ? "steer" : "queue";
}
