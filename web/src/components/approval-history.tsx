import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ApprovalInfo, ApprovalStatus } from "../api/types";
import { vi } from "../i18n/vi";
import { formatDateTime } from "./run-timeline";
import { summarizeArguments } from "./tool-call-card";

const STATUS_CLASS: Record<ApprovalStatus, string> = {
  pending: "live",
  approved: "ok",
  denied: "warn",
  expired: "warn",
};

interface Props {
  agentName: (id: string) => string;
  onOpenConversation: (conversationId: string) => void;
  /** Bumped by the caller whenever a run finishes, so resolved requests show up. */
  refreshKey: number;
}

/** Every approval request across agents, newest first, with how and when it was settled. */
export function ApprovalHistory({ agentName, onOpenConversation, refreshKey }: Props) {
  const [approvals, setApprovals] = useState<ApprovalInfo[] | null | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    api.listApprovals().then(
      (loaded) => !cancelled && setApprovals(loaded),
      () => !cancelled && setApprovals(null),
    );
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (approvals === undefined) return <p className="muted">{vi.loading}</p>;
  if (approvals === null) return <p className="muted">{vi.loadFailed}</p>;
  if (approvals.length === 0) return <p className="muted">{vi.approvalHistoryEmpty}</p>;
  return (
    <ul className="approval-list" data-testid="approval-history">
      {approvals.map((a) => (
        <li key={a.id} data-status={a.status}>
          <div className="approval-head">
            <span>
              <strong>{agentName(a.agent_id)}</strong> · <code>{a.tool_name}</code>
            </span>
            <span className={`badge ${STATUS_CLASS[a.status]}`}>{vi.approvalStatus[a.status]}</span>
          </div>
          <div className="approval-meta muted">
            {formatDateTime(a.resolved_at ?? a.created_at)}
            {a.status === "pending" && a.expires_at && ` · ${vi.approvalDeadline(formatDateTime(a.expires_at))}`}
          </div>
          <code className="tool-arguments">{summarizeArguments(a.arguments) || "—"}</code>
          <button type="button" className="link-button" onClick={() => onOpenConversation(a.conversation_id)}>
            {vi.openConversation}
          </button>
        </li>
      ))}
    </ul>
  );
}
