import type { Conversation } from "../api/types";
import { vi } from "../i18n/vi";
import { timeAgo } from "../lib/relative-time";
import { Icon } from "./ui/icon";

interface Props {
  conversation: Conversation;
  active: boolean;
  /** A run is working in it right now, so the dot pulses. */
  live: boolean;
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
  const status = live ? "running" : c.status;
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
