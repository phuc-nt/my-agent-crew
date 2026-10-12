import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import type { IconName } from "./ui/icon";

/** A run pauses for two unrelated reasons, and only one of them is a permission request.
 *  The open question step is what tells them apart: a tool approval never writes one. */
function isAsking(run: RunInfo): boolean {
  return run.steps.some((step) => step.kind === "question" && step.duration_ms === null);
}

export function label(run: RunInfo, agent: string): string {
  if (run.status === "awaiting_approval") {
    return isAsking(run) ? vi.attentionAsking(agent) : vi.attentionAwaiting(agent);
  }
  if (run.status === "error") return vi.attentionFailed(agent);
  return vi.attentionHalted(agent);
}

/** The shape of the ask, so a question, a permission and a failure differ before they are read. */
export function icon(run: RunInfo): IconName {
  if (run.status === "awaiting_approval") return isAsking(run) ? "help" : "approvals";
  return "alert";
}
