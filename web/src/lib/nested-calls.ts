// What a script did besides print: the calls it made on its own, and its two measures.
//
// The same three things reach the web by three routes — a run's step, the events of a turn
// and the result a conversation stores — and both the run card and the chat card show them.
// The rules they share are here, twins of `activity/tool_steps.py` on the server.
import type { NestedToolCall } from "../api/types";
import { vi } from "../i18n/vi";

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
 *  hearing and false on the other as easily as not, and a call taken for two is paid twice.
 *
 *  What another agent spent on a task handed to it is left out for the same reason. It is
 *  there only above zero, so a hearing without it and one with it are as easily one call;
 *  it is never this run's to pay, so comparing it guards no total; and the figure already
 *  stands in the answer compared here, which tells two tasks of different cost apart. */
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

/** A script may ask a model itself, to sort a text or to shorten one. Such a call is listed
 *  with the script's other calls under a name of this family, which is the name of no tool. */
const MODEL_CALL = "llm.";

/**
 * The words a model call a script made is listed under, or null for a call to a tool, which
 * goes by its own name. Asked of the name alone: nobody looks a nested call up among the
 * tools, so one that is no tool is never found missing. A model call the web has no word
 * for yet is still said to be one, with what was asked of it as the server named it.
 */
export function modelCallLabel(name: string): string | null {
  if (!name.startsWith(MODEL_CALL)) return null;
  return vi.scriptModelCall[name] ?? vi.scriptModelCallOther(name.slice(MODEL_CALL.length));
}

/**
 * What another agent spent on a task a script handed it, in words, or null when the call
 * says nothing of it. That money is the other conversation's: it is shown on the call and
 * added to no total of this run. The figure is written to four places, as the card of a
 * task handed off directly writes it. Only a real amount above zero counts, which is all
 * the server sends; a call heard live is taken as it came, so it is read with care here.
 */
export function childSpentText(call: NestedToolCall): string | null {
  const spent = call.child_spent_usd;
  if (typeof spent !== "number" || !Number.isFinite(spent) || spent <= 0) return null;
  return vi.scriptCallChildSpent(`$${spent.toFixed(4)}`);
}

const DELEGATE = "delegate";
const CHILD_HEADER = /^conversation=(\S+) status=\S+ spent=\$\S+ steps=\d+(?: |$)/;

/**
 * The conversation a task handed off by a script ran in, or null when the call opened none.
 * A script's call keeps only the start of the answer, on one line, so the reader of a whole
 * answer (`delegate-result.ts`) finds no header in it. The id still leads that line, and a
 * call that failed before it opened a conversation leads with its error instead.
 */
export function childConversationId(call: NestedToolCall): string | null {
  return call.name === DELEGATE ? (CHILD_HEADER.exec(call.output)?.[1] ?? null) : null;
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
    (call.gated === undefined || typeof call.gated === "boolean") &&
    // Kept only on a task handed to another agent that spent something.
    (call.child_spent_usd === undefined || typeof call.child_spent_usd === "number")
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
