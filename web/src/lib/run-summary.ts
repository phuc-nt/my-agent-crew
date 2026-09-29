import type { RunInfo, RunStatus } from "../api/types";
import { vi } from "../i18n/vi";

/**
 * A few run endings reach the client as codes, not prose: the halt reasons the loop
 * emits and the marker a run gets when its turn stopped being read. Every other summary
 * is already a sentence (a reply preview, an error message) and is shown as written.
 *
 * A code only counts under the status that writes it. A finished reply that happens to be
 * the single word "budget" is the agent's answer, not a halt, and must read as such.
 */
const CODES = new Map<RunStatus, Map<string, string>>([
  [
    "halted",
    new Map([
      ["budget", vi.haltedBudget],
      ["max_steps", vi.haltedMaxSteps],
      ["loop", vi.haltedLoop],
    ]),
  ],
  ["error", new Map([["interrupted", vi.runInterrupted]])],
]);

/** The line under a run, so the timeline and the attention center say the same thing. */
export function runSummaryText(run: Pick<RunInfo, "status" | "summary">): string {
  return CODES.get(run.status)?.get(run.summary) ?? run.summary;
}
