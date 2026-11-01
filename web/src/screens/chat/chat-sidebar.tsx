import type { ReactNode, RefObject } from "react";
import type { AgentInfo, RunInfo } from "../../api/types";
import { ConversationList } from "../../components/conversation-list";
import { AgentAvatar } from "../../components/ui/agent-avatar";
import { Icon } from "../../components/ui/icon";
import type { useDrawer } from "../../hooks/use-drawer";
import { vi } from "../../i18n/vi";
import type { ChatProps } from "./chat-props";

interface ManageButtonParts extends Pick<ChatProps, "onOpenManage" | "attentionCount"> {
  /** Of `attentionCount`, the requests waiting on a decision; the rest are unread failures. */
  waiting: number;
  running: number;
}

export function chatManageButton({ onOpenManage, attentionCount, waiting, running }: ManageButtonParts) {
  // The one way out of the chat, so it carries the counts that would otherwise need
  // a rail to be visible: work waiting on a person, and work under way. A decision and a
  // failure to read are counted apart, as the manage nav counts them: one number for both
  // would not say whether something is held up until the person answers.
  const failed = attentionCount - waiting;
  const count = (n: number, tone: string, says: string, testId?: string) => (
    <span className={`badge ${tone}`} data-testid={testId}>
      {` ${n}`}
      <span className="sr-only"> {says}</span>
    </span>
  );
  return (
    <button type="button" className="ghost manage-button" onClick={() => onOpenManage()}>
      <Icon name="grid" />
      {vi.manage.open}
      {waiting > 0 && count(waiting, "warn", vi.manage.waitingBadge, "manage-waiting")}
      {failed > 0 && count(failed, "danger", vi.manage.failedBadge)}
      {running > 0 && count(running, "live", vi.manage.liveBadge)}
    </button>
  );
}

interface SidebarParts extends Pick<ChatProps, "list" | "crew" | "liveByAgent" | "onSelectConversation"> {
  master: AgentInfo | null;
  live: RunInfo[];
  phone: boolean;
  drawer: ReturnType<typeof useDrawer>;
  searchRef: RefObject<HTMLInputElement | null>;
  create: ChatProps["list"]["create"];
  remove: (id: string) => void;
  manageButton: ReactNode;
}

/** The conversations to choose from, under the master's card and over the way to the manage screen. */
export function chatSidebar({
  list,
  crew,
  liveByAgent,
  onSelectConversation,
  master,
  live,
  phone,
  drawer,
  searchRef,
  create,
  remove,
  manageButton,
}: SidebarParts) {
  return (
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
  );
}
