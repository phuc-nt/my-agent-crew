import type { NestedToolCall } from "../api/types";
import { vi } from "../i18n/vi";
import type { ScriptWork } from "../lib/nested-calls";
import { formatUsd } from "./budget-indicator";
import { summarizeArguments } from "./tool-args-detail";

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
export function ScriptCalls({ calls }: { calls: NestedToolCall[] }) {
  const failed = calls.filter((call) => !call.ok).length;
  return (
    <details className="script-calls" data-testid="script-calls">
      <summary>{vi.scriptCalls(calls.length, failed)}</summary>
      <ol>
        {calls.map((call, index) => (
          // A script may make the very same call twice; only its place tells the two apart.
          <li key={index} className="script-call" data-testid="script-call" data-ok={call.ok}>
            <span className={call.gated ? "script-call-head gated" : "script-call-head"}>
              <code className="script-call-name">{call.name}</code>
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
export function ScriptReport({ work, settled }: { work: ScriptWork; settled: boolean }) {
  const calls = work.calls ?? [];
  const measured = work.received_chars !== undefined || work.printed_chars !== undefined;
  return (
    <>
      {calls.length > 0 && <ScriptCalls calls={calls} />}
      {settled && (measured || calls.length > 0) && (
        <span className="script-measures" data-testid="script-measures">
          {vi.scriptMeasures(work.received_chars ?? null, calls.length, work.printed_chars ?? null)}
        </span>
      )}
    </>
  );
}
