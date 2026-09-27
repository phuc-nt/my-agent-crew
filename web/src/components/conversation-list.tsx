import { useState, type ReactNode, type RefObject } from "react";
import type { Conversation, RunInfo } from "../api/types";
import { useLastSeen } from "../hooks/use-last-seen";
import { useNow } from "../hooks/use-now";
import { vi } from "../i18n/vi";
import { dayGroup, type DayGroup } from "../lib/relative-time";
import { ConversationRow, type LiveStatus } from "./conversation-row";
import { ConversationSearch, matching } from "./conversation-search";
import { Brand } from "./ui/brand-mark";
import { Icon } from "./ui/icon";

type LiveRun = Pick<RunInfo, "conversation_id" | "status">;

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

/**
 * Each conversation's live state. Two runs can be open in one conversation (an earlier
 * turn left waiting); waiting on the owner wins, since that is the one he has to act on.
 */
function liveByConversation(runs: LiveRun[]): Map<string, LiveStatus> {
  const live = new Map<string, LiveStatus>();
  for (const { conversation_id: id, status } of runs) {
    if (!id || (status !== "running" && status !== "awaiting_approval")) continue;
    if (live.get(id) !== "awaiting_approval") live.set(id, status);
  }
  return live;
}

const GROUPS: DayGroup[] = ["today", "yesterday", "older"];

/** Relative times count in minutes, so the labels are re-read once a minute. */
const TICK_MS = 60_000;

/**
 * Rows under the viewer's own day they last changed on. The server already sends them
 * newest first, so each group keeps that order and only the headers are added.
 */
function byDay(conversations: Conversation[], now: Date): [DayGroup, Conversation[]][] {
  return GROUPS.map((group): [DayGroup, Conversation[]] => [
    group,
    ownFirst(conversations.filter((c) => dayGroup(c.updated_at, now) === group)),
  ]).filter(([, rows]) => rows.length > 0);
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
  liveRuns = [],
}: Props) {
  const [query, setQuery] = useState("");
  const live = liveByConversation(liveRuns);
  const isUnread = useLastSeen(conversations, activeId);
  const now = useNow(TICK_MS);
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
      {bottom && <div className="sidebar-foot">{bottom}</div>}
    </nav>
  );
}
