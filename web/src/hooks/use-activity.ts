import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { api, subscribeActivity } from "../api/client";
import type { Conversation } from "../api/types";
import { activityReducer, emptyActivity, type ActivityState } from "../state/activity-reducer";

export interface ActivityController {
  state: ActivityState;
  refresh: () => Promise<void>;
  /** The stream was (re)opened and has not answered yet, so it is not lost either. */
  connecting: boolean;
  /** This connection's snapshot has landed: a run not live in `state` is not going. */
  synced: boolean;
  /** Closes the stream and opens a fresh one. The browser gives up retrying for good once
   *  the server answers an attempt with an error, which a restart does. */
  reconnect: () => void;
}

const RECENT_LIMIT = 50;

/** Every agent's runs: recent ones from the API, live ones from the SSE stream.
 *
 *  `onConversation` receives the conversations the same stream carries — a thread the
 *  server renamed after reading the first message — so the sidebar can update itself
 *  without the list being fetched again. */
export function useActivity(
  enabled = true,
  onConversation?: (conversation: Conversation) => void,
): ActivityController {
  const [state, dispatch] = useReducer(activityReducer, emptyActivity);
  const [attempt, setAttempt] = useState(0);
  const [link, setLink] = useState({ connecting: true, synced: false });
  // Held in a ref so a new callback identity does not tear down the subscription.
  const notify = useRef(onConversation);
  notify.current = onConversation;

  const refresh = useCallback(async () => {
    try {
      dispatch({ type: "recent", runs: await api.listRuns({ limit: RECENT_LIMIT }) });
    } catch {
      // The stream still shows live work; the list fills in on the next refresh.
    }
  }, []);

  const reconnect = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") return;
    setLink((l) => (l.connecting && !l.synced ? l : { connecting: true, synced: false }));
    void refresh();
    let seenSnapshot = false;
    return subscribeActivity(
      (payload) => {
        if (payload.type === "conversation") {
          notify.current?.(payload.conversation);
          return;
        }
        dispatch({ type: "payload", payload });
        if (payload.type === "snapshot") setLink({ connecting: false, synced: true });
        // Each connection opens with a snapshot of the live runs only. After a drop, a run
        // that ended meanwhile is in neither that nor any event, so the list is read again.
        if (payload.type === "snapshot" && seenSnapshot) void refresh();
        if (payload.type === "snapshot") seenSnapshot = true;
        // A finished run carries server-side durations; pull the list so stats stay honest.
        if (payload.type === "run" && payload.run.finished_at) void refresh();
      },
      (connected) => {
        dispatch({ type: "connection", connected });
        // Open is not synced yet: the snapshot of what is live follows the open.
        setLink((l) => ({ connecting: false, synced: connected && l.synced }));
      },
    );
  }, [enabled, refresh, attempt]);

  return { state, refresh, connecting: link.connecting, synced: link.synced, reconnect };
}
