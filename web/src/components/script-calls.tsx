import type { NestedToolCall } from "../api/types";
import { vi } from "../i18n/vi";
import { childConversationId, childSpentText, modelCallLabel, type ScriptWork } from "../lib/nested-calls";
import { formatUsd } from "./budget-indicator";
import { summarizeArguments } from "./tool-args-detail";

/** Opens the conversation a handed-off task ran in; absent means the way in is hidden. */
type OpenConversation = (conversationId: string) => void;

/**
 * What a call is listed under. A tool goes by its own name, set as the identifier it is. A
 * model the script asked itself goes by words: its name is no tool's, and set as code it
 * would read as one a person could go and look for.
 */
function CallName({ name }: { name: string }) {
  const label = modelCallLabel(name);
  if (label === null) return <code className="script-call-name">{name}</code>;
  return <span className="script-call-name">{label}</span>;
}

/**
 * What a task handed to another agent came to: what that agent spent on it, and the way
 * into the conversation it ran in, as the card of a task handed off directly offers both.
 * The spend is said in words here, since the line above it may carry what the script's
 * own calls paid and the two are different money.
 */
function ChildWork({ call, onOpenConversation }: { call: NestedToolCall; onOpenConversation?: OpenConversation }) {
  const spent = childSpentText(call);
  const child = onOpenConversation ? childConversationId(call) : null;
  if (spent === null && child === null) return null;
  return (
    <span className="script-call-line script-call-child">
      {spent !== null && <span data-testid="script-call-child-spent">{spent}</span>}
      {child !== null && (
        <button type="button" className="link-button" onClick={() => onOpenConversation?.(child)}>
          {vi.delegateOpenChild}
        </button>
      )}
    </span>
  );
}

/**
 * What a script called on its own, listed under the script's step.
 *
 * The model read none of this — only what the script printed — and no call here has a
 * step on the rail. So this list is the one place a person can see which tools a script
 * actually reached, with what, and what came back.
 *
 * Folded until asked for: a script may make two dozen calls, and opened they would push
 * the rest of the run off the screen. The line that stays says how many there were and
 * how many failed, which is what decides whether the list is worth opening.
 */
export function ScriptCalls({ calls, onOpenConversation }: { calls: NestedToolCall[]; onOpenConversation?: OpenConversation }) {
  const failed = calls.filter((call) => !call.ok).length;
  return (
    <details className="script-calls" data-testid="script-calls">
      <summary>{vi.scriptCalls(calls.length, failed)}</summary>
      <ol>
        {calls.map((call, index) => (
          // A script may make the very same call twice; only its place tells the two apart.
          <li key={index} className="script-call" data-testid="script-call" data-ok={call.ok}>
            <span className={call.gated ? "script-call-head gated" : "script-call-head"}>
              <CallName name={call.name} />
              {!call.ok && <span className="step-state failed">{vi.toolFailed}</span>}
              {/* It changed something and the approval gate let it through. Said in words
                  and on the call itself: the step of the script shows one state for all
                  of its calls, and cannot say which of them wrote. */}
              {call.gated && (
                <span className="step-state gated" data-testid="script-call-gated">
                  {vi.scriptCallGated}
                </span>
              )}
              <span className="step-time tabular">{vi.stepDuration(call.ms)}</span>
            </span>
            <span className="script-call-line">{summarizeArguments(call.arguments) || "—"}</span>
            {/* Charged on its own like a call made directly, so the row that spent it says so. */}
            {call.metered && (
              <span className="script-call-line" data-testid="script-call-cost">
                {vi.stepToolCost(call.cost_usd === null ? vi.stepCostUnknown : formatUsd(call.cost_usd))}
              </span>
            )}
            <ChildWork call={call} onOpenConversation={onOpenConversation} />
            {call.output && (
              <span className="script-call-line script-call-output" data-testid="script-call-output">
                {call.output}
              </span>
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}

/**
 * What a script did besides print, on the run's step and on the chat card alike: the calls
 * it made, then one line setting what those calls handed the script against what the script
 * handed the model. The gap between the two is what the script kept out of the model's reading.
 *
 * The line waits for the script to end, since neither number is known before. A script
 * that ran before the two were counted has its calls and no numbers, and the line says so
 * with a dash instead of a nought; one with neither says nothing at all.
 */
export function ScriptReport({
  work,
  settled,
  onOpenConversation,
}: {
  work: ScriptWork;
  settled: boolean;
  onOpenConversation?: OpenConversation;
}) {
  const calls = work.calls ?? [];
  const measured = work.received_chars !== undefined || work.printed_chars !== undefined;
  return (
    <>
      {calls.length > 0 && <ScriptCalls calls={calls} onOpenConversation={onOpenConversation} />}
      {settled && (measured || calls.length > 0) && (
        <span className="script-measures" data-testid="script-measures">
          {vi.scriptMeasures(work.received_chars ?? null, calls.length, work.printed_chars ?? null)}
        </span>
      )}
    </>
  );
}
