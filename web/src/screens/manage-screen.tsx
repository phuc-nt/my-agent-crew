import type { AgentInfo, InstallResult, JobInfo, SettingsInfo, StatsInfo, TemplateInfo } from "../api/types";
import type { RunInfo } from "../api/types";
import { ApprovalHistory } from "../components/approval-history";
import { AttentionCenter } from "../components/attention-center";
import { CrewPanel } from "../components/crew-panel";
import { JobsPanel } from "../components/jobs-panel";
import { MemoryPanel } from "../components/memory-panel";
import { RunGroupCard } from "../components/run-timeline";
import { SettingsPanel } from "../components/settings-panel";
import { StatsPanel } from "../components/stats-panel";
import type { ManageSection } from "../hooks/use-route";
import { MANAGE_SECTIONS } from "../hooks/use-route";
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
  jobs: vi.jobs,
  memory: vi.memory.tab,
  costs: vi.costs,
  connections: vi.manage.connections,
  settings: vi.settings,
};

/**
 * Everything about the crew rather than about one conversation: what is running, what
 * needs a decision, who is on the team, the schedule, what was remembered and the bill.
 *
 * It is a screen of its own rather than a rail beside the chat, because none of it is
 * about the conversation you are in — keeping it next to the thread made the crew's
 * work and the conversation's work look like the same thing.
 */
export function ManageScreen(props: Props) {
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
        <ul>
          {MANAGE_SECTIONS.map((section) => (
            <li key={section}>
              <button
                type="button"
                className={section === props.section ? "active" : ""}
                aria-current={section === props.section ? "page" : undefined}
                onClick={() => props.onNavigate(section)}
              >
                {LABELS[section]}
                {badge(section)}
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <main className="manage-body" aria-label={vi.manage.label}>
        <h2>{LABELS[props.section]}</h2>
        {props.section === "activity" && (
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
                />
              ))
            )}
            <h3>{vi.recentRuns}</h3>
            {recent.length === 0 ? (
              <p className="muted">{vi.noRuns}</p>
            ) : (
              runGroups(recent).map((group) => (
                <RunGroupCard
                  key={group.run.id}
                  group={group}
                  agentName={props.agentName}
                  onOpenConversation={props.onOpenConversation}
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
        {props.section === "crew" && (
          <CrewPanel
            agents={props.agents}
            master={props.master}
            templates={props.templates}
            liveByAgent={props.liveByAgent}
            onInstall={props.onInstall}
          />
        )}
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
        {props.section === "connections" && (
          <p className="muted" data-testid="connections-placeholder">
            {vi.manage.connectionsHint}
          </p>
        )}
        {props.section === "settings" && (
          <SettingsPanel settings={props.settings} agents={props.agents} />
        )}
      </main>
    </div>
  );
}
