import { useLayoutEffect, useRef } from "react";
import type { AgentInfo, McpServerInfo, RegistryTool } from "../../api/types";
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
  /** The MCP servers `config.yaml` declares, for the agent to be handed or not. */
  mcpServers: McpServerInfo[];
  providers: string[];
  onBack: () => void;
  /** What the back link says when it leads somewhere other than the crew list. */
  backLabel?: string;
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
export function AgentEditor({ agent, agents, tools, mcpServers, providers, onBack, backLabel, onChanged, focus }: Props) {
  const form = useAgentDraft(agent, onChanged);
  const readOnly = !agent.editable;
  // A box left empty holds the save without a banner until Lưu is pressed; pressing it
  // then names the box instead of doing nothing silently.
  const blocked = problemsShown(form.problems);
  const others = agents.filter((a) => a.id !== agent.id);
  const root = useRef<HTMLDivElement>(null);
  const bar = useRef<HTMLDivElement>(null);

  // The bar is sticky, so a section scrolled to the top of the page lands under it: from
  // the jobs list the schedules' hint and first row were covered. Its height, one line on
  // a wide screen and two on a phone, goes to the stylesheet for the headings' scroll
  // margin, measured before any section's own effect scrolls it into view.
  useLayoutEffect(() => {
    const measure = () => root.current?.style.setProperty("--editor-bar-height", `${bar.current?.offsetHeight ?? 0}px`);
    measure();
    if (!bar.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(bar.current);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="agent-editor" data-testid="agent-editor" ref={root}>
      <div className="editor-bar" ref={bar}>
        <button type="button" className="ghost" onClick={onBack}>
          {backLabel ?? vi.editor.back}
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
      <ToolsSection form={form} readOnly={readOnly} tools={tools} mcpServers={mcpServers} />
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
