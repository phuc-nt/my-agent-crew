import { useState, type ReactNode, type RefObject } from "react";
import type { Conversation } from "../api/types";
import { vi } from "../i18n/vi";
import { ConversationSearch, matching } from "./conversation-search";

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  /** Rendered above the list, e.g. the agent switcher. */
  top?: ReactNode;
  /** Rendered at the foot, below the list, e.g. the way into the manage screen. */
  bottom?: ReactNode;
  /** Held by the shell so ⌘K can put the cursor in the search box. */
  searchRef?: RefObject<HTMLInputElement | null>;
}

/** How many threads it takes before scanning the list beats reading it. */
const SEARCH_FROM = 8;

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

export function ConversationList({
  conversations,
  activeId,
  onSelect,
  onCreate,
  onDelete,
  top,
  bottom,
  searchRef,
}: Props) {
  const [query, setQuery] = useState("");
  // Below a handful of threads the eye is faster than the box, and a control that is
  // never the quickest way to do the thing is just something else to look past.
  const searchable = conversations.length >= SEARCH_FROM;
  const shown = searchable ? matching(conversations, query) : conversations;

  return (
    <nav className="sidebar" aria-label={vi.conversations}>
      {top}
      <button type="button" className="primary new-conversation" onClick={onCreate}>
        + {vi.newConversation}
      </button>
      {searchable && (
        <ConversationSearch value={query} onChange={setQuery} inputRef={searchRef} />
      )}
      {conversations.length === 0 ? (
        <p className="muted">{vi.noConversations}</p>
      ) : shown.length === 0 ? (
        <p className="muted" data-testid="no-matches">
          {vi.noMatchingConversations}
        </p>
      ) : (
        <ul className="conversation-list">
          {ownFirst(shown).map((c) => (
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
      {bottom && <div className="sidebar-foot">{bottom}</div>}
    </nav>
  );
}
