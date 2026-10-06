import type { NestedToolCall } from "../api/types";
import { vi } from "../i18n/vi";
import { formatUsd } from "./budget-indicator";
import { summarizeArguments } from "./tool-call-card";

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
            <span className="script-call-head">
              <code className="script-call-name">{call.name}</code>
              {!call.ok && <span className="step-state failed">{vi.toolFailed}</span>}
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
