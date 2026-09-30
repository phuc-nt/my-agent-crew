import { useState } from "react";
import { ApiError } from "../api/client";
import type { FactInfo, MemoryProposal } from "../api/types";
import { vi } from "../i18n/vi";
import { CompileProposalView } from "./compile-proposal-view";
import { DiffView } from "./diff-view";
import { formatDateTime } from "./run-timeline";

interface Props {
  proposal: MemoryProposal;
  agentName: (id: string) => string;
  /**
   * The person's facts as they stand, so a forget or an overwrite shows what it replaces;
   * null while they have not been read (still loading, or the read failed).
   */
  facts: FactInfo[] | null;
  /** MEMORY.md of the proposal's agent when that is the one loaded, otherwise null. */
  agentMemoryMd: string | null;
  /** Someone decided it elsewhere first: the card stays, saying so, instead of vanishing. */
  conflicted: boolean;
  onDecide: (id: string, approve: boolean) => Promise<void>;
  onConflict: (id: string) => void;
}

/**
 * The saved fact a proposal names. The server files a fact under its name trimmed and
 * lowercased, while a proposal keeps the name as the agent wrote it, so "Ngu-Som" is the
 * fact "ngu-som" and approving it overwrites or forgets that one.
 */
function namedFact(facts: FactInfo[], name: string): FactInfo | undefined {
  const key = name.trim().toLowerCase();
  return facts.find((fact) => fact.name === key);
}

/** What approving a legacy `agent_memory` proposal writes, mirroring the server's append. */
function appended(current: string, body: string): string {
  const separator = !current || current.endsWith("\n") ? "" : "\n";
  return `${current}${separator}- ${body.trim()}\n`;
}

/** One bullet per line the model gave a reason for, dropping the leading "- " each keeps
 *  from the prompt's own Markdown shape. */
function ProposalReasons({ reasons }: { reasons: string }) {
  const lines = reasons
    .split("\n")
    .map((line) => line.replace(/^\s*[-*+•]\s*/, "").trim())
    .filter(Boolean);
  if (lines.length === 0) return null;
  return (
    <div className="proposal-reasons">
      <p className="muted">{vi.memory.proposalReasons}</p>
      <ul>
        {lines.map((line, index) => (
          <li key={index}>{line}</li>
        ))}
      </ul>
    </div>
  );
}

/**
 * The part of a proposal a reviewer has to see to decide: for a rewrite, both sides of the
 * diff; for a fact, what it overwrites; for a forget, the exact fact that goes. Showing the
 * name alone asked the person to approve something they could not read.
 */
function ProposalBody({ proposal, facts, agentMemoryMd }: Omit<Props, "agentName" | "conflicted" | "onDecide" | "onConflict">) {
  // Unread facts are not "no facts": saying a forget drops nothing, or that a fact is new,
  // would invite approving a loss nobody was shown.
  if (facts === null && (proposal.kind === "user_forget" || proposal.kind === "user_fact")) {
    return (
      <>
        <p className="notice warn">{vi.memory.factsUnknown}</p>
        {proposal.body && <p className="fact-body">{proposal.body}</p>}
      </>
    );
  }
  const existing = facts && namedFact(facts, proposal.name);
  switch (proposal.kind) {
    case "agent_memory_rewrite":
      return <DiffView before={proposal.previous_body} after={proposal.body} />;
    case "agent_memory":
      return <DiffView before={agentMemoryMd ?? ""} after={appended(agentMemoryMd ?? "", proposal.body)} />;
    case "wiki_compile":
      return <CompileProposalView proposal={proposal} />;
    case "user_forget":
      return existing ? (
        <div className="forget-preview">
          <p>{vi.memory.forgetWhat}</p>
          <strong>{existing.description || existing.name}</strong>
          {existing.body && <p className="fact-body">{existing.body}</p>}
        </div>
      ) : (
        <p className="muted">{vi.memory.forgetMissing(proposal.name)}</p>
      );
    case "user_fact":
      return existing ? (
        <>
          <p className="notice warn">{vi.memory.overwrite(existing.description || existing.name)}</p>
          <DiffView before={existing.body} after={proposal.body} />
        </>
      ) : (
        proposal.body && <p className="fact-body">{proposal.body}</p>
      );
    default:
      return proposal.body ? <p className="fact-body">{proposal.body}</p> : null;
  }
}

export function ProposalCard(props: Props) {
  const { proposal } = props;
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const decide = async (approve: boolean) => {
    // A forget cannot be taken back from here, so it asks with the fact's own words.
    if (approve && proposal.kind === "user_forget") {
      const fact = props.facts && namedFact(props.facts, proposal.name);
      if (!window.confirm(vi.memory.confirmForget(fact?.description || proposal.name))) return;
    }
    setBusy(true);
    setFailed(false);
    try {
      await props.onDecide(proposal.id, approve);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) props.onConflict(proposal.id);
      else setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="proposal-card">
      <div className="fact-head">
        <span className="badge">{vi.memory.proposalKinds[proposal.kind] ?? proposal.kind}</span>
        <strong>{proposal.description || proposal.name}</strong>
      </div>
      <div className="muted">
        {props.agentName(proposal.agent_id)} · {formatDateTime(proposal.created_at)}
      </div>
      <ProposalBody proposal={proposal} facts={props.facts} agentMemoryMd={props.agentMemoryMd} />
      <ProposalReasons reasons={proposal.reasons} />
      {props.conflicted ? (
        <p className="notice" role="status">
          {vi.memory.alreadyDecided}
          {proposal.status !== "pending" && ` · ${vi.memory.proposalStatus[proposal.status] ?? proposal.status}`}
        </p>
      ) : (
        <div className="memory-editor-actions">
          <button type="button" disabled={busy} onClick={() => void decide(true)}>
            {vi.memory.approve}
          </button>
          <button type="button" className="ghost" disabled={busy} onClick={() => void decide(false)}>
            {vi.memory.reject}
          </button>
        </div>
      )}
      {failed && (
        <p className="notice error" role="alert">
          {vi.memory.decideFailed}
        </p>
      )}
    </li>
  );
}
