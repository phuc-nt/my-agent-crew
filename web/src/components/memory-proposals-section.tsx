import { useState } from "react";
import type { MemoryProposal } from "../api/types";
import { vi } from "../i18n/vi";
import { addedLines } from "../lib/line-diff";

interface Props {
  proposals: MemoryProposal[];
  /** The current MEMORY.md of the selected agent, to show what an append would add. */
  agentMemoryMd: string;
  agentName: (id: string) => string;
  onDecide: (id: string, approve: boolean) => Promise<void>;
  /** Puts back what an approved rewrite replaced. */
  onUndo: (proposal: MemoryProposal) => Promise<void>;
}

/** An approved rewrite is the only decision with something to put back. */
const canUndo = (proposal: MemoryProposal) =>
  proposal.status === "approved" && proposal.kind === "agent_memory_rewrite";

/** What a scheduled job wanted to remember and could not write on its own. */
export function MemoryProposalsSection(props: Props) {
  const [showHistory, setShowHistory] = useState(false);
  const pending = props.proposals.filter((p) => p.status === "pending");
  const decided = props.proposals.filter((p) => p.status !== "pending");

  return (
    <div data-testid="memory-proposals">
      {pending.length === 0 ? (
        <p className="muted">{vi.memory.proposalsEmpty}</p>
      ) : (
        <ul className="proposal-list">
          {pending.map((proposal) => (
            <li key={proposal.id}>
              <div className="fact-head">
                <span className="badge">
                  {vi.memory.proposalKinds[proposal.kind] ?? proposal.kind}
                </span>
                <strong>{proposal.description || proposal.name}</strong>
              </div>
              <div className="muted">
                {props.agentName(proposal.agent_id)} · {proposal.created_at}
              </div>
              {proposal.kind === "agent_memory" || proposal.kind === "agent_memory_rewrite" ? (
                <pre className="diff">
                  {addedLines(
                    proposal.kind === "agent_memory_rewrite"
                      ? proposal.previous_body
                      : props.agentMemoryMd,
                    proposal.body,
                  ).map((line, index) => (
                    <div key={index} className={line.added ? "added" : ""}>
                      {line.added ? `+ ${line.text}` : `  ${line.text}`}
                    </div>
                  ))}
                </pre>
              ) : (
                proposal.body && <p className="fact-body">{proposal.body}</p>
              )}
              <div className="memory-editor-actions">
                <button type="button" onClick={() => void props.onDecide(proposal.id, true)}>
                  {vi.memory.approve}
                </button>
                <button
                  type="button"
                  className="ghost"
                  onClick={() => void props.onDecide(proposal.id, false)}
                >
                  {vi.memory.reject}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <button type="button" className="ghost" onClick={() => setShowHistory((open) => !open)}>
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
                <div className="muted">{proposal.resolved_at}</div>
                {canUndo(proposal) && (
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => {
                      if (window.confirm(vi.memory.confirmUndo)) void props.onUndo(proposal);
                    }}
                  >
                    {vi.memory.undo}
                  </button>
                )}
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}
