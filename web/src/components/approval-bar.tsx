import { vi } from "../i18n/vi";
import type { PendingApproval } from "../state/thread-reducer";
import { formatClock } from "./run-timeline";
import { summarizeArguments } from "./tool-call-card";
import { Icon } from "./ui/icon";

interface Props {
  pending: PendingApproval;
  busy: boolean;
  onDecide: (approve: boolean) => void;
  /** Approve and stop asking for this tool in the rest of the conversation. */
  onAlways?: () => void;
}

export function ApprovalBar({ pending, busy, onDecide, onAlways }: Props) {
  return (
    <div className="approval-bar callout" role="alertdialog" aria-label={vi.awaitingApproval}>
      <span className="callout-icon">
        <Icon name="approvals" />
      </span>
      <div className="approval-text">
        <strong>{vi.approvalTitle(pending.name)}</strong>
        {pending.reason && <span className="approval-reason">{pending.reason}</span>}
        <code>{summarizeArguments(pending.arguments) || "—"}</code>
        {pending.expiresAt && (
          <span className="approval-deadline">{vi.approvalDeadline(formatClock(pending.expiresAt))}</span>
        )}
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
