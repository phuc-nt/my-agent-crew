// What a script did besides print: the calls it made on its own, and its two measures.
//
// The same three things reach the web by three routes — a run's step, the events of a turn
// and the result a conversation stores — and both the run card and the chat card show them.
// The rules they share are here, twins of `activity/tool_steps.py` on the server.
import type { NestedToolCall } from "../api/types";

/** Each part is there only when it is known, as on a run's step. */
export interface ScriptWork {
  calls?: NestedToolCall[];
  received_chars?: number;
  printed_chars?: number;
}

/** A script's work as a result carries it, on the wire or stored: lists that may be empty
 *  and measures that are null for a tool that is no script. */
interface CarriedWork {
  calls?: NestedToolCall[];
  received_chars?: number | null;
  printed_chars?: number | null;
}

/** One call heard twice says the same thing both times, whichever way it came. Whether it
 *  went through the approval gate is left out of the comparison: it is absent on one
 *  hearing and false on the other as easily as not, and a call taken for two is paid twice. */
function sameCall(a: NestedToolCall, b: NestedToolCall): boolean {
  return (
    a.name === b.name &&
    a.ok === b.ok &&
    a.output === b.output &&
    a.ms === b.ms &&
    a.cost_usd === b.cost_usd &&
    a.metered === b.metered &&
    JSON.stringify(a.arguments) === JSON.stringify(b.arguments)
  );
}

/**
 * The calls of a script's result that were not listed while it ran. Those were counted as
 * they ended, and the result names them again, in the order the script made them rather
 * than the order they ended in. A script may make the very same call twice, so each one
 * listed answers for one of the result's and no more.
 */
export function notYetListed(listed: NestedToolCall[], calls: NestedToolCall[]): NestedToolCall[] {
  const left = [...calls];
  for (const seen of listed) {
    const at = left.findIndex((call) => sameCall(call, seen));
    if (at >= 0) left.splice(at, 1);
  }
  return left;
}

/**
 * A script's calls with one more heard, the `index`-th the script made. `added` says
 * whether it is new here: one heard again, on a stream that joined late or beside a
 * snapshot that already had it, takes the place it has, so whoever adds up money adds it once.
 */
export function withNested(
  calls: NestedToolCall[] | undefined,
  index: number,
  call: NestedToolCall,
): { calls: NestedToolCall[]; added: boolean } {
  const next = [...(calls ?? [])];
  if (index < next.length) {
    next[index] = call;
    return { calls: next, added: false };
  }
  next.push(call);
  return { calls: next, added: true };
}

/** What a result says of a script's work, keeping only what it knows: no empty list, and no
 *  measure for a tool that is no script or a server that did not count yet. */
export function workOf(result: CarriedWork): ScriptWork {
  const work: ScriptWork = {};
  if (result.calls && result.calls.length > 0) work.calls = result.calls;
  if (typeof result.received_chars === "number") work.received_chars = result.received_chars;
  if (typeof result.printed_chars === "number") work.printed_chars = result.printed_chars;
  return work;
}

function isCall(value: unknown): value is NestedToolCall {
  if (typeof value !== "object" || value === null) return false;
  const call = value as Record<string, unknown>;
  return (
    typeof call.name === "string" &&
    typeof call.arguments === "object" &&
    call.arguments !== null &&
    typeof call.ok === "boolean" &&
    typeof call.output === "string" &&
    typeof call.ms === "number" &&
    (call.cost_usd === null || typeof call.cost_usd === "number") &&
    typeof call.metered === "boolean" &&
    // Kept only by a result stored since scripts could make gated calls.
    (call.gated === undefined || typeof call.gated === "boolean")
  );
}

/**
 * What the stored result of a script kept beside its output (`StoredMessage.context`), so
 * the chat card can list the calls after a reload, when the run that showed them may be gone.
 *
 * Read with care: the same field holds a person's canvas note on another kind of message,
 * and a row that is not what is expected must cost the card its list, not the thread its
 * render. Calls that are not all whole are not listed in part.
 */
export function storedWork(context: string | undefined): ScriptWork {
  if (!context) return {};
  let kept: unknown;
  try {
    kept = JSON.parse(context);
  } catch {
    return {};
  }
  if (typeof kept !== "object" || kept === null) return {};
  const { calls, received_chars, printed_chars } = kept as Record<string, unknown>;
  return workOf({
    calls: Array.isArray(calls) && calls.every(isCall) ? calls : undefined,
    received_chars: typeof received_chars === "number" ? received_chars : null,
    printed_chars: typeof printed_chars === "number" ? printed_chars : null,
  });
}
