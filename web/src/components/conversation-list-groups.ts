import type { Conversation, RunInfo } from "../api/types";
import { dayGroup, type DayGroup } from "../lib/relative-time";
import type { LiveStatus } from "./conversation-row";

export type LiveRun = Pick<RunInfo, "conversation_id" | "status">;

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
export function liveByConversation(runs: LiveRun[]): Map<string, LiveStatus> {
  const live = new Map<string, LiveStatus>();
  for (const { conversation_id: id, status } of runs) {
    if (!id || (status !== "running" && status !== "awaiting_approval")) continue;
    if (live.get(id) !== "awaiting_approval") live.set(id, status);
  }
  return live;
}

const GROUPS: DayGroup[] = ["today", "yesterday", "older"];

/**
 * Rows under the viewer's own day they last changed on. The server already sends them
 * newest first, so each group keeps that order and only the headers are added.
 */
export function byDay(conversations: Conversation[], now: Date): [DayGroup, Conversation[]][] {
  return GROUPS.map((group): [DayGroup, Conversation[]] => [
    group,
    ownFirst(conversations.filter((c) => dayGroup(c.updated_at, now) === group)),
  ]).filter(([, rows]) => rows.length > 0);
}
