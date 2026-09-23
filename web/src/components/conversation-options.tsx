import type { Conversation, SkillInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { MetricCard, MetricDivider, MetricRow, SwitchRow } from "./ui/metric-card";
import { PopoverChip } from "./ui/popover-chip";

interface Props {
  conversation: Conversation;
  skills: SkillInfo[];
  onToggleAutonomous: (value: boolean) => void;
  onToggleSkill: (name: string, attached: boolean) => void;
  onRevokeAutoApprove: (name: string) => void;
}

/**
 * How this conversation behaves, behind one pill: whether tools run without asking,
 * which optional skills are attached, and which tools were allowed for good.
 *
 * The pill shows what is switched on — autonomy, attached skills, always-allowed tools —
 * so the state that matters is readable without opening the card.
 */
export function ConversationOptions({
  conversation: c,
  skills,
  onToggleAutonomous,
  onToggleSkill,
  onRevokeAutoApprove,
}: Props) {
  const optional = skills.filter((s) => !s.always);
  return (
    <PopoverChip
      testId="conversation-options"
      tone={c.autonomous ? "ok" : undefined}
      popoverLabel={vi.options.title}
      label={
        <>
          <span aria-hidden="true">⚙</span>
          {vi.options.chip}
          {c.autonomous && <span className="badge ok">{vi.autonomous}</span>}
          {c.skills.length > 0 && <span className="badge">{`${vi.skills} ${c.skills.length}`}</span>}
          {c.auto_approve.length > 0 && (
            <span className="badge" title={vi.autoApproved}>{`✓ ${c.auto_approve.length}`}</span>
          )}
        </>
      }
    >
      <SwitchRow
        icon="⚡"
        label={vi.autonomous}
        hint={vi.autonomousHint}
        checked={c.autonomous}
        onChange={onToggleAutonomous}
      />
      <MetricDivider />
      <MetricCard title={`${vi.skills} (${c.skills.length})`} className="flat">
        {optional.length === 0 ? (
          <p className="muted">{vi.options.skillsNone}</p>
        ) : (
          optional.map((skill) => (
            <SwitchRow
              key={skill.name}
              label={skill.name}
              hint={vi.skillsHint}
              checked={c.skills.includes(skill.name)}
              onChange={(attached) => onToggleSkill(skill.name, attached)}
              sub={skill.description}
            />
          ))
        )}
      </MetricCard>
      <MetricDivider />
      <MetricCard title={vi.autoApproved} className="flat">
        {c.auto_approve.length === 0 ? (
          <p className="muted">{vi.options.autoApproveNone}</p>
        ) : (
          <ul className="metric-list auto-approve" aria-label={vi.autoApproved} title={vi.autoApprovedHint}>
            {c.auto_approve.map((name) => (
              <li key={name}>
              <MetricRow
                icon="✓"
                label={<code>{name}</code>}
                action={
                  <button
                    type="button"
                    className="link-button"
                    aria-label={vi.autoApprovedRevoke(name)}
                    onClick={() => onRevokeAutoApprove(name)}
                  >
                    {vi.options.revoke}
                  </button>
                }
              />
              </li>
            ))}
          </ul>
        )}
      </MetricCard>
    </PopoverChip>
  );
}
