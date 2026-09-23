import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentInfo, Conversation, SettingsInfo } from "../api/types";
import { ApprovalBar } from "../components/approval-bar";
import { QuestionCard } from "../components/question-card";
import { Composer } from "../components/composer";
import { ConversationActivity } from "../components/conversation-activity";
import { ConversationHeader } from "../components/conversation-header";
import { ConversationList } from "../components/conversation-list";
import { ErrorBoundary } from "../components/error-boundary";
import { MessageThread } from "../components/message-thread";
import { StatusLine } from "../components/status-line";
import type { useActivity } from "../hooks/use-activity";
import type { useCrew } from "../hooks/use-agents";
import type { useConversations } from "../hooks/use-conversations";
import { useMediaQuery } from "../hooks/use-media-query";
import type { ManageSection } from "../hooks/use-route";
import { useShortcuts } from "../hooks/use-shortcuts";
import type { useThread } from "../hooks/use-thread";
import { vi } from "../i18n/vi";
import { conversationFamilyRuns, liveRuns, sortedRuns } from "../state/activity-reducer";

interface Props {
  list: ReturnType<typeof useConversations>;
  thread: ReturnType<typeof useThread>;
  crew: ReturnType<typeof useCrew>;
  activity: ReturnType<typeof useActivity>;
  settings: SettingsInfo | null;
  /** How many runs across the crew are waiting on a person; opens the manage screen. */
  attentionCount: number;
  /** Selects a conversation and puts it in the address bar, so the link can be shared. */
  onSelectConversation: (conversationId: string) => void;
  onOpenManage: (section?: ManageSection) => void;
  liveByAgent: Record<string, number>;
}

/** The whole conversation: who you are talking to, what was said, what the agent is doing. */
// Wide enough to keep the conversation's activity open beside the chat. Matches the
// breakpoint in shell.css where the three-column layout folds back to two.
const DOCKED_ACTIVITY_QUERY = "(min-width: 1101px)";

export function ChatScreen({
  list,
  thread,
  crew,
  activity,
  settings,
  attentionCount,
  onSelectConversation,
  onOpenManage,
  liveByAgent,
}: Props) {
  const [draft, setDraft] = useState<string | undefined>(undefined);
  const [queued, setQueued] = useState<{ id: string; text: string } | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [collapseSignal, setCollapseSignal] = useState(0);

  // A message typed before any conversation exists waits until the new one has loaded.
  const { send: threadSend, detail } = thread;
  useEffect(() => {
    if (queued && detail?.id === queued.id) {
      setQueued(null);
      void threadSend(queued.text);
    }
  }, [queued, detail?.id, threadSend]);

  const runs = sortedRuns(activity.state);
  const live = liveRuns(activity.state);
  // A delegate's conversation is not in the master's list; the loaded thread stands in for it.
  const active: Conversation | null =
    list.conversations.find((c) => c.id === list.activeId) ??
    (thread.detail && thread.detail.id === list.activeId ? thread.detail : null);
  // `live` is newest-first, so the first match is the turn being waited on even
  // when an earlier run was left open.
  const activeRun = list.activeId
    ? (live.find((r) => r.conversation_id === list.activeId) ?? null)
    : null;
  // The chat's own activity: this conversation and whatever it handed to a delegate.
  const conversationRuns = list.activeId
    ? conversationFamilyRuns(activity.state, list.activeId)
    : [];
  const echoOnly = settings !== null && settings.providers.every((p) => p === "fake");
  const master: AgentInfo | null = crew.master;
  const crewNames = (master?.delegates ?? []).map(crew.agentName);

  // A new conversation is somewhere the person now is, so it belongs in the address bar
  // as much as one they picked from the list.
  const { create: listCreate } = list;
  const create = useCallback(async () => {
    const created = await listCreate();
    if (created) onSelectConversation(created.id);
    return created;
  }, [listCreate, onSelectConversation]);

  const send = async (text: string) => {
    if (list.activeId) return thread.send(text);
    const created = await create();
    if (created) setQueued({ id: created.id, text });
  };

  // The search box only exists once the list is long enough to need it, so focusing it is
  // a request that can go unanswered — hence a ref that may hold nothing.
  useShortcuts({
    onSearch: useCallback(() => searchRef.current?.focus(), []),
    onNew: useCallback(() => void create(), [create]),
    onEscape: useCallback(() => setCollapseSignal((n) => n + 1), []),
  });

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

  // The one way out of the chat, so it carries the counts that would otherwise need
  // a rail to be visible: work waiting on a person, and work under way.
  const manageButton = (
    <button type="button" className="ghost manage-button" onClick={() => onOpenManage()}>
      ⚙ {vi.manage.open}
      {attentionCount > 0 && <span className="badge warn"> {attentionCount}</span>}
      {live.length > 0 && <span className="badge live"> {live.length}</span>}
    </button>
  );

  // Who is available to take work on, right where the person decides whether to ask for
  // it. It only counts them; changing the team is the manage screen's job.
  const crewChip = (
    <button type="button" className="ghost" onClick={() => onOpenManage("crew")}>
      👥 {vi.crew.count(crewNames.length)}
    </button>
  );

  // A narrow screen keeps the one-line strip under the thread instead of the column.
  const wide = useMediaQuery(DOCKED_ACTIVITY_QUERY);
  const docked = wide && Boolean(active);
  const activityPane = active && (
    <ErrorBoundary>
      <ConversationActivity
        runs={conversationRuns}
        conversationId={active.id}
        spentUsd={active.spent_usd}
        agentName={crew.agentName}
        onOpenConversation={onSelectConversation}
        collapseSignal={collapseSignal}
        docked={docked}
      />
    </ErrorBoundary>
  );

  return (
    <div className={`layout${docked ? " with-activity" : ""}`}>
      <ConversationList
        conversations={list.conversations}
        activeId={list.activeId}
        onSelect={onSelectConversation}
        onCreate={() => void create()}
        onDelete={remove}
        searchRef={searchRef}
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
        bottom={manageButton}
      />
      <main className="main">
        {active ? (
          <ConversationHeader
            conversation={active}
            agentName={crew.agentName(active.agent_id)}
            agent={crew.agents.find((a) => a.id === active.agent_id)}
            childCount={runs.filter((r) => r.source === `delegate:${active.id}`).length}
            spentUsd={state.spentUsd}
            unknownCostCalls={state.unknownCostCalls}
            skills={settings?.skills ?? []}
            onRename={(title) => void list.patch(active.id, { title })}
            onSummarize={() => void list.summarize(active.id)}
            onToggleAutonomous={(value) => void list.patch(active.id, { autonomous: value })}
            onToggleSkill={(name, attached) => {
              const next = attached
                ? [...active.skills, name]
                : active.skills.filter((s) => s !== name);
              void list.patch(active.id, { skills: next });
            }}
            onRevokeAutoApprove={(name) =>
              void list.patch(active.id, {
                auto_approve: active.auto_approve.filter((n) => n !== name),
              })
            }
            onOpenSettings={() => onOpenManage("settings")}
            extra={crewChip}
          />
        ) : (
          <header className="conversation-header">
            <h1>{vi.appName}</h1>
            {/* No manage button here: the sidebar's is always on screen, and two of them
                would leave the person guessing whether they do the same thing. */}
            <div className="header-controls">{crewChip}</div>
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
            onOpenConversation={onSelectConversation}
            onSuggestion={(text) => setDraft(text)}
            masterName={master?.name}
            crewNames={crewNames}
          />
        </ErrorBoundary>
        {!docked && activityPane}
        {state.pending?.kind === "question" && (
          <QuestionCard
            pending={state.pending}
            busy={state.busy}
            onAnswer={(text) => void thread.answer(text)}
          />
        )}
        {state.pending && state.pending.kind !== "question" && (
          <ApprovalBar
            pending={state.pending}
            busy={state.busy}
            onDecide={(ok) => void thread.decide(ok)}
            // The header shows the always-allow list from the conversation list, so refresh it.
            onAlways={() => void thread.decide(true, true).then(list.refresh)}
          />
        )}
        {active?.over_budget && !state.busy && <div className="notice halted">{vi.overBudget}</div>}
        <Composer
          // Anything pending blocks the composer, question included: the server refuses a
          // new message while an approval waits, so an enabled box would only collect text
          // and then 409. The question card carries its own input for the reply.
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
      {docked && activityPane}
    </div>
  );
}
