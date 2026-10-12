import { useCallback, useRef, useState } from "react";
import type { AgentInfo, Conversation } from "../api/types";
import { CanvasDockView } from "../components/canvas/canvas-dock";
import { CanvasChatNotices } from "../components/canvas/canvas-dock-controls";
import { QueuedChips } from "../components/queued-chips";
import { StatusLine } from "../components/status-line";
import { useDrawer } from "../hooks/use-drawer";
import { useMediaQuery } from "../hooks/use-media-query";
import { vi } from "../i18n/vi";
import { dockShowing } from "../lib/canvas-dock-state";
import { conversationFamilyRuns, liveRuns, runningRuns, sortedRuns } from "../state/activity-reducer";
import { conversationMoney } from "../state/conversation-money";
import { chatApproval, chatComposer, chatQuestion } from "./chat/chat-composer";
import { chatCrewChip, chatHeader, chatMenuButton } from "./chat/chat-header";
import { chatNotice, forkErrorNotice, loadFailedNotice, overBudgetNotice } from "./chat/chat-notices";
import type { ChatProps } from "./chat/chat-props";
import { chatAsk, chatSend } from "./chat/chat-send";
import { chatManageButton, chatSidebar } from "./chat/chat-sidebar";
import { chatStanding } from "./chat/chat-standing";
import { chatActivityPane, chatThread } from "./chat/chat-thread";
import { useChatCanvas } from "./chat/use-chat-canvas";
import { useChatFork } from "./chat/use-chat-fork";
import { useChatShortcuts } from "./chat/use-chat-shortcuts";
import { useFocusAfterRaise } from "./chat/use-focus-after-raise";
import { useQueuedSend } from "./chat/use-queued-send";
import { useRestoreText } from "./chat/use-restore-text";

/** The whole conversation: who you are talking to, what was said, what the agent is doing. */
// A phone: the conversation list stops being a column and slides over the chat instead.
// Matches the breakpoint in shell-responsive.css.
const PHONE_QUERY = "(max-width: 720px)";

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
}: ChatProps) {
  const [draft, setDraft] = useState<string | undefined>(undefined);
  const [queued, setQueued] = useState<{ id: string; text: string } | null>(null);
  const { restore, restoreText } = useRestoreText();
  const searchRef = useRef<HTMLInputElement>(null);
  const [collapseSignal, setCollapseSignal] = useState(0);
  const phone = useMediaQuery(PHONE_QUERY);
  const drawer = useDrawer(phone);
  const { open: drawerOpen, show: showDrawer, hide: hideDrawer } = drawer;

  const { activeRef, sendRef } = useQueuedSend({ list, thread, queued, setQueued, restoreText });

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

  const { wide, dock, saving, writing, showing, leaveWriting, canvasLinks } = useChatCanvas({ thread, activity, active });
  const send = chatSend({ list, create, setQueued, saving, dock, activeRef, sendRef });
  const dockOpen = dockShowing(dock.view, showing);
  const overlayOpen = !wide && dockOpen;
  const { close: closeDock } = dock;
  const canvasTrigger = useRef<HTMLButtonElement>(null);

  const ask = chatAsk({ list, dock, wide, closeDock, activeRef, sendRef });

  useChatShortcuts({
    searchRef, phone, drawerOpen, showDrawer, hideDrawer, create, overlayOpen, showing, leaveWriting, closeDock, setCollapseSignal,
  });

  const remove = (id: string) => {
    if (window.confirm(vi.confirmDelete)) void list.remove(id);
  };

  const { state } = thread;
  const money = active && conversationMoney(active, active !== thread.detail, state);
  const { askDisabled, overBudget, stoppable } = chatStanding({ thread, externalRun, money });
  // One way to change the cap, shared by the budget card and both budget notices. A
  // delegate's conversation is not in the list, so only its reloaded thread shows the cap.
  const onRaiseCap = async (cost_cap_usd: number) => {
    if (!active) return;
    await list.patch(active.id, { cost_cap_usd });
    if (active === thread.detail) await thread.reload();
  };
  const onStop = async () => {
    const cleared = await thread.stop(externalRun !== null);
    if (cleared.length > 0) restoreText(cleared.join("\n\n"));
  };
  const { mainRef, raiseFromNotice } = useFocusAfterRaise(onRaiseCap);
  const { fork, onFork } = useChatFork({ list, onSelectConversation, state, active, mainRef });
  const notice = chatNotice({ state, money, active, overBudget, raiseFromNotice });
  const manageButton = chatManageButton({ onOpenManage, attentionCount, running });
  const crewChip = chatCrewChip({ onOpenManage, crewNames });
  const menuButton = chatMenuButton({ phone, drawer, showDrawer, attentionCount });

  // A narrow screen keeps the one-line strip under the thread instead of the column.
  const docked = wide && Boolean(active);
  const activityPane = chatActivityPane({ crew, onSelectConversation, active, conversationRuns, money, collapseSignal, docked });

  // The screen's parts are functions called in this render, not components: none has state or
  // effects of its own, and the tree is what their JSX makes written out here.
  return (
    <div className={`layout${docked ? (dockOpen ? " with-canvas" : " with-activity") : ""}`}>
      {drawer.open && <div className="scrim" aria-hidden="true" onClick={drawer.hide} />}
      {chatSidebar({
        list, crew, liveByAgent, onSelectConversation, master, live, phone, drawer, searchRef, create, remove, manageButton,
      })}
      {/* The open drawer is modal, and so is a canvas covering the chat: what either covers
          takes no focus and reads as absent. */}
      <main className="main" ref={mainRef} inert={drawer.open || overlayOpen || undefined}>
        {chatHeader({
          list, crew, settings, onSelectConversation, active, forkSource, runs, money, state, onRaiseCap,
          dock, canvasTrigger, showing, leaveWriting, crewChip, menuButton,
        })}
        {loadFailedNotice(list)}
        {forkErrorNotice(fork)}
        <CanvasChatNotices dock={dock} />
        {notice}
        {chatThread({
          crew, onSelectConversation, state, externalRun, activeRun, echoOnly, active, canvasLinks, writing, setDraft,
          master, crewNames, onFork,
        })}
        {!docked && activityPane}
        {chatQuestion({ state, thread })}
        {chatApproval({ state, thread, list })}
        {overBudgetNotice({ overBudget, active, raiseFromNotice })}
        <QueuedChips items={state.waiting} />
        {chatComposer({
          list, crew, state, money, externalRun, stoppable, restore, saving, draft, setDraft, active, master, send, onStop,
        })}
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
