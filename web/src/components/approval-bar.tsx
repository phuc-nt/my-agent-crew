import { vi } from "../i18n/vi";
import type { PendingApproval } from "../state/thread-reducer";
import { summarizeArguments } from "./tool-call-card";

interface Props {
  pending: PendingApproval;
  busy: boolean;
  onDecide: (approve: boolean) => void;
}

export function ApprovalBar({ pending, busy, onDecide }: Props) {
  return (
    <div className="approval-bar" role="alertdialog" aria-label={vi.awaitingApproval}>
      <div className="approval-text">
        <strong>{vi.approvalTitle(pending.name)}</strong>
        {pending.reason && <span className="approval-reason">{pending.reason}</span>}
        <code>{summarizeArguments(pending.arguments) || "—"}</code>
      </div>
      <div className="approval-actions">
        <button type="button" className="primary" disabled={busy} onClick={() => onDecide(true)}>
          {vi.approve}
        </button>
        <button type="button" className="danger" disabled={busy} onClick={() => onDecide(false)}>
          {vi.deny}
        </button>
      </div>
    </div>
  );
}
