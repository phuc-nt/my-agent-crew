/**
 * Reading the header line a `delegate` result starts with.
 *
 * The tool returns the child's last reply prefixed by one line naming the conversation,
 * how its run ended, what it cost and how many steps it took, then one line saying what
 * the task came to (`outcome=`, with a reason when it is not done). A run can end `done`
 * on a task that is not, so the card leads with the outcome. Results stored before the
 * outcome line existed go straight from the header to the reply.
 *
 * A result whose first line is not that header is treated as reply text alone: the tool
 * may have failed before it opened a child, and showing the error beats showing nothing.
 */

export type DelegateResult = {
  conversationId: string;
  status: string;
  spentUsd: number;
  steps: number;
  outcome?: string;
  outcomeReason?: string;
  reply: string;
};

// Both are read by the Python tests too, so each stays a one-line constant.
const HEADER = /^conversation=(\S+) status=(\S+) spent=\$(\S+) steps=(\d+)$/;
const OUTCOME = /^outcome=(\S+)(?: reason=(.+))?$/;

export function parseDelegateResult(output: string): DelegateResult | null {
  const [first, ...rest] = output.split("\n");
  const match = HEADER.exec(first.trim());
  if (!match) return null;
  const spent = Number.parseFloat(match[3]);
  const outcome = rest.length > 0 ? OUTCOME.exec(rest[0].trim()) : null;
  const result: DelegateResult = {
    conversationId: match[1],
    status: match[2],
    spentUsd: Number.isFinite(spent) ? spent : 0,
    steps: Number.parseInt(match[4], 10),
    reply: (outcome ? rest.slice(1) : rest).join("\n").trim(),
  };
  if (outcome) {
    result.outcome = outcome[1];
    if (outcome[2]) result.outcomeReason = outcome[2];
  }
  return result;
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
