import { useEffect, useReducer, useRef } from "react";
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
  // A turn of this tab's starts one run or resumes the one paused here: this is it.
  const claim = useRef<{ taken: boolean; run: string | null }>({ taken: false, run: null });
  const wasBusy = useRef(false);
  const [, redraw] = useReducer((n: number) => n + 1, 0);
  const busy = thread.state.busy;
  const { reload, reloadWhenIdle, settle, handledElsewhere } = thread;
  const handledSeen = useRef(handledElsewhere);
  const { synced } = activity;
  const runs = conversationId ? runsForConversation(activity.state, conversationId) : [];
  const key = runs.map((r) => `${r.id}:${r.status}`).join(",");

  // Declared first so it runs first: a newly opened conversation's runs are all first
  // sightings, not changes to reload for.
  useEffect(() => {
    seen.current = new Map();
    ours.current = new Set();
    claim.current = { taken: false, run: null };
  }, [conversationId]);

  // The stream says nothing of what happened while it was down: a run may have started
  // and ended in the gap, or ended after it was last seen live. So once it is back in
  // sync the thread is loaded again, and runs are measured against that load from then
  // on: one going now was going already, not one a later turn of this tab's starts. A
  // turn of this tab's own gets to end first.
  const everSynced = useRef(false);
  const behind = useRef(false);
  useEffect(() => {
    if (!synced) {
      behind.current ||= everSynced.current;
      return;
    }
    everSynced.current = true;
    if (!behind.current || busy) return;
    behind.current = false;
    seen.current = new Map(runs.map((r) => [r.id, r.status]));
    if (conversationId) void reload();
    // `runs` is read as it stands when the stream is back; it is no reason to run again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [synced, busy, conversationId, reload]);

  useEffect(() => {
    if (busy && !wasBusy.current) claim.current = { taken: false, run: null };
    wasBusy.current = busy;
    // A decision refused as already taken elsewhere resumed nothing here: the run seen
    // resuming meanwhile is the other channel's, to show as going and to load once over.
    // The render that ended the turn still counted it as this tab's, hence the redraw.
    if (handledSeen.current !== handledElsewhere) {
      handledSeen.current = handledElsewhere;
      if (claim.current.run && ours.current.delete(claim.current.run)) redraw();
      claim.current = { taken: true, run: null };
    }
    let changed = false;
    for (const run of runs) {
      const prev = seen.current.get(run.id);
      seen.current.set(run.id, run.status);
      // The first run to start or resume while this tab streams is the one it streams. A
      // run that was going already, or one that starts after it, is another channel's.
      const starts = prev === undefined || prev === AWAITING;
      if (busy && starts && run.status === "running" && !claim.current.taken) {
        ours.current.add(run.id);
        claim.current = { taken: true, run: run.id };
      }
      const mine = ours.current.has(run.id);
      // A paused run belongs to whoever answers it: a decision taken here resumes it on
      // this tab's stream, one taken elsewhere does not.
      if (run.status === AWAITING) ours.current.delete(run.id);
      // A drain turn's first sighting is exactly the run a waiting chip is about to
      // become: the person's message was written before the turn even started. This does
      // not require catching it as `running` — the server may finish that turn before the
      // browser renders a frame for it (an echo reply, a turn halted on budget with no
      // model call at all), in which case the first payload this tab ever sees for the run
      // already carries its terminal status. Either way the chip needs the same reload.
      const drains = prev === undefined && thread.state.waiting.length > 0;
      if (!mine && drains && !behind.current) changed = true;
      if (mine || prev === undefined || prev === run.status) continue;
      // Going back to running only matters when it took an approval with it.
      if (run.status !== "running" || prev === AWAITING) changed = true;
    }
    // While the stream is behind, the reload on its return covers this change as well.
    // During a turn of this tab's the load waits for the turn, which it would wipe.
    if (changed && !behind.current) reloadWhenIdle();
    // `key` stands for `runs`, which is a new array on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, busy, handledElsewhere, reloadWhenIdle]);

  // Once the stream has said what is live, a call still spinning in a conversation with
  // nothing going is one no run will ever answer — a turn cut off before its result.
  const live = runs.some((r) => LIVE.includes(r.status));
  const { items } = thread.state;
  useEffect(() => {
    if (synced && !busy && !live) settle();
  }, [synced, busy, live, items, settle]);

  if (busy) return null;
  return runs.find((r) => r.status === "running" && !ours.current.has(r.id)) ?? null;
}
