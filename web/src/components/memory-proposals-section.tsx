import { useState } from "react";
import type { FactInfo, MemoryProposal } from "../api/types";
import { vi } from "../i18n/vi";
import { ProposalCard } from "./proposal-card";
import { formatDateTime } from "./run-timeline";

interface Props {
  proposals: MemoryProposal[];
  /** The agent whose MEMORY.md is loaded; an append is only previewed against its own file. */
  agentId: string;
  agentMemoryMd: string;
  /** The person's facts, so a forget or an overwrite can show what it replaces; null unread. */
  facts: FactInfo[] | null;
  agentName: (id: string) => string;
  onDecide: (id: string, approve: boolean) => Promise<void>;
  /** Puts back what an approved rewrite replaced. */
  onUndo: (proposal: MemoryProposal) => Promise<void>;
  /** Re-reads the list, after finding out it was stale. */
  onRefresh: () => Promise<void>;
}

/** An approved rewrite is the only decision with something to put back. */
const canUndo = (proposal: MemoryProposal) =>
  proposal.status === "approved" && proposal.kind === "agent_memory_rewrite";

type UndoState = { id: string; state: "busy" | "done" | "failed" };

/** What a scheduled job wanted to remember and could not write on its own. */
export function MemoryProposalsSection(props: Props) {
  const [showHistory, setShowHistory] = useState(false);
  // Decided somewhere else first (another tab, the phone). Kept on screen with a note, so
  // the card the person was reading does not silently vanish under their cursor.
  const [conflicted, setConflicted] = useState<ReadonlySet<string>>(new Set());
  const [undo, setUndo] = useState<UndoState | null>(null);
  const pending = props.proposals.filter((p) => p.status === "pending" || conflicted.has(p.id));
  const decided = props.proposals.filter((p) => p.status !== "pending");

  const onConflict = (id: string) => {
    setConflicted((ids) => new Set(ids).add(id));
    void props.onRefresh().catch(() => undefined);
  };

  const runUndo = async (proposal: MemoryProposal) => {
    if (!window.confirm(vi.memory.confirmUndo)) return;
    setUndo({ id: proposal.id, state: "busy" });
    try {
      await props.onUndo(proposal);
      setUndo({ id: proposal.id, state: "done" });
    } catch {
      setUndo({ id: proposal.id, state: "failed" });
    }
  };

  return (
    <div data-testid="memory-proposals">
      {pending.length === 0 ? (
        <p className="muted">{vi.memory.proposalsEmpty}</p>
      ) : (
        <ul className="proposal-list">
          {pending.map((proposal) => (
            <ProposalCard
              key={proposal.id}
              proposal={proposal}
              agentName={props.agentName}
              facts={props.facts}
              agentMemoryMd={proposal.agent_id === props.agentId ? props.agentMemoryMd : null}
              conflicted={conflicted.has(proposal.id)}
              onDecide={props.onDecide}
              onConflict={onConflict}
            />
          ))}
        </ul>
      )}

      <button
        type="button"
        className="ghost proposal-history-toggle"
        aria-expanded={showHistory}
        onClick={() => setShowHistory((open) => !open)}
      >
        {vi.memory.history} ({decided.length})
      </button>
      {showHistory &&
        (decided.length === 0 ? (
          <p className="muted">{vi.memory.historyEmpty}</p>
        ) : (
          <ul className="proposal-list history">
            {decided.map((proposal) => (
              <li key={proposal.id}>
                <span className="badge">{vi.memory.proposalStatus[proposal.status] ?? proposal.status}</span>
                <span className="badge">
                  {vi.memory.proposalKinds[proposal.kind] ?? proposal.kind}
                </span>
                <strong>{proposal.description || proposal.name}</strong>
                <div className="muted">
                  {proposal.resolved_at ? formatDateTime(proposal.resolved_at) : ""}
                </div>
                {canUndo(proposal) && (
                  <button
                    type="button"
                    className="ghost"
                    disabled={undo?.id === proposal.id && undo.state === "busy"}
                    onClick={() => void runUndo(proposal)}
                  >
                    {vi.memory.undo}
                  </button>
                )}
                {undo?.id === proposal.id && undo.state !== "busy" && (
                  <p
                    className={undo.state === "done" ? "notice ok" : "notice error"}
                    role={undo.state === "done" ? "status" : "alert"}
                  >
                    {undo.state === "done" ? vi.memory.undone : vi.memory.undoFailed}
                  </p>
                )}
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}
