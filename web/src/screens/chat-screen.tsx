import { useCallback, useEffect, useRef, useState } from "react";
import type { MessageCanvas } from "../api/artifact-types";
import type { AgentInfo, Conversation, RunInfo, SettingsInfo } from "../api/types";
import { ApprovalBar } from "../components/approval-bar";
import { RaiseCapButton } from "../components/budget-indicator";
import type { AskDisabled } from "../components/canvas/canvas-ask";
import { CanvasDockView } from "../components/canvas/canvas-dock";
import { CanvasButton, CanvasChatNotices } from "../components/canvas/canvas-dock-controls";
import { QuestionCard } from "../components/question-card";
import { Composer, type RestoreRequest } from "../components/composer";
import { ConversationActivity } from "../components/conversation-activity";
import { ConversationHeader } from "../components/conversation-header";
import { ConversationList } from "../components/conversation-list";
import { ErrorBoundary } from "../components/error-boundary";
import { MessageThread } from "../components/message-thread";
import { QueuedChips } from "../components/queued-chips";
import { StatusLine } from "../components/status-line";
import { AgentAvatar } from "../components/ui/agent-avatar";
import { Icon, type IconName } from "../components/ui/icon";
import type { useActivity } from "../hooks/use-activity";
import type { useCrew } from "../hooks/use-agents";
import { useCanvasAutoOpen } from "../hooks/use-canvas-auto-open";
import { useCanvasDock } from "../hooks/use-canvas-dock";
import { useCanvasFocus } from "../hooks/use-canvas-focus";
import { useCanvasWriting } from "../hooks/use-canvas-writing";
import type { useConversations } from "../hooks/use-conversations";
import { useDrawer } from "../hooks/use-drawer";
import { useFork } from "../hooks/use-fork";
import { useLivePreview } from "../hooks/use-live-preview";
import { useMediaQuery } from "../hooks/use-media-query";
import type { ManageSection } from "../hooks/use-route";
import { useSavingNote } from "../hooks/use-saving-note";
import { useShortcuts } from "../hooks/use-shortcuts";
import type { useThread } from "../hooks/use-thread";
import { vi } from "../i18n/vi";
import { dockShowing } from "../lib/canvas-dock-state";
import { runSummaryText } from "../lib/run-summary";
import type { SendResult } from "../lib/send-result";
import { conversationFamilyRuns, liveRuns, runningRuns, sortedRuns } from "../state/activity-reducer";
import type { ThreadItem } from "../state/thread-reducer";

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
  /** A run for this conversation that another channel started, while this tab streams nothing. */
  externalRun?: RunInfo | null;
}

/** The whole conversation: who you are talking to, what was said, what the agent is doing. */
// Wide enough to keep the conversation's activity open beside the chat. Matches the
// breakpoint in shell.css where the three-column layout folds back to two.
const DOCKED_ACTIVITY_QUERY = "(min-width: 1101px)";
// A phone: the conversation list stops being a column and slides over the chat instead.
// Matches the breakpoint in shell.css.
const PHONE_QUERY = "(max-width: 720px)";

const NOTICE_ICON: Record<string, IconName> = {
  fallback: "refresh",
  halted: "pause",
  stopped: "stop",
  handled: "info",
  elsewhere: "info",
};

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
  externalRun = null,
}: Props) {
  const [draft, setDraft] = useState<string | undefined>(undefined);
  const [queued, setQueued] = useState<{ id: string; text: string } | null>(null);
  // Text handed back to the composer from outside: a queueing POST that itself failed, or
  // words Stop pulled off the server's queue. `restoreNonce` is a plain counter rather than
  // `Date.now()` so two restores in the same millisecond (Stop, then a failed send right
  // after) still read as two distinct requests to the composer's own nonce check.
  const [restore, setRestore] = useState<RestoreRequest | null>(null);
  const restoreNonce = useRef(0);
  const restoreText = useCallback((text: string) => {
    restoreNonce.current += 1;
    setRestore({ nonce: restoreNonce.current, text });
  }, []);
  const searchRef = useRef<HTMLInputElement>(null);
  const [collapseSignal, setCollapseSignal] = useState(0);
  const phone = useMediaQuery(PHONE_QUERY);
  const drawer = useDrawer(phone);
  const { open: drawerOpen, show: showDrawer, hide: hideDrawer } = drawer;

  const { send: threadSend, detail } = thread;
  // A send waits for the canvas to be saved before it posts. By then the person may be in
  // another conversation, and this one may have become busy: it posts through what is current.
  const activeRef = useRef(list.activeId);
  activeRef.current = list.activeId;
  const sendRef = useRef(threadSend);
  sendRef.current = threadSend;
  // Only a send the server never took gives its words back: one it queued is held there and
  // shown as a chip, and one it began a turn for is on screen as a message.
  const sendOrRestore = useCallback(
    async (text: string) => {
      const result = await threadSend(text);
      if (result.status === "failed") restoreText(text);
    },
    [threadSend, restoreText],
  );
  // A message typed before any conversation exists waits until the new one has loaded.
  useEffect(() => {
    if (queued && detail?.id === queued.id) {
      setQueued(null);
      void sendOrRestore(queued.text);
    }
  }, [queued, detail?.id, sendOrRestore]);

  const runs = sortedRuns(activity.state);
  const live = liveRuns(activity.state);
  const running = runningRuns(activity.state).length;
  // A delegate's conversation is not in the master's list; the loaded thread stands in for it.
  const active: Conversation | null =
    list.conversations.find((c) => c.id === list.activeId) ??
    (thread.detail && thread.detail.id === list.activeId ? thread.detail : null);
  // Narrowed once here rather than at each use: `forked_from` is `string | undefined` on
  // the type (kept optional so ~15 existing fixtures need no edit), but empty and absent
  // mean the same thing — "not a fork" — so this also folds that into one falsy check.
  const forkSource = active?.forked_from || null;
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

  // Narrower than this, the activity is a strip under the thread and an open canvas covers
  // the chat column; wider, both share the column beside the chat.
  const wide = useMediaQuery(DOCKED_ACTIVITY_QUERY);
  const dock = useCanvasDock(active?.id ?? null, activity.state.connected, wide);
  const saving = useSavingNote();
  useCanvasFocus(active?.id ?? null, wide, dock);
  // A canvas the agent is still writing shows where the dock is without opening it, on a device
  // that has not turned that off. It comes first: the canvas it turns into is its to open, not
  // the hook's that opens what an agent made.
  const writing = useCanvasWriting(thread, dock, wide, useLivePreview().enabled);
  useCanvasAutoOpen(thread, dock, wide, writing.callId);
  const showing = writing.shown !== null;
  const { leave: leaveWriting } = writing;
  const { titleOf, isGone, verify } = dock.list;
  // Opening the canvas the dock already holds moves nothing, so a card pressed while a canvas
  // being written stands before it has to put that away itself.
  const openCanvas = (id: string) => {
    if (showing) leaveWriting();
    dock.open(id);
  };
  const canvasLinks = { titleOf, isGone, verify, open: openCanvas };

  // The composer keeps the words until this answers. A conversation that does not exist yet is
  // made first, and the words wait for it to load; one that does waits for the open canvas's
  // last save and goes with the canvas as it stands by then, which the chat says when that is
  // not what the person sees. `false` means nothing was sent:
  // the conversation could not be made, the person went to another one before the save landed,
  // or the server turned the message down before it began.
  const send = async (text: string): Promise<boolean> => {
    const id = list.activeId;
    if (!id) {
      const created = await create();
      if (created) setQueued({ id: created.id, text });
      return Boolean(created);
    }
    const unsaved = await saving.during(dock.flushForMessage());
    if (activeRef.current !== id) return false;
    const result = await sendRef.current(text, dock.messageCanvas());
    if (result.status !== "failed") dock.noteSentUnsaved(unsaved);
    return result.status !== "failed";
  };
  const dockOpen = dockShowing(dock.view, showing);
  const overlayOpen = !wide && dockOpen;
  const { close: closeDock } = dock;
  const canvasTrigger = useRef<HTMLButtonElement>(null);

  // A question about a passage of the open canvas. The panel has saved the canvas and names the
  // version, so this only posts it, to the conversation the person pressed Send in. A canvas that
  // covers the chat is put away once the server has taken the question, so that the answer shows.
  const ask = async (canvas: MessageCanvas, question: string): Promise<SendResult> => {
    const id = list.activeId;
    if (activeRef.current !== id) return { status: "failed", error: vi.canvas.ask.elsewhere };
    const result = await sendRef.current(question, canvas);
    // It went with the canvas as the panel saved it: the message that went unsaved is no longer the last.
    if (result.status !== "failed") dock.noteSentUnsaved(false);
    // Only the conversation the question went to has an overlay to put away.
    if (!wide && result.status !== "failed" && activeRef.current === id) void closeDock();
    return result;
  };

  // The search box only exists once the list is long enough to need it, so focusing it is
  // a request that can go unanswered — hence a ref that may hold nothing. On a phone it
  // lives in the drawer, which has to open around it first. Escape closes the topmost
  // layer only: the drawer, else a canvas being written that covers the chat, else a canvas
  // covering the chat (once its typing is saved), and only then the strip under the thread.
  useShortcuts({
    onSearch: useCallback(() => {
      const box = searchRef.current;
      if (box && phone && !drawerOpen) showDrawer(box);
      else box?.focus();
    }, [phone, drawerOpen, showDrawer]),
    onNew: useCallback(() => void create(), [create]),
    onEscape: useCallback(() => {
      if (drawerOpen) hideDrawer();
      else if (overlayOpen && showing) leaveWriting();
      else if (overlayOpen) void closeDock();
      else setCollapseSignal((n) => n + 1);
    }, [drawerOpen, hideDrawer, overlayOpen, showing, leaveWriting, closeDock]),
  });

  const remove = (id: string) => {
    if (window.confirm(vi.confirmDelete)) void list.remove(id);
  };

  const { state } = thread;
  // Why a question about a passage cannot go now, which the ask bar says in words. A turn that
  // is running comes first: the passage would be of a canvas the agent is still changing.
  const askDisabled: AskDisabled =
    state.busy || externalRun !== null
      ? "busy"
      : state.pending !== null
        ? "pending"
        : active?.over_budget
          ? "budget"
          : null;
  // One way to change the cap, shared by the budget card and both budget notices. A
  // delegate's conversation is not in the list, so only its reloaded thread shows the cap.
  const onRaiseCap = async (cost_cap_usd: number) => {
    if (!active) return;
    await list.patch(active.id, { cost_cap_usd });
    if (active === thread.detail) await thread.reload();
  };
  // One way out of a spent budget on screen at a time: the over-budget notice carries it
  // while it shows, and the halt's notice until then — only while the cap still stands at
  // what was spent, so a raise takes it away and the halt's notice says to send again.
  const overBudget = Boolean(active?.over_budget) && !state.busy;
  const capReached = active !== null && active.cost_cap_usd > 0 && state.spentUsd >= active.cost_cap_usd;
  // Stop can reach three different things: this tab's own running turn, a message still
  // only sitting in the queue with nothing running yet, or a turn another chat tab or the
  // Telegram channel started. Only the last of those needs asking the server whether
  // anything was even there to stop — `chat` and `api` are the sources a person, not a
  // schedule or a delegate, could plausibly be running from right now.
  const stoppable =
    state.busy ||
    state.waiting.length > 0 ||
    (externalRun !== null && ["chat", "api"].includes(externalRun.source));
  const onStop = async () => {
    const cleared = await thread.stop(externalRun !== null);
    if (cleared.length > 0) restoreText(cleared.join("\n\n"));
  };
  // A raise from a notice often takes the notice, or its button, away with the control
  // the keyboard was on. Once the screen has caught up, the keyboard goes where the person
  // carries on: the composer when the raise let it write, or the raise still on offer.
  const mainRef = useRef<HTMLElement>(null);
  const [afterRaise, setAfterRaise] = useState(0);
  const raiseFromNotice = async (cost_cap_usd: number) => {
    await onRaiseCap(cost_cap_usd);
    setAfterRaise((n) => n + 1);
  };
  useEffect(() => {
    if (afterRaise === 0) return;
    mainRef.current
      ?.querySelector<HTMLElement>(".composer textarea:not(:disabled), [data-testid=over-budget] > .link-button")
      ?.focus();
  }, [afterRaise]);
  // Rewinds and forks the conversation at a saved user message. The list is refreshed and
  // the fork selected inside the hook itself; this screen only has to move focus into the
  // composer afterwards, the same way a cap raise does — the fork's own draft is already
  // seeded by the time `onSelectConversation` switches `draftKey` onto it.
  const { refresh: listRefresh } = list;
  const fork = useFork({ activeId: list.activeId, refresh: listRefresh, onSelectConversation });
  const [afterFork, setAfterFork] = useState(0);
  const { items: threadItems } = state;
  const onFork = useCallback(
    (item: ThreadItem) => {
      if (!active) return;
      void fork.fork(active.id, item, threadItems).then((ok) => {
        if (ok) setAfterFork((n) => n + 1);
      });
    },
    [active, fork, threadItems],
  );
  useEffect(() => {
    if (afterFork === 0) return;
    mainRef.current?.querySelector<HTMLElement>(".composer textarea:not(:disabled)")?.focus();
  }, [afterFork]);
  const notice = state.notice && (
    <div className={`notice ${state.notice.kind}`} role="status" data-testid="notice">
      <Icon name={NOTICE_ICON[state.notice.kind] ?? "alert"} />
      {state.notice.kind === "halted"
        ? state.notice.text === "budget"
          ? overBudget || capReached
            ? vi.haltedBudget
            : vi.haltedBudgetLifted
          : runSummaryText({ status: "halted", summary: state.notice.text })
        : state.notice.kind === "fallback"
          ? vi.routeFallback(state.notice.text)
          : state.notice.kind === "stopped"
            ? vi.stopped
            : state.notice.kind === "handled"
              ? vi.attentionHandled
              : state.notice.kind === "elsewhere"
                ? vi.stopElsewhere
                : vi.errorPrefix + state.notice.text}
      {state.notice.kind === "halted" && state.notice.text === "budget" && active && !overBudget && capReached && (
        <RaiseCapButton capUsd={active.cost_cap_usd} onSave={raiseFromNotice} />
      )}
    </div>
  );

  // The one way out of the chat, so it carries the counts that would otherwise need
  // a rail to be visible: work waiting on a person, and work under way.
  const manageButton = (
    <button type="button" className="ghost manage-button" onClick={() => onOpenManage()}>
      <Icon name="grid" />
      {vi.manage.open}
      {attentionCount > 0 && <span className="badge warn"> {attentionCount}</span>}
      {running > 0 && <span className="badge live"> {running}</span>}
    </button>
  );

  // Who is available to take work on, right where the person decides whether to ask for
  // it. It only counts them; changing the team is the manage screen's job.
  const crewChip = (
    <button type="button" className="pill" onClick={() => onOpenManage("crew")}>
      <Icon name="users" />
      {vi.crew.count(crewNames.length)}
    </button>
  );

  // On a phone the list is a drawer, and this is the way to it. Work waiting on a person
  // lives behind the drawer too (on the manage button at its foot), so the button carries
  // a dot for it rather than letting that count go out of sight — and says it in words,
  // since a dot is only there for the eye.
  const menuButton = phone && (
    <button
      type="button"
      className="icon-button menu-button"
      ref={drawer.triggerRef}
      aria-label={
        attentionCount > 0
          ? `${vi.openConversations} (${vi.manage.waiting(attentionCount)})`
          : vi.openConversations
      }
      aria-expanded={drawer.open}
      onClick={() => showDrawer()}
    >
      <Icon name="menu" />
      {attentionCount > 0 && <span className="menu-dot" aria-hidden="true" />}
    </button>
  );

  // A narrow screen keeps the one-line strip under the thread instead of the column.
  const docked = wide && Boolean(active);
  const activityPane = active && (
    <ErrorBoundary>
      <ConversationActivity
        runs={conversationRuns}
        conversationId={active.id}
        spentUsd={active.spent_usd}
        capUsd={active.cost_cap_usd}
        agentName={crew.agentName}
        onOpenConversation={onSelectConversation}
        collapseSignal={collapseSignal}
        docked={docked}
      />
    </ErrorBoundary>
  );

  return (
    <div className={`layout${docked ? (dockOpen ? " with-canvas" : " with-activity") : ""}`}>
      {drawer.open && <div className="scrim" aria-hidden="true" onClick={drawer.hide} />}
      <ConversationList
        conversations={list.conversations}
        activeId={list.activeId}
        onSelect={onSelectConversation}
        onCreate={() => void create()}
        onDelete={remove}
        searchRef={searchRef}
        drawer={phone ? { open: drawer.open, close: drawer.hide, ref: drawer.panelRef } : undefined}
        liveRuns={live}
        agentName={crew.agentName}
        top={
          master && (
            <div className="master-card" data-testid="master-card">
              <AgentAvatar id={master.id} name={master.name} size="lg" />
              <div className="master-text">
                <div className="master-name">
                  <strong>{master.name}</strong>
                  {(liveByAgent[master.id] ?? 0) > 0 && (
                    <span className="badge live"> {liveByAgent[master.id]}</span>
                  )}
                </div>
                <div className="muted">{master.description || vi.crew.masterHint}</div>
              </div>
            </div>
          )
        }
        bottom={manageButton}
      />
      {/* The open drawer is modal, and so is a canvas covering the chat: what either covers
          takes no focus and reads as absent. */}
      <main className="main" ref={mainRef} inert={drawer.open || overlayOpen || undefined}>
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
            onSetCap={onRaiseCap}
            first={<CanvasButton dock={dock} ref={canvasTrigger} showing={showing} onLeave={leaveWriting} />}
            extra={crewChip}
            lead={menuButton}
            sourceTitle={list.conversations.find((c) => c.id === forkSource)?.title}
            onOpenSource={forkSource ? () => onSelectConversation(forkSource) : undefined}
          />
        ) : (
          <header className="conversation-header">
            <div className="header-row">
              <div className="header-title">
                {menuButton}
                <h1>{vi.appName}</h1>
              </div>
              <div className="header-controls">{crewChip}</div>
            </div>
          </header>
        )}
        {list.error && (
          <div className="notice error">
            <Icon name="alert" />
            {vi.loadFailed}
          </div>
        )}
        {fork.error && (
          <div className="notice error" data-testid="fork-error">
            <Icon name="alert" />
            {fork.error}
          </div>
        )}
        <CanvasChatNotices dock={dock} />
        {notice}
        <ErrorBoundary>
          <MessageThread
            items={state.items}
            streaming={state.streaming}
            // A run started from another channel shows its progress the same way, so the
            // thread does not look idle while an answer is on its way.
            busy={state.busy || externalRun !== null}
            liveRun={activeRun}
            echoOnly={echoOnly}
            agentId={active?.agent_id ?? "default"}
            agentName={crew.agentName}
            onOpenConversation={onSelectConversation}
            canvas={canvasLinks}
            writing={{ items: writing.items, onShow: writing.show }}
            onSuggestion={(text) => setDraft(text)}
            masterName={master?.name}
            crewNames={crewNames}
            // A delegate's own conversation (`parent_call_id` set) is not a valid fork
            // source — the server rejects it with 400 — so the button is withheld there
            // rather than offering something that would only fail on click.
            onFork={active && !active.parent_call_id ? onFork : undefined}
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
            // Withheld whenever a reason stopped the call: that pause cannot be waived (see
            // `tool_gate.needs_decision`), so always-allowing the tool here would not stop
            // this card coming back — it would only let the tool's other calls run unasked.
            // The header shows the always-allow list from the conversation list, so refresh it.
            onAlways={
              state.pending.reason ? undefined : () => void thread.decide(true, true).then(list.refresh)
            }
          />
        )}
        {overBudget && active && (
          <div className="notice halted" data-testid="over-budget">
            <Icon name="coins" />
            {vi.overBudget}
            <RaiseCapButton capUsd={active.cost_cap_usd} onSave={raiseFromNotice} />
          </div>
        )}
        <QueuedChips items={state.waiting} />
        <Composer
          // Anything pending blocks the composer, question included: the server refuses a
          // new message while an approval waits, so an enabled box would only collect text
          // and then 409. The question card carries its own input for the reply. A spent
          // budget blocks it too: the server would halt the turn before it started.
          disabled={state.pending !== null || Boolean(active?.over_budget)}
          busy={state.busy || externalRun !== null}
          stoppable={stoppable}
          restore={restore}
          note={saving.shown ? vi.canvas.savingFirst : undefined}
          draft={draft}
          draftKey={list.activeId ?? "new"}
          agentName={active ? crew.agentName(active.agent_id) : master?.name}
          commands={(active ? crew.agents.find((a) => a.id === active.agent_id) : master)?.commands ?? []}
          onSend={(text) => {
            setDraft(undefined);
            return send(text);
          }}
          onStop={() => void onStop()}
        />
        <StatusLine
          thread={state}
          connected={activity.state.connected}
          liveCount={running}
          connecting={activity.connecting}
          onReconnect={activity.reconnect}
          overBudget={overBudget}
        />
      </main>
      <CanvasDockView
        dock={dock}
        mode={wide ? "column" : "overlay"}
        activity={docked ? activityPane : null}
        connected={activity.state.connected}
        agentName={crew.agentName}
        trigger={canvasTrigger}
        onAsk={ask}
        askDisabled={askDisabled}
        writing={writing.shown && { item: writing.shown, asked: writing.asked, onLeave: leaveWriting }}
      />
    </div>
  );
}
