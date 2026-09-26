import { useState, type ReactNode, type RefObject } from "react";
import type { Conversation } from "../api/types";
import { vi } from "../i18n/vi";
import { ConversationSearch, matching } from "./conversation-search";
import { Brand } from "./ui/brand-mark";
import { Icon } from "./ui/icon";

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
  /** Present on a phone, where the list slides over the chat instead of sitting beside it. */
  drawer?: { open: boolean; close: () => void; ref: RefObject<HTMLElement | null> };
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
  drawer,
}: Props) {
  const [query, setQuery] = useState("");
  // Below a handful of threads the eye is faster than the box, and a control that is
  // never the quickest way to do the thing is just something else to look past.
  const searchable = conversations.length >= SEARCH_FROM;
  const shown = searchable ? matching(conversations, query) : conversations;
  // Choosing where to go is the drawer's whole job, so doing it also puts the drawer away.
  const pick = (id: string) => {
    onSelect(id);
    drawer?.close();
  };

  return (
    <nav
      className={`sidebar${drawer ? " drawer" : ""}${drawer?.open ? " open" : ""}`}
      aria-label={vi.conversations}
      ref={drawer?.ref}
      // Closed, the drawer is off screen but still in the DOM; inert keeps Tab and screen
      // readers from wandering into a panel nobody can see.
      inert={drawer ? !drawer.open : undefined}
    >
      <div className="sidebar-head">
        <Brand />
        {drawer && (
          <button
            type="button"
            className="icon-button"
            aria-label={vi.closeConversations}
            onClick={drawer.close}
          >
            <Icon name="close" />
          </button>
        )}
      </div>
      {top}
      <button
        type="button"
        className="primary new-conversation"
        onClick={() => {
          onCreate();
          drawer?.close();
        }}
      >
        <Icon name="plus" />
        {vi.newConversation}
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
                onClick={() => pick(c.id)}
                aria-current={c.id === activeId ? "page" : undefined}
              >
                <span className={`status-dot ${c.status}`} title={c.status} />
                {c.parent_call_id && (
                  <span className="child-marker" data-testid="child-marker" title={vi.delegateChild}>
                    <Icon name="corner-down-right" />
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
                <Icon name="trash" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {bottom && <div className="sidebar-foot">{bottom}</div>}
    </nav>
  );
}
