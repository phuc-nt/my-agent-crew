import type { AgentInfo } from "../../api/types";
import { AgentEditor } from "../../components/agent-editor/agent-editor";
import { CanvasSection } from "../../components/canvas/canvas-section";
import { CrewPanel } from "../../components/crew-panel";
import { JobsPanel } from "../../components/jobs-panel";
import { MemoryPanel } from "../../components/memory-panel";
import { ToolsMatrix } from "../../components/tools-matrix";
import type { McpController } from "../../hooks/use-mcp-servers";
import type { RegistryController } from "../../hooks/use-registry";
import { vi } from "../../i18n/vi";
import type { ManageProps } from "./manage-props";

interface CrewParts {
  editing: AgentInfo | null;
  registry: RegistryController;
  mcp: McpController;
  crewChanged: () => void;
  pendingProposals: number;
}

/** The pages for the crew, its tools, jobs, memory and canvases, as the screen draws them. */
export function crewPages(
  props: ManageProps,
  { editing, registry, mcp, crewChanged, pendingProposals }: CrewParts,
) {
  return (
    <>
      {/* A link to an agent that is gone says so rather than quietly showing the list:
          the person followed a URL and deserves to know it no longer resolves. The crew
          still has to have finished loading for "gone" to mean anything. */}
      {props.section === "crew" &&
        props.editingAgentId !== undefined &&
        editing === null &&
        props.agents.length > 0 && (
          <div className="notice error" role="status" data-testid="agent-not-found">
            {vi.editor.notFound(props.editingAgentId)}
          </div>
        )}
      {props.section === "crew" &&
        (editing ? (
          <AgentEditor
            agent={editing}
            agents={props.agents}
            tools={registry.tools}
            mcpServers={mcp.servers}
            browser={registry.connections?.browser}
            providers={registry.connections?.providers.map((p) => p.name) ?? []}
            onBack={() => props.onEditAgent(null)}
            fromJob={props.fromJob}
            onChanged={crewChanged}
            focus={props.editFocus}
            onOpenConversation={props.onOpenConversation}
          />
        ) : (
          <CrewPanel
            agents={props.agents}
            master={props.master}
            templates={props.templates}
            liveByAgent={props.liveByAgent}
            onInstall={props.onInstall}
            onEdit={(id) => props.onEditAgent(id)}
            onCreated={(id) => {
              crewChanged();
              props.onEditAgent(id);
            }}
          />
        ))}
      {props.section === "tools" && <ToolsMatrix tools={registry.tools} agents={props.agents} />}
      {props.section === "jobs" && (
        <JobsPanel
          jobs={props.jobs}
          agentName={props.agentName}
          onRunNow={props.onRunJob}
          onToggle={props.onToggleJob}
          onDelete={props.onDeleteJob}
          onOpenConversation={props.onOpenConversation}
          onOpenRun={props.onReplayRun}
          onEditSchedules={props.onEditSchedules}
          focusJob={props.focusJob}
          onOpenCrew={() => props.onNavigate("crew")}
        />
      )}
      {props.section === "memory" && (
        <MemoryPanel
          agents={props.agents}
          agentId={props.agentId}
          pendingProposals={pendingProposals}
          agentName={props.agentName}
          runs={props.runs}
        />
      )}
      {props.section === "canvas" && (
        <CanvasSection
          connected={props.connection?.connected ?? true}
          agentName={props.agentName}
          canvasId={props.canvasId}
          onOpenCanvas={props.onOpenCanvas}
          conversations={props.conversations}
          onOpenConversation={props.onOpenConversation}
        />
      )}
    </>
  );
}
