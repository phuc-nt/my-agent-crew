import { type ReactNode, useState } from "react";
import type { AgentInfo, Conversation, SkillInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { BudgetIndicator } from "./budget-indicator";
import { EditableTitle } from "./editable-title";
import { ConversationOptions } from "./conversation-options";
import { AgentAvatar } from "./ui/agent-avatar";
import { Icon } from "./ui/icon";

interface Props {
  conversation: Conversation;
  agentName: string;
  /** The agent's profile, when the crew is loaded: drives the work-mode badge. */
  agent?: AgentInfo;
  /** How many conversations this one delegated, for the budget tooltip. */
  childCount?: number;
  spentUsd: number;
  unknownCostCalls: number;
  skills: SkillInfo[];
  onRename: (title: string) => void;
  onSummarize: () => void;
  onToggleAutonomous: (value: boolean) => void;
  onToggleSkill: (name: string, attached: boolean) => void;
  /** Make the tool ask again: drop it from the conversation's always-allow list. */
  onRevokeAutoApprove: (name: string) => void;
  /** Stores a new cost cap from the budget card; 0 lifts it. */
  onSetCap?: (capUsd: number) => Promise<void>;
  /** A pill at the start of the row, ahead of spend and options: on a phone the row
   *  scrolls sideways, and only its start is sure to be on screen. */
  first?: ReactNode;
  /** Extra pills at the end of the row, e.g. the crew count. */
  extra?: ReactNode;
  /** A control before the title, e.g. the button that opens the list on a phone. */
  lead?: ReactNode;
  /** The source conversation's title, when `conversation.forked_from` names one still in
   *  the loaded list. Left `undefined` — the source has scrolled out of the sidebar's page,
   *  or belongs to another agent — falls back to a generic label rather than hiding the
   *  line: the conversation is still a fork even when its origin cannot be named. */
  sourceTitle?: string;
  /** Opens the source conversation; only ever rendered when `conversation.forked_from` is
   *  set, so `chat-screen.tsx` need not guard this itself. */
  onOpenSource?: () => void;
  /** A phone: the title row alone, with the pills and the recap behind a toggle. */
  compact?: boolean;
}

/**
 * Who you are talking to and how the conversation behaves, in two lines.
 *
 * The first line is the title and three pills — spend, options, crew — each opening a
 * card with the detail, so the switches that used to crowd the row (autonomy, skills,
 * always-allowed tools) are one click away rather than always in the way. The second
 * line is the recap.
 *
 * On a phone both are folded under the title row: the thread is what the screen is for,
 * and the switches are rarely what a thumb came for. Opening another conversation folds
 * them again.
 */
export function ConversationHeader(props: Props) {
  const { conversation: c, compact = false } = props;
  const [openFor, setOpenFor] = useState<string | null>(null);
  const open = !compact || openFor === c.id;
  return (
    <header className={`conversation-header${compact ? " compact" : ""}`}>
      <div className="header-row">
        <div className="header-title">
          {props.lead}
          <EditableTitle title={c.title} onRename={props.onRename} />
          <span className="agent-tag">
            <AgentAvatar id={c.agent_id} name={props.agentName} size="sm" />
            <span className="badge agent-badge" title={vi.agent}>
              {props.agentName}
            </span>
          </span>
          {props.agent?.mode === "work" && (
            <span
              className="badge work-badge"
              data-testid="work-badge"
              title={vi.modeWorkHint
                .replace("{cap}", String(props.agent.cost_cap_usd))
                .replace("{steps}", String(props.agent.max_steps))}
            >
              {vi.modeWork}
            </span>
          )}
          {/* The canvas is somewhere to go, not a setting, so a phone keeps it on this row. */}
          {compact && props.first}
          {compact && (
            <button
              type="button"
              className="icon-button header-more"
              aria-label={vi.headerMore}
              aria-expanded={open}
              onClick={() => setOpenFor(open ? null : c.id)}
            >
              <Icon name="chevron-down" />
            </button>
          )}
        </div>
        {open && <HeaderControls {...props} />}
      </div>
      {open && c.forked_from ? (
        <div className="header-fork-origin" data-testid="fork-origin">
          <span className="muted">{vi.fork.from}</span>
          <button type="button" className="link-button" onClick={props.onOpenSource}>
            {props.sourceTitle ?? vi.fork.original}
          </button>
        </div>
      ) : null}
      {open && <HeaderSummary summary={c.summary} onSummarize={props.onSummarize} />}
    </header>
  );
}

function HeaderControls(props: Props) {
  const { conversation: c, compact } = props;
  return (
    <div className="header-controls">
      {!compact && props.first}
      <BudgetIndicator
        spentUsd={props.spentUsd}
        capUsd={c.cost_cap_usd}
        unknownCostCalls={props.unknownCostCalls}
        childCount={props.childCount}
        onSetCap={props.onSetCap}
      />
      <ConversationOptions
        conversation={c}
        agentName={props.agentName}
        skills={props.skills}
        onToggleAutonomous={props.onToggleAutonomous}
        onToggleSkill={props.onToggleSkill}
        onRevokeAutoApprove={props.onRevokeAutoApprove}
      />
      {props.extra}
    </div>
  );
}

function HeaderSummary({ summary, onSummarize }: { summary: string; onSummarize: () => void }) {
  return (
    <div className="header-summary">
      {summary ? (
        <p className="summary-text" title={summary}>
          {summary}
        </p>
      ) : (
        <p className="summary-text muted">{vi.noSummary}</p>
      )}
      <button type="button" className="link-button" title={vi.resummarizeHint} onClick={onSummarize}>
        {vi.resummarize}
      </button>
    </div>
  );
}
