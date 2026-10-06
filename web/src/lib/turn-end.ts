import type { AgentEvent } from "../api/types";

/**
 * Whether `event` is the last a turn says on a stream that reads it: the turn finished, gave
 * up, broke, or stopped to wait on the person. A stream that closes without one says nothing
 * of its turn — the server was told to go, or the turn was stopped elsewhere.
 *
 * A `watching` that finds nothing going is not one. It stands in for events the reader was
 * not given, and a server on its way out says it of a turn the next server carries on.
 */
export function endsTurn(event: AgentEvent): boolean {
  return event.type === "done" || event.type === "halted" || event.type === "error" || event.type === "approval_required";
}
