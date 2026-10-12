import { useState, type ReactNode, type RefObject } from "react";
import type { Conversation } from "../api/types";
import { useContentSearch } from "../hooks/use-content-search";
import { useLastSeen } from "../hooks/use-last-seen";
import { useNow } from "../hooks/use-now";
import { vi } from "../i18n/vi";
import { ContentHits } from "./content-hits";
import { byDay, liveByConversation, type LiveRun } from "./conversation-list-groups";
import { ConversationRow } from "./conversation-row";
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
  /** The runs working right now; each row shows the state of the one in it. */
  liveRuns?: LiveRun[];
  /**
   * Looks up an agent's display name for a content hit's badge, e.g. `crew.agentName`.
   * Present, the search box also searches message content; absent, it only searches titles,
   * exactly as before.
   */
  agentName?: (agentId: string) => string;
}

/** How many threads it takes before scanning the list beats reading it. */
const SEARCH_FROM = 8;

/** Relative times count in minutes, so the labels are re-read once a minute. */
const TICK_MS = 60_000;

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
  liveRuns = [],
  agentName,
}: Props) {
  const [query, setQuery] = useState("");
  const live = liveByConversation(liveRuns);
  const isUnread = useLastSeen(conversations, activeId);
  const now = useNow(TICK_MS);
  // Below a handful of threads the eye is faster than the box, and a control that is
  // never the quickest way to do the thing is just something else to look past.
  const searchable = conversations.length >= SEARCH_FROM;
  const shown = searchable ? matching(conversations, query) : conversations;
  const content = useContentSearch(query, searchable && agentName !== undefined);
  // A title miss is not "no results" once content search still found something; the
  // "Trong nội dung" section below speaks for itself in that case.
  const hasContentHits = (content.hits?.length ?? 0) > 0;
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
      ) : shown.length === 0 && !hasContentHits ? (
        <p className="muted" data-testid="no-matches">
          {vi.noMatchingConversations}
        </p>
      ) : shown.length === 0 ? null : (
        <div className="conversation-list">
          {byDay(shown, now).map(([group, rows]) => (
            // A group, not a section: a labelled section is a landmark, and one per day
            // would crowd the landmark list beside the navigation it sits in.
            <div
              key={group}
              role="group"
              className="conversation-group"
              aria-labelledby={`group-${group}`}
            >
              <h2 id={`group-${group}`}>{vi.time.groups[group]}</h2>
              <ul>
                {rows.map((c) => (
                  <ConversationRow
                    key={c.id}
                    conversation={c}
                    active={c.id === activeId}
                    live={live.get(c.id)}
                    now={now}
                    // A delegated conversation is the agents' working, not a reply to the
                    // person, so it never asks for attention with a dot.
                    unread={!c.parent_call_id && isUnread(c)}
                    onPick={() => pick(c.id)}
                    onDelete={() => onDelete(c.id)}
                  />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
      {agentName && (
        <ContentHits
          hits={content.hits}
          loading={content.loading}
          error={content.error}
          onRetry={content.retry}
          onSelect={pick}
          agentName={agentName}
          now={now}
        />
      )}
      {bottom && <div className="sidebar-foot">{bottom}</div>}
    </nav>
  );
}
