import type { ReactNode } from "react";
import type { AgentInfo, Conversation, SkillInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { BudgetIndicator } from "./budget-indicator";
import { EditableTitle } from "./editable-title";

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
  onOpenSettings: () => void;
  /** Extra controls, e.g. the activity toggle. */
  extra?: ReactNode;
}

export function ConversationHeader(props: Props) {
  const { conversation: c, skills } = props;
  const optional = skills.filter((s) => !s.always);
  return (
    <header className="conversation-header">
      <div className="header-title">
        <EditableTitle title={c.title} onRename={props.onRename} />
        <span className="badge agent-badge" title={vi.agent}>
          {props.agentName}
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
      <div className="header-controls">
        <BudgetIndicator
          spentUsd={props.spentUsd}
          capUsd={c.cost_cap_usd}
          unknownCostCalls={props.unknownCostCalls}
          childCount={props.childCount}
        />
        <label className="toggle" title={vi.autonomousHint}>
          <input
            type="checkbox"
            checked={c.autonomous}
            onChange={(event) => props.onToggleAutonomous(event.currentTarget.checked)}
          />
          {vi.autonomous}
        </label>
        {optional.length > 0 && (
          <details className="skills-picker">
            <summary title={vi.skillsHint}>
              {vi.skills} ({c.skills.length})
            </summary>
            <ul>
              {optional.map((skill) => (
                <li key={skill.name}>
                  <label>
                    <input
                      type="checkbox"
                      checked={c.skills.includes(skill.name)}
                      onChange={(event) => props.onToggleSkill(skill.name, event.currentTarget.checked)}
                    />
                    {skill.name}
                    <span className="muted"> — {skill.description}</span>
                  </label>
                </li>
              ))}
            </ul>
          </details>
        )}
        {c.auto_approve.length > 0 && (
          <ul className="chip-list auto-approve" aria-label={vi.autoApproved} title={vi.autoApprovedHint}>
            {c.auto_approve.map((name) => (
              <li key={name}>
                <code>{name}</code>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={vi.autoApprovedRevoke(name)}
                  onClick={() => props.onRevokeAutoApprove(name)}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
        {props.extra}
        <button type="button" className="ghost" onClick={props.onOpenSettings}>
          ⚙ {vi.settings}
        </button>
      </div>
    </header>
  );
}
