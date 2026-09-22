import { useEffect, useState } from "react";
import { api } from "./api/client";
import type { SettingsInfo, TemplateInfo } from "./api/types";
import { ActivityPanel, type ActivityTab } from "./components/activity-panel";
import { ApprovalBar } from "./components/approval-bar";
import { Composer } from "./components/composer";
import { ConversationActivity } from "./components/conversation-activity";
import { ConversationHeader } from "./components/conversation-header";
import { ConversationList } from "./components/conversation-list";
import { ErrorBoundary } from "./components/error-boundary";
import { MessageThread } from "./components/message-thread";
import { SettingsPanel } from "./components/settings-panel";
import { StatusLine } from "./components/status-line";
import { useActivity } from "./hooks/use-activity";
import { useCrew } from "./hooks/use-agents";
import { useConversations } from "./hooks/use-conversations";
import { useThread } from "./hooks/use-thread";
import { vi } from "./i18n/vi";
import {
  conversationFamilyRuns,
  liveRuns,
  needsAttention,
  sortedRuns,
} from "./state/activity-reducer";

export function App() {
  const list = useConversations();
  const thread = useThread(list.activeId);
  const crew = useCrew();
  const activity = useActivity(true, list.applyUpdate);
  const [settings, setSettings] = useState<SettingsInfo | null>(null);
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [activityOpen, setActivityOpen] = useState(true);
  const [activityTab, setActivityTab] = useState<ActivityTab>("activity");
  const [draft, setDraft] = useState<string | undefined>(undefined);
  const [queued, setQueued] = useState<{ id: string; text: string } | null>(null);

  useEffect(() => {
    api.settings().then(setSettings, () => setSettings(null));
    api.templates().then(setTemplates, () => setTemplates([]));
  }, []);

  // A message typed before any conversation exists waits until the new one has loaded.
  const { send: threadSend, detail } = thread;
  useEffect(() => {
    if (queued && detail?.id === queued.id) {
      setQueued(null);
      void threadSend(queued.text);
    }
  }, [queued, detail?.id, threadSend]);

  // Each finished run changes the bill, the job history and per-conversation spend.
  const runs = sortedRuns(activity.state);
  const finished = runs.filter((r) => r.finished_at !== null).length;
  const { refreshJobs, refreshStats } = crew;
  const { refresh: refreshList } = list;
  useEffect(() => {
    if (finished === 0) return;
    void refreshJobs();
    void refreshStats();
    void refreshList();
  }, [finished, refreshJobs, refreshStats, refreshList]);

  const live = liveRuns(activity.state);
  const attention = needsAttention(activity.state);
  const liveByAgent: Record<string, number> = {};
  for (const run of live) liveByAgent[run.agent_id] = (liveByAgent[run.agent_id] ?? 0) + 1;

  // A delegate's conversation is not in the master's list; the loaded thread stands in for it.
  const active =
    list.conversations.find((c) => c.id === list.activeId) ??
    (thread.detail && thread.detail.id === list.activeId ? thread.detail : null);
  // `live` is newest-first, so the first match is the turn being waited on even
  // when an earlier run was left open.
  const activeRun = list.activeId ? (live.find((r) => r.conversation_id === list.activeId) ?? null) : null;
  // The chat's own activity: this conversation and whatever it handed to a delegate.
  const conversationRuns = list.activeId
    ? conversationFamilyRuns(activity.state, list.activeId)
    : [];
  const echoOnly = settings !== null && settings.providers.every((p) => p === "fake");
  const master = crew.master;
  const crewNames = (master?.delegates ?? []).map(crew.agentName);

  const send = async (text: string) => {
    if (list.activeId) return thread.send(text);
    const created = await list.create();
    if (created) setQueued({ id: created.id, text });
  };

  const rename = (title: string) => {
    if (!active) return;
    void list.patch(active.id, { title });
  };

  const remove = (id: string) => {
    if (window.confirm(vi.confirmDelete)) void list.remove(id);
  };

  const { state } = thread;
  const notice = state.notice && (
    <div className={`notice ${state.notice.kind}`} role="status" data-testid="notice">
      {state.notice.kind === "halted"
        ? state.notice.text === "budget"
          ? vi.haltedBudget
          : vi.haltedMaxSteps
        : state.notice.kind === "fallback"
          ? vi.routeFallback(state.notice.text)
          : vi.errorPrefix + state.notice.text}
    </div>
  );

  const activityButton = (
    <>
      <button
        type="button"
        className="ghost"
        aria-pressed={activityOpen && activityTab === "crew"}
        onClick={() => {
          setActivityTab("crew");
          setActivityOpen(true);
        }}
      >
        👥 {vi.crew.count(crewNames.length)}
      </button>
      <button
        type="button"
        className="ghost"
        aria-pressed={activityOpen}
        onClick={() => setActivityOpen((o) => !o)}
      >
        ◔ {vi.activity}
        {attention.length > 0 && <span className="badge warn"> {attention.length}</span>}
        {live.length > 0 && <span className="badge live"> {live.length}</span>}
      </button>
    </>
  );

  return (
    <div className={`layout ${activityOpen ? "with-activity" : ""}`}>
      <ConversationList
        conversations={list.conversations}
        activeId={list.activeId}
        onSelect={list.select}
        onCreate={() => void list.create()}
        onDelete={remove}
        top={
          master && (
            <div className="master-card" data-testid="master-card">
              <strong>{master.name}</strong>
              {(liveByAgent[master.id] ?? 0) > 0 && (
                <span className="badge live"> {liveByAgent[master.id]}</span>
              )}
              <div className="muted">{master.description || vi.crew.masterHint}</div>
            </div>
          )
        }
      />
      <main className="main">
        {active ? (
          <ConversationHeader
            conversation={active}
            agentName={crew.agentName(active.agent_id)}
            agent={crew.agents.find((a) => a.id === active.agent_id)}
            childCount={
              runs.filter((r) => r.source === `delegate:${active.id}`).length
            }
            spentUsd={state.spentUsd}
            unknownCostCalls={state.unknownCostCalls}
            skills={settings?.skills ?? []}
            onRename={rename}
            onSummarize={() => void list.summarize(active.id)}
            onToggleAutonomous={(value) => void list.patch(active.id, { autonomous: value })}
            onToggleSkill={(name, attached) => {
              const next = attached
                ? [...active.skills, name]
                : active.skills.filter((s) => s !== name);
              void list.patch(active.id, { skills: next });
            }}
            onRevokeAutoApprove={(name) =>
              void list.patch(active.id, { auto_approve: active.auto_approve.filter((n) => n !== name) })
            }
            onOpenSettings={() => setSettingsOpen(true)}
            extra={activityButton}
          />
        ) : (
          <header className="conversation-header">
            <h1>{vi.appName}</h1>
            <div className="header-controls">
              {activityButton}
              <button type="button" className="ghost" onClick={() => setSettingsOpen(true)}>
                ⚙ {vi.settings}
              </button>
            </div>
          </header>
        )}
        {list.error && <div className="notice error">{vi.loadFailed}</div>}
        {notice}
        <ErrorBoundary>
          <MessageThread
            items={state.items}
            streaming={state.streaming}
            busy={state.busy}
            liveRun={activeRun}
            echoOnly={echoOnly}
            agentId={active?.agent_id ?? "default"}
            agentName={crew.agentName}
            onOpenConversation={list.select}
            onSuggestion={(text) => setDraft(text)}
            masterName={master?.name}
            crewNames={crewNames}
          />
        </ErrorBoundary>
        {active && (
          <ErrorBoundary>
            <ConversationActivity
              runs={conversationRuns}
              conversationId={active.id}
              spentUsd={active.spent_usd}
              agentName={crew.agentName}
              onOpenConversation={list.select}
            />
          </ErrorBoundary>
        )}
        {state.pending && (
          <ApprovalBar
            pending={state.pending}
            busy={state.busy}
            onDecide={(ok) => void thread.decide(ok)}
            // The header shows the always-allow list from the conversation list, so refresh it.
            onAlways={() => void thread.decide(true, true).then(refreshList)}
          />
        )}
        {active?.over_budget && !state.busy && <div className="notice halted">{vi.overBudget}</div>}
        <Composer
          disabled={state.pending !== null}
          busy={state.busy}
          draft={draft}
          onSend={(text) => {
            setDraft(undefined);
            void send(text);
          }}
          onStop={thread.stop}
        />
        <StatusLine thread={state} connected={activity.state.connected} liveCount={live.length} />
      </main>
      {activityOpen && (
        <ErrorBoundary>
          <ActivityPanel
            runs={runs}
            liveRuns={live}
            attention={attention}
            jobs={crew.jobs}
            stats={crew.stats}
            agents={crew.agents}
            agentId={active?.agent_id ?? master?.id ?? "default"}
            agentName={crew.agentName}
            master={master}
            templates={templates}
            liveByAgent={liveByAgent}
            onInstall={crew.installTemplate}
            tab={activityTab}
            onTabChange={setActivityTab}
            onOpenConversation={list.select}
            onRunJob={(id) => void crew.runJob(id)}
            onToggleJob={(id, enabled) => void crew.setJobEnabled(id, enabled)}
            onClose={() => setActivityOpen(false)}
          />
        </ErrorBoundary>
      )}
      {settingsOpen && (
        <SettingsPanel settings={settings} agents={crew.agents} onClose={() => setSettingsOpen(false)} />
      )}
    </div>
  );
}
