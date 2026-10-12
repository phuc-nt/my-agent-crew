import { newestFirst } from "../lib/run-order";
import type { RunInfo } from "../api/types";

const DELEGATE_SOURCE = "delegate";

/** A delegated run names the conversation that handed out the work: `delegate:<id>`. */
export function parentConversationId(run: RunInfo): string | null {
  return run.source.startsWith(`${DELEGATE_SOURCE}:`)
    ? run.source.slice(DELEGATE_SOURCE.length + 1) || null
    : null;
}

export type RunGroup = { run: RunInfo; children: RunInfo[] };

function push<K, V>(map: Map<K, V[]>, key: K, value: V): void {
  const known = map.get(key);
  if (known) known.push(value);
  else map.set(key, [value]);
}

/**
 * The turn that asked for a delegated run, among its parent conversation's turns.
 *
 * The source names only the conversation, and a conversation's history holds many turns.
 * A conversation runs one turn at a time and the delegate tool starts its child from inside
 * one, so the turn that asked is the one going when the child started: begun by then, and
 * not yet over. Timestamps are whole seconds, so both ends count; of two turns that touch
 * the same second, the later one is the one still going.
 */
function askingTurn(child: RunInfo, turns: RunInfo[]): RunInfo | null {
  const start = Date.parse(child.started_at);
  let asking: RunInfo | null = null;
  for (const turn of turns) {
    const began = Date.parse(turn.started_at);
    const ended = turn.finished_at === null ? Infinity : Date.parse(turn.finished_at);
    const going = began <= start && start <= ended;
    if (going && (asking === null || began > Date.parse(asking.started_at))) asking = turn;
  }
  return asking;
}

/**
 * Runs for the rail, with delegated runs tucked under the run that asked for them.
 *
 * Nesting is one level deep because delegation is: a child cannot delegate on, so a
 * child never has children of its own. A child whose parent is not in view stands on
 * its own rather than disappearing.
 */
export function runGroups(runs: RunInfo[]): RunGroup[] {
  const turns = new Map<string, RunInfo[]>();
  for (const run of runs) {
    // A run with no conversation (a scheduled job) can never be delegated to.
    if (run.conversation_id !== null && parentConversationId(run) === null) {
      push(turns, run.conversation_id, run);
    }
  }
  const children = new Map<string, RunInfo[]>();
  const orphans = new Set<RunInfo>();
  for (const run of runs) {
    const parent = parentConversationId(run);
    if (parent === null) continue;
    const asking = askingTurn(run, turns.get(parent) ?? []);
    if (asking === null) orphans.add(run);
    else push(children, asking.id, run);
  }
  // Kept in the order given, a child standing alone included, for runs that tie.
  return runs
    .filter((run) => parentConversationId(run) === null || orphans.has(run))
    .map((run) => ({ run, children: children.get(run.id) ?? [] }))
    .sort((a, b) => newestFirst(a.run, b.run));
}
