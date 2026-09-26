import type { ReactNode } from "react";
import type { AgentInfo, Conversation, SkillInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { BudgetIndicator } from "./budget-indicator";
import { EditableTitle } from "./editable-title";
import { ConversationOptions } from "./conversation-options";
import { AgentAvatar } from "./ui/agent-avatar";

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
  /** Extra pills at the end of the row, e.g. the crew count. */
  extra?: ReactNode;
  /** A control before the title, e.g. the button that opens the list on a phone. */
  lead?: ReactNode;
}

/**
 * Who you are talking to and how the conversation behaves, in two lines.
 *
 * The first line is the title and three pills — spend, options, crew — each opening a
 * card with the detail, so the switches that used to crowd the row (autonomy, skills,
 * always-allowed tools) are one click away rather than always in the way. The second
 * line is the recap.
 */
export function ConversationHeader(props: Props) {
  const { conversation: c } = props;
  return (
    <header className="conversation-header">
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
        </div>
        <div className="header-controls">
          <BudgetIndicator
            spentUsd={props.spentUsd}
            capUsd={c.cost_cap_usd}
            unknownCostCalls={props.unknownCostCalls}
            childCount={props.childCount}
          />
          <ConversationOptions
            conversation={c}
            skills={props.skills}
            onToggleAutonomous={props.onToggleAutonomous}
            onToggleSkill={props.onToggleSkill}
            onRevokeAutoApprove={props.onRevokeAutoApprove}
          />
          {props.extra}
        </div>
      </div>
      <div className="header-summary">
        {c.summary ? (
          <p className="summary-text" title={c.summary}>
            {c.summary}
          </p>
        ) : (
          <p className="summary-text muted">{vi.noSummary}</p>
        )}
        <button
          type="button"
          className="link-button"
          title={vi.resummarizeHint}
          onClick={props.onSummarize}
        >
          {vi.resummarize}
        </button>
      </div>
    </header>
  );
}
