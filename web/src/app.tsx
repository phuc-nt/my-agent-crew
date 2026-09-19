import { useEffect, useState } from "react";
import { api } from "./api/client";
import type { SettingsInfo } from "./api/types";
import { ActivityPanel } from "./components/activity-panel";
import { AgentSwitcher } from "./components/agent-switcher";
import { ApprovalBar } from "./components/approval-bar";
import { Composer } from "./components/composer";
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
import { liveRuns, needsAttention, sortedRuns } from "./state/activity-reducer";

export function App() {
  const list = useConversations();
  const thread = useThread(list.activeId);
  const crew = useCrew();
  const activity = useActivity();
  const [settings, setSettings] = useState<SettingsInfo | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [activityOpen, setActivityOpen] = useState(true);
  const [draft, setDraft] = useState<string | undefined>(undefined);
  const [queued, setQueued] = useState<{ id: string; text: string } | null>(null);

  useEffect(() => {
    api.settings().then(setSettings, () => setSettings(null));
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

  const active = list.conversations.find((c) => c.id === list.activeId) ?? null;
  const echoOnly = settings !== null && settings.providers.every((p) => p === "fake");

  const send = async (text: string) => {
    if (list.activeId) return thread.send(text);
    const created = await list.create();
    if (created) setQueued({ id: created.id, text });
  };

  const rename = () => {
    if (!active) return;
    const title = window.prompt(vi.renamePrompt, active.title);
    if (title && title !== active.title) void list.patch(active.id, { title });
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
        : vi.errorPrefix + state.notice.text}
    </div>
  );

  const activityButton = (
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
          <AgentSwitcher
            agents={crew.agents}
            selectedId={list.agentId}
            liveByAgent={liveByAgent}
            onSelect={list.selectAgent}
          />
        }
      />
      <main className="main">
        {active ? (
          <ConversationHeader
            conversation={active}
            agentName={crew.agentName(active.agent_id)}
            spentUsd={state.spentUsd}
            unknownCostCalls={state.unknownCostCalls}
            skills={settings?.skills ?? []}
            onRename={rename}
            onToggleAutonomous={(value) => void list.patch(active.id, { autonomous: value })}
            onToggleSkill={(name, attached) => {
              const next = attached
                ? [...active.skills, name]
                : active.skills.filter((s) => s !== name);
              void list.patch(active.id, { skills: next });
            }}
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
            echoOnly={echoOnly}
            agentId={active?.agent_id ?? "default"}
            onSuggestion={(text) => setDraft(text)}
          />
        </ErrorBoundary>
        {state.pending && (
          <ApprovalBar pending={state.pending} busy={state.busy} onDecide={(ok) => void thread.decide(ok)} />
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
            conversationId={list.activeId}
            jobs={crew.jobs}
            stats={crew.stats}
            agentName={crew.agentName}
            onOpenConversation={list.select}
            onRunJob={(id) => void crew.runJob(id)}
            onClose={() => setActivityOpen(false)}
          />
        </ErrorBoundary>
      )}
      {settingsOpen && <SettingsPanel settings={settings} onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}
