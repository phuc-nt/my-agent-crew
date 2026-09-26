import type { AgentInfo, RegistryTool } from "../../api/types";
import { problemsShown } from "../../hooks/agent-draft-checks";
import { useAgentDraft } from "../../hooks/use-agent-draft";
import { vi } from "../../i18n/vi";
import { AgentAvatar } from "../ui/agent-avatar";
import { ChannelSection } from "./channel-section";
import { DeleteAgent } from "./delete-agent";
import { IdentitySection } from "./identity-section";
import { LimitsSection } from "./limits-section";
import { ModelSection } from "./model-section";
import { PersonaSection } from "./persona-section";
import { PromptSection } from "./prompt-section";
import { SchedulesSection } from "./schedules-section";
import { ToolsSection } from "./tools-section";

interface Props {
  agent: AgentInfo;
  agents: AgentInfo[];
  tools: RegistryTool[];
  providers: string[];
  onBack: () => void;
  /** Called after a save or a delete so the crew list stops showing the old profile. */
  onChanged: () => void;
  /** A section to bring into view on arrival, such as "schedules" from the jobs list. */
  focus?: string;
}

/**
 * One agent's whole profile, in sections.
 *
 * The save bar stays at the top rather than at the bottom of nine sections: the person
 * needs to know there is something unsaved while they are still scrolling through them,
 * not after they have left.
 */
export function AgentEditor({ agent, agents, tools, providers, onBack, onChanged, focus }: Props) {
  const form = useAgentDraft(agent, onChanged);
  const readOnly = !agent.editable;
  // A box left empty holds the save without a banner until Lưu is pressed; pressing it
  // then names the box instead of doing nothing silently.
  const blocked = problemsShown(form.problems);
  const others = agents.filter((a) => a.id !== agent.id);

  return (
    <div className="agent-editor" data-testid="agent-editor">
      <div className="editor-bar">
        <button type="button" className="ghost" onClick={onBack}>
          {vi.editor.back}
        </button>
        <AgentAvatar id={agent.id} name={agent.name} />
        <span className="editor-title">
          <strong>{agent.name}</strong>
          <code>{agent.id}</code>
        </span>
        {agent.is_master && <span className="badge master">{vi.crew.master}</span>}
        <span className="spacer" />
        {/* One group, so on a phone the save controls wrap to a line of their own
            together instead of splitting word by word around the name. */}
        <span className="editor-actions">
          <span className="muted editor-dirty">
            {form.dirty.length > 0 ? vi.editor.dirty(form.dirty.length) : vi.editor.clean}
          </span>
          <button
            type="button"
            className="ghost"
            disabled={readOnly || form.dirty.length === 0 || form.saving}
            onClick={form.reset}
          >
            {vi.editor.revert}
          </button>
          <button
            type="button"
            className="primary"
            disabled={readOnly || form.dirty.length === 0 || form.saving || blocked}
            onClick={() => void form.save()}
          >
            {form.saving ? vi.editor.saving : vi.editor.save}
          </button>
        </span>
      </div>

      {readOnly && (
        <div className="notice" role="status" data-testid="read-only">
          {vi.editor.readOnly}
          <div className="muted">{vi.editor.definedAt(agent.dir)}</div>
        </div>
      )}
      {blocked && (
        <div className="notice warn" role="status" data-testid="save-held">
          {vi.editor.problemsHoldSave}
        </div>
      )}
      {form.error && (
        <div className="notice error" role="status">
          {vi.editor.saveFailed(form.error)}
        </div>
      )}
      {form.restartRequired.length > 0 && (
        <div className="notice warn restart-banner" role="status" data-testid="restart-banner">
          <strong>{vi.editor.restartTitle}</strong>
          <div>{vi.editor.restartBody(form.restartRequired)}</div>
        </div>
      )}

      <IdentitySection form={form} readOnly={readOnly} />
      <ModelSection form={form} readOnly={readOnly} providers={providers} />
      <PersonaSection agent={agent} readOnly={readOnly} />
      <ToolsSection form={form} readOnly={readOnly} tools={tools} />
      <LimitsSection
        form={form}
        readOnly={readOnly}
        others={others}
        isMaster={agent.is_master}
      />
      <SchedulesSection
        form={form}
        readOnly={readOnly}
        skills={agent.skills}
        focused={focus === "schedules"}
      />
      <ChannelSection form={form} agent={agent} readOnly={readOnly} />
      {/* Last, because it is the sum of every section above it. */}
      <PromptSection agentId={agent.id} />
      {!agent.is_master && agent.editable && (
        <DeleteAgent
          agentId={agent.id}
          onDeleted={() => {
            onChanged();
            onBack();
          }}
        />
      )}
    </div>
  );
}
