import type { ReactNode } from "react";
import { vi } from "../i18n/vi";
import type { PendingApproval } from "../state/thread-reducer";
import { formatClock } from "./run-timeline";
import { ToolArgsDetail } from "./tool-args-detail";
import { summarizeArguments } from "./tool-call-card";
import { Icon } from "./ui/icon";

interface Props {
  pending: PendingApproval;
  busy: boolean;
  onDecide: (approve: boolean) => void;
  /** Approve and stop asking for this tool in the rest of the conversation. */
  onAlways?: () => void;
  /** Stands in for the deadline sentence, where the time left is counted down instead. */
  deadline?: ReactNode;
  /** In a list of requests: a group named by its row, not an alert breaking into the page. */
  labelledBy?: string;
}

export function ApprovalBar({ pending, busy, onDecide, onAlways, deadline, labelledBy }: Props) {
  return (
    <div
      className="approval-bar callout"
      role={labelledBy ? "group" : "alertdialog"}
      aria-label={labelledBy ? undefined : vi.awaitingApproval}
      aria-labelledby={labelledBy}
    >
      <span className="callout-icon">
        <Icon name="approvals" />
      </span>
      <div className="approval-text">
        <strong>{vi.approvalTitle(pending.name)}</strong>
        {pending.reason && <span className="approval-reason">{pending.reason}</span>}
        <code>{summarizeArguments(pending.arguments) || "—"}</code>
        <ToolArgsDetail args={pending.arguments} />
        {deadline ??
          (pending.expiresAt && (
            <span className="approval-deadline">{vi.approvalDeadline(formatClock(pending.expiresAt))}</span>
          ))}
      </div>
      <div className="approval-actions">
        <button type="button" className="primary" disabled={busy} onClick={() => onDecide(true)}>
          {vi.approve}
        </button>
        {onAlways && (
          <button type="button" disabled={busy} title={vi.alwaysAllowHint} onClick={onAlways}>
            {vi.alwaysAllow}
          </button>
        )}
        <button type="button" className="danger" disabled={busy} onClick={() => onDecide(false)}>
          {vi.deny}
        </button>
      </div>
    </div>
  );
}
