import { useEffect, useRef } from "react";
import type { RunInfo } from "../api/types";
import { runsForConversation } from "../state/activity-reducer";
import type { ActivityController } from "./use-activity";
import type { ThreadController } from "./use-thread";

const LIVE: RunInfo["status"][] = ["running", "awaiting_approval"];
const AWAITING: RunInfo["status"] = "awaiting_approval";

/**
 * Keeps the open thread in step with runs this tab did not stream: a message sent from
 * Telegram, a scheduled job, an approval decided on another device.
 *
 * The thread is a copy fetched once and then extended by this tab's own streams, so
 * without this it goes on showing an old state until someone reloads by hand. A run this
 * tab streams is already on screen event by event, so it is left alone: fetching it again
 * would only redraw what is there.
 *
 * Returns the run another channel has going in this conversation, for the thread to show
 * its progress the way it shows its own.
 */
export function useExternalRunRefresh(
  conversationId: string | null,
  thread: ThreadController,
  activity: ActivityController,
): RunInfo | null {
  const seen = useRef(new Map<string, RunInfo["status"]>());
  const ours = useRef(new Set<string>());
  const busy = thread.state.busy;
  const { reload, settle } = thread;
  const runs = conversationId ? runsForConversation(activity.state, conversationId) : [];
  const key = runs.map((r) => `${r.id}:${r.status}`).join(",");

  // Declared first so it runs first: a newly opened conversation's runs are all first
  // sightings, not changes to reload for.
  useEffect(() => {
    seen.current = new Map();
    ours.current = new Set();
  }, [conversationId]);

  useEffect(() => {
    let changed = false;
    for (const run of runs) {
      const prev = seen.current.get(run.id);
      seen.current.set(run.id, run.status);
      const mine = busy || ours.current.has(run.id);
      if (busy && run.status !== AWAITING) ours.current.add(run.id);
      // A paused run belongs to whoever answers it: a decision taken here resumes it on
      // this tab's stream, one taken elsewhere does not.
      if (run.status === AWAITING) ours.current.delete(run.id);
      if (mine || prev === undefined || prev === run.status) continue;
      // Going back to running only matters when it took an approval with it.
      if (run.status !== "running" || prev === AWAITING) changed = true;
    }
    if (changed) void reload();
    // `key` stands for `runs`, which is a new array on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, busy, reload]);

  // Once the stream has said what is live, a call still spinning in a conversation with
  // nothing going is one no run will ever answer — a turn cut off before its result.
  const live = runs.some((r) => LIVE.includes(r.status));
  const { synced } = activity;
  const { items } = thread.state;
  useEffect(() => {
    if (synced && !busy && !live) settle();
  }, [synced, busy, live, items, settle]);

  if (busy) return null;
  return runs.find((r) => r.status === "running" && !ours.current.has(r.id)) ?? null;
}
