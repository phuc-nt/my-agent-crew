import type { ReactNode, RefObject } from "react";
import type { Conversation, RunInfo } from "../../api/types";
import { CanvasButton } from "../../components/canvas/canvas-dock-controls";
import { ConversationHeader } from "../../components/conversation-header";
import { SpendChip } from "../../components/spend-chip";
import { Icon } from "../../components/ui/icon";
import type { CanvasDock } from "../../hooks/use-canvas-dock";
import type { useDrawer } from "../../hooks/use-drawer";
import { vi } from "../../i18n/vi";
import type { ConversationMoney } from "../../state/conversation-money";
import type { ThreadState } from "../../state/thread-reducer";
import type { ChatProps } from "./chat-props";

type Drawer = ReturnType<typeof useDrawer>;

export function chatCrewChip({ onOpenManage, crewNames }: Pick<ChatProps, "onOpenManage"> & { crewNames: string[] }) {
  // Who is available to take work on, right where the person decides whether to ask for
  // it. It only counts them; changing the team is the manage screen's job.
  return (
    <button type="button" className="pill" onClick={() => onOpenManage("crew")}>
      <Icon name="users" />
      {vi.crew.count(crewNames.length)}
    </button>
  );
}

interface MenuButtonParts extends Pick<ChatProps, "attentionCount"> {
  phone: boolean;
  drawer: Drawer;
  showDrawer: Drawer["show"];
}

export function chatMenuButton({ phone, drawer, showDrawer, attentionCount }: MenuButtonParts) {
  // On a phone the list is a drawer, and this is the way to it. Work waiting on a person
  // lives behind the drawer too (on the manage button at its foot), so the button carries
  // a dot for it rather than letting that count go out of sight — and says it in words,
  // since a dot is only there for the eye.
  return phone && (
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
}

/**
 * On a phone, the way to the inbox: what waits on the person and what the jobs reported,
 * read the way a chat app's notifications are. The count is both — a request to settle or
 * a failure to read, and a result not yet seen — since each is a reason to open it.
 */
export function chatInboxButton({ phone, count, onOpenInbox }: { phone: boolean; count: number; onOpenInbox?: () => void }) {
  return phone && onOpenInbox && (
    <button
      type="button"
      className="icon-button inbox-button"
      aria-label={count > 0 ? vi.inbox.openWith(count) : vi.inbox.open}
      onClick={onOpenInbox}
    >
      <Icon name="inbox" />
      {count > 0 && (
        <span className="inbox-count" aria-hidden="true" data-testid="inbox-count">
          {count > 9 ? "9+" : count}
        </span>
      )}
    </button>
  );
}

interface HeaderParts extends Pick<ChatProps, "list" | "crew" | "settings" | "onSelectConversation"> {
  active: Conversation | null;
  forkSource: string | null;
  runs: RunInfo[];
  money: ConversationMoney | null;
  state: ThreadState;
  onRaiseCap: (cost_cap_usd: number) => Promise<void>;
  dock: CanvasDock;
  canvasTrigger: RefObject<HTMLButtonElement | null>;
  showing: boolean;
  leaveWriting: () => void;
  crewChip: ReactNode;
  menuButton: ReactNode;
  /** A phone: the header folds to its title row. */
  compact: boolean;
}

/** The head of the chat column: the open conversation's, or the app's name while there is none. */
export function chatHeader({
  list,
  crew,
  settings,
  onSelectConversation,
  active,
  forkSource,
  runs,
  money,
  state,
  onRaiseCap,
  dock,
  canvasTrigger,
  showing,
  leaveWriting,
  crewChip,
  menuButton,
  compact,
}: HeaderParts) {
  return active ? (
    <ConversationHeader
      conversation={active}
      agentName={crew.agentName(active.agent_id)}
      agent={crew.agents.find((a) => a.id === active.agent_id)}
      childCount={runs.filter((r) => r.source === `delegate:${active.id}`).length}
      spentUsd={money?.spentUsd ?? 0}
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
      first={
        <>
          <CanvasButton dock={dock} ref={canvasTrigger} showing={showing} onLeave={leaveWriting} />
          {/* A phone folds the controls away; the month's spend stays on the title row. */}
          {compact && <SpendChip compact />}
        </>
      }
      extra={
        <>
          {!compact && <SpendChip />}
          {crewChip}
        </>
      }
      lead={menuButton}
      compact={compact}
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
        <div className="header-controls">
          <SpendChip />
          {crewChip}
        </div>
      </div>
    </header>
  );
}
