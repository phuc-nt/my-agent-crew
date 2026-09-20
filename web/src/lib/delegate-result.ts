/**
 * Reading the header line a `delegate` result starts with.
 *
 * The tool returns the child's last reply prefixed by one line naming the conversation,
 * how it ended, what it cost and how many steps it took. The card wants those four as
 * fields and the reply as prose, so the parse happens here rather than in the component.
 *
 * A result whose first line is not that header is treated as reply text alone: the tool
 * may have failed before it opened a child, and showing the error beats showing nothing.
 */

export type DelegateResult = {
  conversationId: string;
  status: string;
  spentUsd: number;
  steps: number;
  reply: string;
};

const HEADER = /^conversation=(\S+) status=(\S+) spent=\$(\S+) steps=(\d+)$/;

export function parseDelegateResult(output: string): DelegateResult | null {
  const newline = output.indexOf("\n");
  const first = newline === -1 ? output : output.slice(0, newline);
  const match = HEADER.exec(first.trim());
  if (!match) return null;
  const spent = Number.parseFloat(match[3]);
  return {
    conversationId: match[1],
    status: match[2],
    spentUsd: Number.isFinite(spent) ? spent : 0,
    steps: Number.parseInt(match[4], 10),
    reply: newline === -1 ? "" : output.slice(newline + 1).trim(),
  };
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
