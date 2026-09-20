import type { ReactNode } from "react";
import type { Conversation } from "../api/types";
import { vi } from "../i18n/vi";

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  /** Rendered above the list, e.g. the agent switcher. */
  top?: ReactNode;
}

/**
 * Conversations the user started, then the ones an agent opened on their behalf. A
 * delegated conversation is a record of work, not somewhere the user is talking, so it
 * stays reachable without pushing the real threads down the list.
 */
function ownFirst(conversations: Conversation[]): Conversation[] {
  return [
    ...conversations.filter((c) => !c.parent_call_id),
    ...conversations.filter((c) => c.parent_call_id),
  ];
}

export function ConversationList({ conversations, activeId, onSelect, onCreate, onDelete, top }: Props) {
  return (
    <nav className="sidebar" aria-label={vi.conversations}>
      {top}
      <button type="button" className="primary new-conversation" onClick={onCreate}>
        + {vi.newConversation}
      </button>
      {conversations.length === 0 ? (
        <p className="muted">{vi.noConversations}</p>
      ) : (
        <ul className="conversation-list">
          {ownFirst(conversations).map((c) => (
            <li key={c.id} className={c.id === activeId ? "active" : ""}>
              <button
                type="button"
                className="conversation-item"
                onClick={() => onSelect(c.id)}
                aria-current={c.id === activeId ? "page" : undefined}
              >
                <span className={`status-dot ${c.status}`} title={c.status} />
                {c.parent_call_id && (
                  <span className="child-marker" data-testid="child-marker" title={vi.delegateChild}>
                    ↳
                  </span>
                )}
                <span className="conversation-title">{c.title || vi.newConversation}</span>
                {c.channel && <span className="channel-tag">{vi.channelName(c.channel)}</span>}
                {c.summary && (
                  <span className="conversation-summary" title={c.summary}>
                    {c.summary}
                  </span>
                )}
              </button>
              <button
                type="button"
                className="icon-button"
                aria-label={vi.deleteConversation}
                title={vi.deleteConversation}
                onClick={() => onDelete(c.id)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </nav>
  );
}
