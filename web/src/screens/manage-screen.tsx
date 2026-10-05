import { useLayoutEffect, useRef, useState, type UIEvent } from "react";
import type { AgentInfo, Conversation, InstallResult, JobInfo, SettingsInfo, StatsInfo, TemplateInfo } from "../api/types";
import type { RunInfo } from "../api/types";
import { AgentEditor } from "../components/agent-editor/agent-editor";
import { ApprovalHistory } from "../components/approval-history";
import { AttentionCenter } from "../components/attention-center";
import { CanvasSection } from "../components/canvas/canvas-section";
import { LivePreviewSetting } from "../components/canvas/live-preview-setting";
import { ConnectionNotice } from "../components/connection-notice";
import { ConnectionsPanel } from "../components/connections-panel";
import { CrewPanel } from "../components/crew-panel";
import { EmptyState } from "../components/empty-state";
import { ErrorBoundary } from "../components/error-boundary";
import { failingJobs } from "../components/job-last-run";
import { JobsPanel } from "../components/jobs-panel";
import { MemoryPanel } from "../components/memory-panel";
import { RecentRunsLog } from "../components/recent-runs-log";
import { RunReplay } from "../components/run-replay";
import { RunGroupCard } from "../components/run-timeline";
import { SettingsPanel } from "../components/settings-panel";
import { StatsPanel } from "../components/stats-panel";
import { ToolsMatrix } from "../components/tools-matrix";
import { Brand } from "../components/ui/brand-mark";
import { Icon, type IconName } from "../components/ui/icon";
import { useCredentials } from "../hooks/use-credentials";
import { useRegistry } from "../hooks/use-registry";
import type { ManageSection } from "../hooks/use-route";
import { vi } from "../i18n/vi";
import { waitingKey } from "../lib/run-progress";
import { parentConversationId, runGroups } from "../state/activity-reducer";

interface Props {
  section: ManageSection;
  runs: RunInfo[];
  liveRuns: RunInfo[];
  attention: RunInfo[];
  jobs: JobInfo[] | null;
  stats: StatsInfo | null;
  settings: SettingsInfo | null;
  /** The build this page runs and the one the server runs, shown under Settings. */
  versions?: { page: string | null; server: string | null };
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
  onReplayRun: (runId: string | null, fromJob?: string) => void;
  /** Re-reads the crew after a profile is written, created or removed. */
  onReloadCrew: () => void;
  onNavigate: (section: ManageSection) => void;
  /** Reads the activity list again after a request was settled from the approvals page. */
  onReloadActivity?: () => void;
  /** Leaving the manage screen: back to the chat, opening a conversation if one is named. */
  onBackToChat: () => void;
  onOpenConversation: (conversationId: string) => void;
  onRunJob: (jobId: string) => void;
  onToggleJob: (jobId: string, enabled: boolean) => void;
  onDeleteJob: (jobId: string) => void;
  /** The part of the open editor to bring into view, when the URL names one. */
  editFocus?: string;
  /** Opens an agent's editor on its schedules, from a row in the jobs list. */
  onEditSchedules?: (agentId: string, fromJob: string) => void;
  /** The row of the jobs list to bring into view, when the URL names one. */
  focusJob?: string;
  /** What the URL names under the canvas section; the section decides whether it is a canvas's id. */
  canvasId?: string;
  /** Opens a canvas on its own page, or the library for none, by rewriting the route. */
  onOpenCanvas: (canvasId: string | null) => void;
  /** The conversations this tab has listed, for the names of those a canvas is used in. */
  conversations: Conversation[];
  /** The open editor or run was reached from a job's row, and its back link returns there. */
  fromJob?: boolean;
  /** The live stream the pages follow; absent leaves out the notice of a drop. */
  connection?: { connected: boolean; connecting: boolean; onRetry: () => void };
}

const LABELS: Record<ManageSection, string> = {
  activity: vi.activity,
  approvals: vi.approvalsTab,
  crew: vi.crew.tab,
  tools: vi.manage.tools,
  jobs: vi.jobs,
  memory: vi.memory.tab,
  canvas: vi.canvas.tab,
  costs: vi.costs,
  connections: vi.manage.connections,
  settings: vi.settings,
};

/** An icon per section, so the list can be scanned by shape before it is read. */
const ICONS: Record<ManageSection, IconName> = {
  activity: "activity",
  approvals: "approvals",
  costs: "coins",
  crew: "users",
  tools: "wrench",
  jobs: "clock",
  memory: "book",
  canvas: "document",
  connections: "plug",
  settings: "sliders",
};

/**
 * The sections in three groups rather than one list of ten: what to keep an eye on,
 * who is on the team and what they can do, and how the install is wired. Grouped, the
 * section a person wants is found by its kind first — "is this about the team?" — which
 * is how the question arrives, instead of by reading the list top to bottom.
 */
export const NAV_GROUPS: { key: keyof typeof vi.manage.groups; sections: ManageSection[] }[] = [
  { key: "watch", sections: ["activity", "approvals", "costs"] },
  { key: "crew", sections: ["crew", "tools", "jobs", "memory", "canvas"] },
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
  const failing = failingJobs(props.jobs);
  const liveIds = new Set(props.liveRuns.map((r) => r.id));
  const recent = props.runs.filter((r) => !liveIds.has(r.id));
  const live = props.runs.filter((r) => liveIds.has(r.id));
  // A request waits on a decision and is settled on the approvals page; a failure or a
  // halt is read and dismissed with the rest of the activity. Counting them together
  // sent the person to Duyệt for an error with nothing to decide.
  const awaiting = props.attention.filter((r) => r.status === "awaiting_approval");
  const failed = props.attention.filter((r) => r.status !== "awaiting_approval");
  // The ledger lists settled requests, and a request settles as its run leaves the pause.
  // Its key changes with every sign of that here: a run ending, the requests waiting
  // changing, and a row below changing something on the server. A sum of the first two
  // stays put when a resume and its end land in one update; and a turn that stops again on
  // its next tool is the same run waiting once more, told apart only by what it waits on.
  const [rowReloads, setRowReloads] = useState(0);
  const finishedRuns = props.runs.filter((r) => r.finished_at !== null).length;
  const approvalsKey = `${finishedRuns}|${waitingKey(awaiting)}|${rowReloads}`;
  const reloadAfterRow = () => {
    setRowReloads((n) => n + 1);
    props.onReloadActivity?.();
  };
  const parentTitle = (run: RunInfo) => {
    const parent = parentConversationId(run);
    if (parent === null) return null;
    const owner = props.runs.find((r) => r.conversation_id === parent);
    return owner ? owner.title || props.agentName(owner.agent_id) : null;
  };

  // The number alone is ambiguous once an entry can carry two, so each says what it counts.
  const count = (n: number, tone: string, says: string) => (
    <span className={`badge ${tone}`}>
      {` ${n}`}
      <span className="sr-only"> {says}</span>
    </span>
  );
  // A paused run is still live, but it is waiting on a person rather than running: it is
  // counted on Duyệt, and counting it here too would call one request two things at once.
  const running = props.liveRuns.filter((r) => r.status === "running").length;

  // Brings the current section's entry into view. On a phone the sections are one row of
  // pills scrolled sideways, and arriving on a section whose pill sits past the edge would
  // leave the person with no sign of where they are. The counts come after the first paint
  // and widen the pills, and a browser does not hold a sideways scroll in place as they
  // grow, so the entry is brought back when one changes — unless the person has scrolled
  // it out of sight since: the row is theirs then, and snapping it back would slide the
  // pill they were reaching for from under their finger. "nearest" moves nothing that is
  // already visible, so neither the sidebar on a wide screen nor a pill in view jumps.
  const active = useRef<HTMLButtonElement>(null);
  const shown = useRef<{ section: ManageSection | null; inView: boolean }>({ section: null, inView: true });
  const counts = [running, failed.length, awaiting.length, pendingProposals, failing].join();
  useLayoutEffect(() => {
    if (shown.current.section === props.section && !shown.current.inView) return;
    active.current?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    shown.current = { section: props.section, inView: true };
  }, [props.section, counts]);
  // Where the person's scrolling left the current entry. A scroll event does not bubble in
  // React, so the wide screen's column and the phone's row each report their own.
  const onNavScroll = (event: UIEvent<HTMLElement>) => {
    const pill = active.current?.getBoundingClientRect();
    if (!pill) return;
    const box = event.currentTarget.getBoundingClientRect();
    shown.current.inView =
      pill.left >= box.left - 1 && pill.right <= box.right + 1 && pill.top >= box.top - 1 && pill.bottom <= box.bottom + 1;
  };
  const badge = (section: ManageSection) => {
    if (section === "activity")
      return (
        <>
          {running > 0 && count(running, "live", vi.manage.liveBadge)}
          {failed.length > 0 && count(failed.length, "warn", vi.manage.failedBadge)}
        </>
      );
    if (section === "approvals" && awaiting.length > 0) return count(awaiting.length, "warn", vi.manage.waitingBadge);
    if (section === "memory" && pendingProposals > 0)
      return <span className="badge warn"> {pendingProposals}</span>;
    // Only a failure earns a count here: a schedule that ran fine or never ran yet is
    // not something to go and look at.
    if (section === "jobs" && failing > 0)
      return (
        <span className="badge danger" title={vi.jobRow.failing(failing)} data-testid="jobs-failing">
          {/* A bare red number reads as "1" to a screen reader; the sentence says what of. */}
          <span aria-hidden="true">{failing}</span>
          <span className="sr-only">{vi.jobRow.failing(failing)}</span>
        </span>
      );
    return null;
  };

  return (
    <div className="manage-layout" data-testid="manage-screen">
      <nav className="manage-nav" aria-label={vi.manage.nav} onScroll={onNavScroll}>
        <div className="manage-nav-head">
          <Brand />
        </div>
        <button type="button" className="ghost back-to-chat" onClick={props.onBackToChat}>
          {vi.manage.backToChat}
        </button>
        <div className="manage-nav-groups" onScroll={onNavScroll}>
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
                      ref={section === props.section ? active : undefined}
                      onClick={() => props.onNavigate(section)}
                    >
                      <Icon name={ICONS[section]} />
                      <span className="manage-nav-name">{LABELS[section]}</span>
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
        <h2 className="manage-title">{LABELS[props.section]}</h2>
        {props.connection && <ConnectionNotice {...props.connection} />}
        {/* One boundary per page, keyed by it: a section that breaks leaves the nav
            standing, and choosing any other page is enough to leave the failure behind. */}
        <ErrorBoundary key={`${props.section}/${props.replayRunId ?? props.editingAgentId ?? ""}`}>
          {props.section === "activity" && props.replayRunId !== undefined && (
            <RunReplay
              runId={props.replayRunId}
              known={props.runs}
              agentName={props.agentName}
              onBack={() => props.onReplayRun(null)}
              backLabel={props.fromJob ? vi.jobRow.back : undefined}
              onOpenConversation={props.onOpenConversation}
            />
          )}
          {props.section === "activity" && props.replayRunId === undefined && (
            <>
              <AttentionCenter
                runs={failed}
                parentTitle={parentTitle}
                agentName={props.agentName}
                onOpenConversation={props.onOpenConversation}
                waitingElsewhere={awaiting.length}
                onOpenWaiting={() => props.onNavigate("approvals")}
              />
              <h3>{vi.liveNow}</h3>
              {live.length === 0 ? (
                <EmptyState icon="activity" says={vi.nothingLive} />
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
              <RecentRunsLog
                streamed={recent}
                agents={props.agents}
                agentName={props.agentName}
                onOpenConversation={props.onOpenConversation}
                onOpenRun={props.onReplayRun}
                onBackToChat={props.onBackToChat}
              />
            </>
          )}
          {props.section === "approvals" && (
            <>
              {/* What waits comes first and is decided here; the ledger of what was
                  decided before sits under it. */}
              <AttentionCenter
                runs={awaiting}
                inline
                parentTitle={parentTitle}
                agentName={props.agentName}
                onOpenConversation={props.onOpenConversation}
                onReload={reloadAfterRow}
                failedElsewhere={failed.length}
                onOpenFailed={() => props.onNavigate("activity")}
              />
              <h3>{vi.approvalHistory}</h3>
              <ApprovalHistory
                agentName={props.agentName}
                onOpenConversation={props.onOpenConversation}
                refreshKey={approvalsKey}
              />
            </>
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
                backLabel={props.fromJob ? vi.jobRow.back : undefined}
                onChanged={props.onReloadCrew}
                focus={props.editFocus}
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
            <>
              {/* The one thing here the person sets, and for this device alone, comes before the
                  machine's configuration, which is read on this page and changed elsewhere. */}
              <LivePreviewSetting />
              <SettingsPanel
                settings={props.settings}
                agents={props.agents}
                onNavigate={props.onNavigate}
                versions={props.versions}
              />
            </>
          )}
        </ErrorBoundary>
      </main>
    </div>
  );
}
