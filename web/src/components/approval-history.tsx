import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ApprovalInfo, ApprovalStatus } from "../api/types";
import { vi } from "../i18n/vi";
import { EmptyState } from "./empty-state";
import { formatDateTime } from "./run-timeline";
import { ToolArgsDetail } from "./tool-args-detail";
import { summarizeArguments } from "./tool-call-card";

const STATUS_CLASS: Record<ApprovalStatus, string> = {
  pending: "live",
  approved: "ok",
  denied: "warn",
  // Nobody decided an expired request, so it is grey: amber is kept for a refusal,
  // which someone did choose, and for a request still waiting.
  expired: "",
  // An answered question is a settled request, not a refused one.
  answered: "ok",
};

/** The page sizes "Xem thêm" steps through. The first is the server's default and the
 *  last its ceiling, so a longer page than that would be clipped without saying so. */
const LIMITS = [50, 200, 500];

interface Props {
  agentName: (id: string) => string;
  onOpenConversation: (conversationId: string) => void;
  /** Bumped by the caller whenever a run finishes, so resolved requests show up. */
  refreshKey: number;
  /** Narrows the list to one conversation; every agent's requests when absent. */
  conversationId?: string;
}

/** Every approval request across agents, newest first, with how and when it was settled.
 *  The server lists only settled ones: a request still waiting is acted on elsewhere. */
export function ApprovalHistory({
  agentName,
  onOpenConversation,
  refreshKey,
  conversationId,
}: Props) {
  const [approvals, setApprovals] = useState<ApprovalInfo[] | null | undefined>(undefined);
  const [step, setStep] = useState(0);
  // The limit the rows on screen were fetched with; below `LIMITS[step]` a bigger page is
  // on its way, and the rows stay put meanwhile instead of blanking to "Đang tải…".
  const [loaded, setLoaded] = useState(0);
  const [shownFor, setShownFor] = useState(conversationId);
  if (shownFor !== conversationId) {
    // Another conversation's history starts from its first page, not the last one read.
    setShownFor(conversationId);
    setStep(0);
    setLoaded(0);
    setApprovals(undefined);
  }
  const limit = LIMITS[step];

  // The server narrows, not this component: its page is the newest N across the crew, so a
  // filter here would hide a quiet conversation's history behind a busy one's.
  useEffect(() => {
    let cancelled = false;
    api.listApprovals({ conversation_id: conversationId, limit }).then(
      (rows) => {
        if (cancelled) return;
        setApprovals(rows);
        setLoaded(limit);
      },
      () => !cancelled && setApprovals(null),
    );
    return () => {
      cancelled = true;
    };
  }, [refreshKey, conversationId, limit]);

  if (approvals === undefined) return <p className="muted">{vi.loading}</p>;
  if (approvals === null) return <p className="muted">{vi.loadFailed}</p>;
  if (approvals.length === 0) return <EmptyState icon="approvals" says={vi.approvalHistoryEmpty} />;
  // A short page is the whole history; a full one at the ceiling is as far as the server goes.
  // While a bigger page loads the button stays, disabled, so the tap visibly did something.
  const fetching = loaded < limit;
  const more = fetching || (step < LIMITS.length - 1 && approvals.length >= loaded);
  return (
    <>
      <ul className="approval-list" data-testid="approval-history">
        {approvals.map((a) => (
          <li key={a.id} data-status={a.status}>
            <div className="approval-head">
              <span>
                <strong>{agentName(a.agent_id)}</strong> · <code>{a.tool_name}</code>
              </span>
              <span className={`badge ${STATUS_CLASS[a.status]}`}>{vi.approvalStatus[a.status]}</span>
            </div>
            <div className="approval-meta muted">{formatDateTime(a.resolved_at ?? a.created_at)}</div>
            {a.kind === "question" ? <QuestionAsked approval={a} /> : <ToolCalled approval={a} />}
            <button type="button" className="link-button" onClick={() => onOpenConversation(a.conversation_id)}>
              {vi.openConversation}
            </button>
          </li>
        ))}
      </ul>
      {more && (
        <button
          type="button"
          className="approval-more"
          disabled={fetching}
          onClick={() => setStep((s) => s + 1)}
        >
          {fetching ? vi.loading : vi.approvalHistoryMore}
        </button>
      )}
    </>
  );
}

function ToolCalled({ approval }: { approval: ApprovalInfo }) {
  return (
    <>
      <code className="tool-arguments">{summarizeArguments(approval.arguments) || "—"}</code>
      <ToolArgsDetail args={approval.arguments} />
    </>
  );
}

/** A question reads as the question, what it offered and what came back: "ask_user" with
 *  its arguments cut to sixty characters says none of the three. */
function QuestionAsked({ approval }: { approval: ApprovalInfo }) {
  const asked = approval.arguments.question;
  const options = approval.options ?? [];
  return (
    <>
      <p className="approval-question">
        {typeof asked === "string" ? asked : summarizeArguments(approval.arguments)}
      </p>
      {options.length > 0 && (
        <div className="approval-options">
          <span className="muted">{vi.approvalOptions}</span>
          {options.map((option) => (
            <span key={option} className="approval-option">
              {option}
            </span>
          ))}
        </div>
      )}
      {approval.answer && <span className="approval-answer">{vi.approvalAnswer(approval.answer)}</span>}
    </>
  );
}
