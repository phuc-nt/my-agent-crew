import { useState } from "react";
import type { AgentInfo, InstallResult, JobInfo, RunInfo, StatsInfo, TemplateInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { ApprovalHistory } from "./approval-history";
import { AttentionCenter } from "./attention-center";
import { CrewPanel } from "./crew-panel";
import { JobsPanel } from "./jobs-panel";
import { MemoryPanel } from "./memory-panel";
import { parentConversationId, runGroups } from "../state/activity-reducer";
import { RunGroupCard } from "./run-timeline";
import { StatsPanel } from "./stats-panel";

export type ActivityTab = "activity" | "crew" | "jobs" | "approvals" | "memory" | "costs";

interface Props {
  runs: RunInfo[];
  liveRuns: RunInfo[];
  attention: RunInfo[];
  conversationId: string | null;
  jobs: JobInfo[] | null;
  stats: StatsInfo | null;
  agents: AgentInfo[];
  agentId: string;
  agentName: (id: string) => string;
  /** The crew tab: the master, the team and the bundled profiles that can join. */
  master?: AgentInfo | null;
  templates?: TemplateInfo[];
  liveByAgent?: Record<string, number>;
  onInstall?: (template: string) => Promise<InstallResult>;
  /** Controlled tab, so a header chip can open the crew tab; uncontrolled when absent. */
  tab?: ActivityTab;
  onTabChange?: (tab: ActivityTab) => void;
  onOpenConversation: (conversationId: string) => void;
  onRunJob: (jobId: string) => void;
  onToggleJob: (jobId: string, enabled: boolean) => void;
  onClose: () => void;
}

const TABS: { id: ActivityTab; label: string }[] = [
  { id: "activity", label: vi.activity },
  { id: "crew", label: vi.crew.tab },
  { id: "jobs", label: vi.jobs },
  { id: "approvals", label: vi.approvalsTab },
  { id: "memory", label: vi.memory.tab },
  { id: "costs", label: vi.costs },
];

/** Right rail: what needs you, what is running, the team, the schedule and the bill. */
export function ActivityPanel(props: Props) {
  const [ownTab, setOwnTab] = useState<ActivityTab>("activity");
  const tab = props.tab ?? ownTab;
  const setTab = (next: ActivityTab) => {
    setOwnTab(next);
    props.onTabChange?.(next);
  };
  const [onlyThisConversation, setOnlyThisConversation] = useState(false);
  const scoped =
    onlyThisConversation && props.conversationId
      ? props.runs.filter((r) => r.conversation_id === props.conversationId)
      : props.runs;
  const pendingProposals = props.stats?.pending_proposals ?? 0;
  const liveIds = new Set(props.liveRuns.map((r) => r.id));
  const recent = scoped.filter((r) => !liveIds.has(r.id));
  const live = scoped.filter((r) => liveIds.has(r.id));
  // Each settled run or new pause may have changed the approval ledger.
  const approvalsVersion = props.runs.filter((r) => r.finished_at !== null).length + props.attention.length;

  return (
    <aside className="activity-panel" aria-label={vi.activity} data-testid="activity-panel">
      <header>
        <div role="tablist" className="tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              className={tab === t.id ? "active" : ""}
              onClick={() => setTab(t.id)}
            >
              {t.label}
              {t.id === "activity" && props.liveRuns.length > 0 && (
                <span className="badge live"> {props.liveRuns.length}</span>
              )}
              {t.id === "memory" && pendingProposals > 0 && (
                <span className="badge warn"> {pendingProposals}</span>
              )}
            </button>
          ))}
        </div>
        <button type="button" className="icon-button" aria-label={vi.close} onClick={props.onClose}>
          ×
        </button>
      </header>

      {tab === "activity" && (
        <div className="panel-body" role="tabpanel">
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
          {props.conversationId && (
            <label className="toggle">
              <input
                type="checkbox"
                checked={onlyThisConversation}
                onChange={(event) => setOnlyThisConversation(event.currentTarget.checked)}
              />
              {vi.timelineForConversation}
            </label>
          )}
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
        </div>
      )}
      {tab === "crew" && (
        <div className="panel-body" role="tabpanel">
          <CrewPanel
            agents={props.agents}
            master={props.master ?? null}
            templates={props.templates ?? []}
            liveByAgent={props.liveByAgent ?? {}}
            onInstall={props.onInstall ?? (() => Promise.reject(new Error(vi.loadFailed)))}
          />
        </div>
      )}
      {tab === "jobs" && (
        <div className="panel-body" role="tabpanel">
          <JobsPanel
            jobs={props.jobs}
            agentName={props.agentName}
            onRunNow={props.onRunJob}
            onToggle={props.onToggleJob}
            onOpenConversation={props.onOpenConversation}
          />
        </div>
      )}
      {tab === "approvals" && (
        <div className="panel-body" role="tabpanel">
          <ApprovalHistory
            agentName={props.agentName}
            onOpenConversation={props.onOpenConversation}
            refreshKey={approvalsVersion}
          />
        </div>
      )}
      {tab === "memory" && (
        <div className="panel-body" role="tabpanel">
          <MemoryPanel
            agents={props.agents}
            agentId={props.agentId}
            pendingProposals={pendingProposals}
            agentName={props.agentName}
          />
        </div>
      )}
      {tab === "costs" && (
        <div className="panel-body" role="tabpanel">
          <StatsPanel stats={props.stats} agentName={props.agentName} />
        </div>
      )}
    </aside>
  );
}
