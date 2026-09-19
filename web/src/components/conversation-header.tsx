import type { Conversation, SkillInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { BudgetIndicator } from "./budget-indicator";

interface Props {
  conversation: Conversation;
  spentUsd: number;
  unknownCostCalls: number;
  skills: SkillInfo[];
  onRename: () => void;
  onToggleAutonomous: (value: boolean) => void;
  onToggleSkill: (name: string, attached: boolean) => void;
  onOpenSettings: () => void;
}

export function ConversationHeader(props: Props) {
  const { conversation: c, skills } = props;
  const optional = skills.filter((s) => !s.always);
  return (
    <header className="conversation-header">
      <div className="header-title">
        <h1>{c.title || vi.newConversation}</h1>
        <button type="button" className="link-button" onClick={props.onRename}>
          {vi.rename}
        </button>
      </div>
      <div className="header-controls">
        <BudgetIndicator
          spentUsd={props.spentUsd}
          capUsd={c.cost_cap_usd}
          unknownCostCalls={props.unknownCostCalls}
        />
        <label className="toggle" title={vi.autonomousHint}>
          <input
            type="checkbox"
            checked={c.autonomous}
            onChange={(event) => props.onToggleAutonomous(event.target.checked)}
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
                      onChange={(event) => props.onToggleSkill(skill.name, event.target.checked)}
                    />
                    {skill.name}
                    <span className="muted"> — {skill.description}</span>
                  </label>
                </li>
              ))}
            </ul>
          </details>
        )}
        <button type="button" className="ghost" onClick={props.onOpenSettings}>
          ⚙ {vi.settings}
        </button>
      </div>
    </header>
  );
}
