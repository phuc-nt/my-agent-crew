import type { RunInfo } from "../api/types";
import { parentConversationId } from "./run-groups";

/**
 * The requests waiting in work a conversation handed out, at any depth.
 *
 * A delegated run names the conversation that asked for it in its `source`; a run that
 * resumed after a decision names the channel that decided instead, so the link from a
 * child up to its parent is read from any of the child's runs that still carries it.
 * `runs` is every run known to the page, `waiting` the ones paused on a person.
 */
export function waitingInDelegated(runs: RunInfo[], waiting: RunInfo[], conversationId: string): RunInfo[] {
  const parentOf = new Map<string, string>();
  for (const run of [...waiting, ...runs]) {
    const parent = parentConversationId(run);
    if (parent && run.conversation_id && !parentOf.has(run.conversation_id)) parentOf.set(run.conversation_id, parent);
  }
  const descends = (from: string) => {
    // A loop in the links is never written by the server; the walk stops on one anyway.
    const passed = new Set<string>();
    for (let at = parentOf.get(from); at !== undefined && !passed.has(at); at = parentOf.get(at)) {
      if (at === conversationId) return true;
      passed.add(at);
    }
    return false;
  };
  return waiting.filter(
    (run) =>
      run.status === "awaiting_approval" &&
      run.conversation_id !== null &&
      run.conversation_id !== conversationId &&
      descends(run.conversation_id),
  );
}
