/**
 * Reading the lines a `delegate` result starts with.
 *
 * The tool returns the child's last reply prefixed by one line naming the conversation,
 * how its run ended, what it cost and how many steps it took, then one line saying what
 * the task came to (`outcome=`, with a reason when it is not done). A run can end `done`
 * on a task that is not, so the card leads with the outcome. Results stored before the
 * outcome line existed go straight from the header to the reply.
 *
 * Under the outcome line stand the canvases the child wrote, one a line, then a blank line
 * that is there even when it wrote none. Only lines above that blank line are read as
 * canvases, and only when every one of them is: a reply that quotes a tag stays a reply,
 * and so does a result stored before the blank line existed.
 *
 * A result whose first line is not that header is treated as reply text alone: the tool
 * may have failed before it opened a child, and showing the error beats showing nothing.
 */

import type { RunStatus } from "../api/types";
import { vi } from "../i18n/vi";
import { runSummaryText } from "./run-summary";

export type DelegateResult = {
  conversationId: string;
  status: string;
  spentUsd: number;
  steps: number;
  outcome?: string;
  outcomeReason?: string;
  canvases: DelegateCanvas[];
  reply: string;
};

/** A canvas the child wrote, at the newest version it wrote. The title is the child's wording. */
export type DelegateCanvas = { id: string; version: number; title: string };

// All three are read by the Python tests too, so each stays a one-line constant.
const HEADER = /^conversation=(\S+) status=(\S+) spent=\$(\S+) steps=(\d+)$/;
const OUTCOME = /^outcome=(\S+)(?: reason=(.+))?$/;
const CANVAS = /^\[artifact ([0-9a-f]{12}) v(\d+)\] (.*)$/;

/** What follows the outcome line, split at the blank line the server always writes there. */
function canvasBlock(lines: string[]): { canvases: DelegateCanvas[]; reply: string[] } {
  const blank = lines.indexOf("");
  if (blank < 0) return { canvases: [], reply: lines };
  const canvases: DelegateCanvas[] = [];
  for (const line of lines.slice(0, blank)) {
    const match = CANVAS.exec(line);
    if (!match) return { canvases: [], reply: lines };
    canvases.push({ id: match[1], version: Number.parseInt(match[2], 10), title: match[3] });
  }
  return { canvases, reply: lines.slice(blank + 1) };
}

export function parseDelegateResult(output: string): DelegateResult | null {
  const [first, ...rest] = output.split("\n");
  const match = HEADER.exec(first.trim());
  if (!match) return null;
  const spent = Number.parseFloat(match[3]);
  const outcome = rest.length > 0 ? OUTCOME.exec(rest[0].trim()) : null;
  const block = outcome ? canvasBlock(rest.slice(1)) : { canvases: [], reply: rest };
  const result: DelegateResult = {
    conversationId: match[1],
    status: match[2],
    spentUsd: Number.isFinite(spent) ? spent : 0,
    steps: Number.parseInt(match[4], 10),
    canvases: block.canvases,
    reply: block.reply.join("\n").trim(),
  };
  if (outcome) {
    result.outcome = outcome[1];
    if (outcome[2]) result.outcomeReason = outcome[2];
  }
  return result;
}

const STILL_GOING = new Set(["running", "awaiting_approval"]);
const ENDED: Record<string, string> = { error: vi.runEndedError, halted: vi.runEndedHalted };
const REFUSED = /^(\S+) (denied|expired)$/;

/**
 * The reason in words. The server writes some as codes for the delegating model to read —
 * how the child's run stopped, a wait that ran out while it was still going, a tool approval
 * refused or left to lapse — and the child's own reasons as it wrote them.
 */
export function delegateReason(result: DelegateResult): string {
  const reason = result.outcomeReason ?? "";
  if (result.outcome === "failed") {
    if (reason === "timeout" && STILL_GOING.has(result.status)) return vi.delegateTimeout;
    // A run that stopped with nothing to say gets its status as the reason.
    if (reason === result.status) return ENDED[reason] ?? reason;
    return runSummaryText({ status: result.status as RunStatus, summary: reason });
  }
  const refused = result.outcome === "blocked" ? REFUSED.exec(reason) : null;
  return refused ? vi.delegateRefused[refused[2]](refused[1]) : reason;
}

/** How the card colours a result: a run that did not finish, or an older result whose run
 *  did not end `done`, is a failure; a task that ended short of done is a warning. */
export function delegateTone(result: DelegateResult): "ok" | "warn" | "danger" {
  if (!result.outcome) return result.status === "done" ? "ok" : "danger";
  if (result.outcome === "done") return "ok";
  return result.outcome === "failed" ? "danger" : "warn";
}

/** The task a delegate call was given, short enough to read at a glance. */
export function delegateTask(args: Record<string, unknown>, limit = 140): string {
  const task = typeof args.task === "string" ? args.task.trim() : "";
  return task.length > limit ? `${task.slice(0, limit)}…` : task;
}

/** The agent a delegate call named, or "" when the arguments are not what we expect. */
export function delegateAgent(args: Record<string, unknown>): string {
  return typeof args.agent === "string" ? args.agent : "";
}
