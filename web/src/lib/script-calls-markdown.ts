import type { NestedToolCall } from "../api/types";
import { formatUsd } from "../components/budget-indicator";
import { vi } from "../i18n/vi";
import { childSpentText, modelCallLabel } from "./nested-calls";

/**
 * What a script called on its own, as a numbered list for an exported conversation: which
 * tool, whether it failed, whether it changed something and went through the approval
 * gate, how long it took, and what it cost where it was charged on its own. What each was
 * asked and what it answered stay out, being the JSON the export is kept free of.
 *
 * A model the script asked itself is written in the words the card lists it under, and
 * not as code: its name is no tool's. A task handed to another agent says last what that
 * agent spent on it, in words, so the figure is not read as what the script's call paid.
 */
export function scriptCallsMarkdown(calls: NestedToolCall[]): string {
  const failed = calls.filter((call) => !call.ok).length;
  const lines = calls.map((call, index) => {
    const said = [modelCallLabel(call.name) ?? `\`${call.name}\``];
    if (!call.ok) said.push(vi.toolFailed);
    if (call.gated) said.push(vi.scriptCallGated);
    said.push(vi.stepDuration(call.ms));
    if (call.metered) said.push(call.cost_usd === null ? vi.stepCostUnknown : formatUsd(call.cost_usd));
    const childSpent = childSpentText(call);
    if (childSpent !== null) said.push(childSpent);
    return `${index + 1}. ${said.join(" · ")}`;
  });
  return `${vi.scriptCalls(calls.length, failed)}:\n\n${lines.join("\n")}`;
}
