import type { AgentInfo, InstallResult, JobInfo, SettingsInfo, StatsInfo, TemplateInfo } from "../api/types";
import type { RunInfo } from "../api/types";
import { AgentEditor } from "../components/agent-editor/agent-editor";
import { ApprovalHistory } from "../components/approval-history";
import { AttentionCenter } from "../components/attention-center";
import { ConnectionsPanel } from "../components/connections-panel";
import { CrewPanel } from "../components/crew-panel";
import { EmptyState } from "../components/empty-state";
import { JobsPanel } from "../components/jobs-panel";
import { MemoryPanel } from "../components/memory-panel";
import { RunReplay } from "../components/run-replay";
import { RunGroupCard } from "../components/run-timeline";
import { SettingsPanel } from "../components/settings-panel";
import { StatsPanel } from "../components/stats-panel";
import { ToolsMatrix } from "../components/tools-matrix";
import { useCredentials } from "../hooks/use-credentials";
import { useRegistry } from "../hooks/use-registry";
import type { ManageSection } from "../hooks/use-route";
import { vi } from "../i18n/vi";
import { parentConversationId, runGroups } from "../state/activity-reducer";

interface Props {
  section: ManageSection;
  runs: RunInfo[];
  liveRuns: RunInfo[];
  attention: RunInfo[];
  jobs: JobInfo[] | null;
  stats: StatsInfo | null;
  settings: SettingsInfo | null;
  agents: AgentInfo[];
  agentId: string;
  agentName: (id: string) => string;
  master: AgentInfo | null;
  templates: TemplateInfo[];
  liveByAgent: Record<string, number>;
  onInstall: (template: string) => Promise<InstallResult>;
  /** The agent whose editor is open, when the URL names one. */
  editingAgentId?: string;
  /** The run shown on its own, when the URL names one. */
  replayRunId?: string;
  /** Opens or closes the editor by rewriting the route, so Back leaves it. */
  onEditAgent: (agentId: string | null) => void;
  /** Opens or closes a single run by rewriting the route, so Back leaves it. */
  onReplayRun: (runId: string | null) => void;
  /** Re-reads the crew after a profile is written, created or removed. */
  onReloadCrew: () => void;
  onNavigate: (section: ManageSection) => void;
  /** Leaving the manage screen: back to the chat, opening a conversation if one is named. */
  onBackToChat: () => void;
  onOpenConversation: (conversationId: string) => void;
  onRunJob: (jobId: string) => void;
  onToggleJob: (jobId: string, enabled: boolean) => void;
}

const LABELS: Record<ManageSection, string> = {
  activity: vi.activity,
  approvals: vi.approvalsTab,
  crew: vi.crew.tab,
  tools: vi.manage.tools,
  jobs: vi.jobs,
  memory: vi.memory.tab,
  costs: vi.costs,
  connections: vi.manage.connections,
  settings: vi.settings,
};

/** An icon per section, so the list can be scanned by shape before it is read. */
const ICONS: Record<ManageSection, string> = {
  activity: "📈",
  approvals: "✋",
  costs: "💰",
  crew: "👥",
  tools: "🔧",
  jobs: "⏰",
  memory: "🧠",
  connections: "🔌",
  settings: "⚙",
};

/**
 * The sections in three groups rather than one list of nine: what to keep an eye on,
 * who is on the team and what they can do, and how the install is wired. Grouped, the
 * section a person wants is found by its kind first — "is this about the team?" — which
 * is how the question arrives, instead of by reading the list top to bottom.
 */
export const NAV_GROUPS: { key: keyof typeof vi.manage.groups; sections: ManageSection[] }[] = [
  { key: "watch", sections: ["activity", "approvals", "costs"] },
  { key: "crew", sections: ["crew", "tools", "jobs", "memory"] },
  { key: "system", sections: ["connections", "settings"] },
];

/**
 * Everything about the crew rather than about one conversation: what is running, what
 * needs a decision, who is on the team, the schedule, what was remembered and the bill.
 *
 * It is a screen of its own rather than a rail beside the chat, because none of it is
 * about the conversation you are in — keeping it next to the thread made the crew's
 * work and the conversation's work look like the same thing.
 */
export function ManageScreen(props: Props) {
  const registry = useRegistry();
  // A saved key can build a provider or a search backend; the registry shows which.
  const credentials = useCredentials(registry.refresh);
  const editing = props.agents.find((a) => a.id === props.editingAgentId) ?? null;
  const pendingProposals = props.stats?.pending_proposals ?? 0;
  const liveIds = new Set(props.liveRuns.map((r) => r.id));
  const recent = props.runs.filter((r) => !liveIds.has(r.id));
  const live = props.runs.filter((r) => liveIds.has(r.id));
  // Each settled run or new pause may have changed the approval ledger.
  const approvalsVersion =
    props.runs.filter((r) => r.finished_at !== null).length + props.attention.length;

  const badge = (section: ManageSection) => {
    if (section === "activity" && props.liveRuns.length > 0)
      return <span className="badge live"> {props.liveRuns.length}</span>;
    if (section === "approvals" && props.attention.length > 0)
      return <span className="badge warn"> {props.attention.length}</span>;
    if (section === "memory" && pendingProposals > 0)
      return <span className="badge warn"> {pendingProposals}</span>;
    return null;
  };

  return (
    <div className="manage-layout" data-testid="manage-screen">
      <nav className="manage-nav" aria-label={vi.manage.nav}>
        <button type="button" className="ghost back-to-chat" onClick={props.onBackToChat}>
          {vi.manage.backToChat}
        </button>
        <div className="manage-nav-groups">
          {NAV_GROUPS.map((group) => (
            <div className="manage-nav-group" key={group.key}>
              <p className="manage-nav-label">{vi.manage.groups[group.key]}</p>
              <ul>
                {group.sections.map((section) => (
                  <li key={section}>
                    <button
                      type="button"
                      className={section === props.section ? "active" : ""}
                      aria-current={section === props.section ? "page" : undefined}
                      onClick={() => props.onNavigate(section)}
                    >
                      <span className="manage-nav-icon" aria-hidden="true">
                        {ICONS[section]}
                      </span>
                      {LABELS[section]}
                      {badge(section)}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </nav>
      <main className="manage-body" aria-label={vi.manage.label}>
        <h2>{LABELS[props.section]}</h2>
        {props.section === "activity" && props.replayRunId !== undefined && (
          <RunReplay
            runId={props.replayRunId}
            known={props.runs}
            agentName={props.agentName}
            onBack={() => props.onReplayRun(null)}
            onOpenConversation={props.onOpenConversation}
          />
        )}
        {props.section === "activity" && props.replayRunId === undefined && (
          <>
            <AttentionCenter
              runs={props.attention}
              parentTitle={(run) => {
                const parent = parentConversationId(run);
                if (parent === null) return null;
                const owner = props.runs.find((r) => r.conversation_id === parent);
                return owner ? owner.title || props.agentName(owner.agent_id) : null;
              }}
              agentName={props.agentName}
              onOpenConversation={props.onOpenConversation}
            />
            <h3>{vi.liveNow}</h3>
            {live.length === 0 ? (
              <p className="muted">{vi.nothingLive}</p>
            ) : (
              runGroups(live).map((group) => (
                <RunGroupCard
                  key={group.run.id}
                  group={group}
                  agentName={props.agentName}
                  expanded
                  onOpenConversation={props.onOpenConversation}
                  onOpenRun={props.onReplayRun}
                />
              ))
            )}
            <h3>{vi.recentRuns}</h3>
            {recent.length === 0 ? (
              // Nothing has run yet because nothing has been asked yet, so the way
              // out of this screen is the answer rather than another sentence.
              <EmptyState
                says={vi.noRuns}
                action={{ label: vi.noRunsAction, onClick: props.onBackToChat }}
              />
            ) : (
              runGroups(recent).map((group) => (
                <RunGroupCard
                  key={group.run.id}
                  group={group}
                  agentName={props.agentName}
                  onOpenConversation={props.onOpenConversation}
                  onOpenRun={props.onReplayRun}
                />
              ))
            )}
          </>
        )}
        {props.section === "approvals" && (
          <ApprovalHistory
            agentName={props.agentName}
            onOpenConversation={props.onOpenConversation}
            refreshKey={approvalsVersion}
          />
        )}
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
              providers={registry.connections?.providers.map((p) => p.name) ?? []}
              onBack={() => props.onEditAgent(null)}
              onChanged={props.onReloadCrew}
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
                props.onReloadCrew();
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
            onOpenConversation={props.onOpenConversation}
          />
        )}
        {props.section === "memory" && (
          <MemoryPanel
            agents={props.agents}
            agentId={props.agentId}
            pendingProposals={pendingProposals}
            agentName={props.agentName}
          />
        )}
        {props.section === "costs" && (
          <StatsPanel stats={props.stats} agentName={props.agentName} />
        )}
        {props.section === "connections" &&
          (registry.connections ? (
            <ConnectionsPanel
              connections={registry.connections}
              credentials={credentials}
              onChanged={registry.refresh}
            />
          ) : (
            <p className="muted">{registry.error ?? vi.manage.loading}</p>
          ))}
        {props.section === "settings" && (
          <SettingsPanel
            settings={props.settings}
            agents={props.agents}
            onNavigate={props.onNavigate}
          />
        )}
      </main>
    </div>
  );
}
