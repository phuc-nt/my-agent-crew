import { useId, useState } from "react";
import { api } from "../api/client";
import type { Conversation, SkillInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { conversationMarkdown, downloadText, markdownFileName } from "../lib/conversation-markdown";
import { Icon } from "./ui/icon";
import { MetricCard, MetricDivider, MetricRow, SwitchRow } from "./ui/metric-card";
import { PopoverChip } from "./ui/popover-chip";

interface Props {
  conversation: Conversation;
  /** Who the replies are from, for the headings of an exported file. */
  agentName?: string;
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
  agentName = vi.agent,
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
          <Icon name="sliders" />
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
        icon="bolt"
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
                icon="check"
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
      <MetricDivider />
      <ExportButton conversationId={c.id} agentName={agentName} />
    </PopoverChip>
  );
}

/**
 * Downloads the whole conversation as markdown. It reads the stored messages rather than
 * the thread on screen: those carry the time each turn was said, and the thread may still
 * be loading or hold a reply that is only half streamed.
 */
function ExportButton({ conversationId, agentName }: { conversationId: string; agentName: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const hintId = useId();
  const run = async () => {
    setBusy(true);
    setError("");
    try {
      const detail = await api.getConversation(conversationId);
      downloadText(markdownFileName(detail.title), conversationMarkdown(detail, agentName));
    } catch (err) {
      setError(vi.options.exportFailed(err instanceof Error ? err.message : String(err)));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="export-row">
      <button type="button" disabled={busy} aria-describedby={hintId} onClick={() => void run()}>
        <Icon name="download" />
        {busy ? vi.options.exporting : vi.options.exportMarkdown}
      </button>
      {/* Written out rather than a tooltip, which a phone never shows. */}
      <p id={hintId} className="export-hint">
        {vi.options.exportHint}
      </p>
      {error && (
        <p className="notice error" role="status">
          {error}
        </p>
      )}
    </div>
  );
}
