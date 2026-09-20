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
          {conversations.map((c) => (
            <li key={c.id} className={c.id === activeId ? "active" : ""}>
              <button
                type="button"
                className="conversation-item"
                onClick={() => onSelect(c.id)}
                aria-current={c.id === activeId ? "page" : undefined}
              >
                <span className={`status-dot ${c.status}`} title={c.status} />
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
