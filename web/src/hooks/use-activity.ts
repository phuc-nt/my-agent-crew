import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { api, subscribeActivity } from "../api/client";
import { emitArtifactEvent } from "../lib/artifact-events";
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
  const [connecting, setConnecting] = useState(true);
  // Held in a ref so a new callback identity does not tear down the subscription.
  const notify = useRef(onConversation);
  notify.current = onConversation;
  const everSynced = useRef(false);

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
    setConnecting(true);
    // A stream opened again reads the list once its snapshot is in (below); a read now as
    // well would race that one, and could land after it with older news.
    if (!everSynced.current) void refresh();
    return subscribeActivity(
      (payload) => {
        if (payload.type === "conversation") {
          notify.current?.(payload.conversation);
          return;
        }
        if (payload.type === "artifact") {
          emitArtifactEvent(payload);
          return;
        }
        dispatch({ type: "payload", payload });
        if (payload.type === "snapshot") {
          setConnecting(false);
          // Each connection opens with a snapshot of the live runs only. After a drop (or a
          // reconnect), a run that ended meanwhile is in neither that nor any event, so the
          // list is read again.
          if (everSynced.current) void refresh();
          everSynced.current = true;
        }
        // A finished run carries server-side durations; pull the list so stats stay honest.
        if (payload.type === "run" && payload.run.finished_at) void refresh();
      },
      (connected) => {
        dispatch({ type: "connection", connected });
        setConnecting(false);
      },
    );
  }, [enabled, refresh, attempt]);

  return { state, refresh, connecting, synced: state.synced, reconnect };
}
