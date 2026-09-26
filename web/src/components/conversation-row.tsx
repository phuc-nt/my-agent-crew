import type { Conversation, RunStatus } from "../api/types";
import { vi } from "../i18n/vi";
import { timeAgo } from "../lib/relative-time";
import { Icon } from "./ui/icon";

/** The states in which a run is still going, and so pulses the row's dot. */
export type LiveStatus = Extract<RunStatus, "running" | "awaiting_approval">;

interface Props {
  conversation: Conversation;
  active: boolean;
  /** The state of the run working in it right now, if one is. */
  live?: LiveStatus;
  /** It changed since this viewer last had it open. */
  unread: boolean;
  onPick: () => void;
  onDelete: () => void;
}

/**
 * One sidebar row: the status dot, the title and where it came from, then when it last
 * changed and its recap on the line under the title. The DOM follows that order, so the
 * row reads to a screen reader the way it reads on screen.
 */
export function ConversationRow({ conversation: c, active, live, unread, onPick, onDelete }: Props) {
  // The live run speaks for the row: the list is fetched as runs finish, so the row's own
  // status can be a turn behind, and a run waiting on the owner must say so, not "running".
  const status = live ?? c.status;
  return (
    <li className={`${active ? "active" : ""}${unread ? " unread" : ""}`.trim() || undefined}>
      <button
        type="button"
        className="conversation-item"
        onClick={onPick}
        aria-current={active ? "page" : undefined}
      >
        <span className={`status-dot ${status}`} title={vi.conversationStatus[status]} />
        {c.parent_call_id && (
          <span className="child-marker" data-testid="child-marker" title={vi.delegateChild}>
            <Icon name="corner-down-right" />
          </span>
        )}
        <span className="conversation-title">{c.title || vi.newConversation}</span>
        {c.channel && <span className="channel-tag">{vi.channelName(c.channel)}</span>}
        {unread && (
          <span className="unread-dot" data-testid="unread-dot" title={vi.unread}>
            <span className="sr-only">{vi.unread}</span>
          </span>
        )}
        {(c.updated_at || c.summary) && (
          <span className="conversation-meta">
            {c.updated_at && (
              <time className="conversation-time" dateTime={c.updated_at}>
                {timeAgo(c.updated_at)}
              </time>
            )}
            {c.summary && (
              <span className="conversation-summary" title={c.summary}>
                {c.summary}
              </span>
            )}
          </span>
        )}
      </button>
      <button
        type="button"
        className="icon-button"
        aria-label={vi.deleteConversation}
        title={vi.deleteConversation}
        onClick={onDelete}
      >
        <Icon name="trash" />
      </button>
    </li>
  );
}
