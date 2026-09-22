import { useCallback, useEffect, useReducer, useRef } from "react";
import { api, subscribeActivity } from "../api/client";
import type { Conversation } from "../api/types";
import { activityReducer, emptyActivity, type ActivityState } from "../state/activity-reducer";

export interface ActivityController {
  state: ActivityState;
  refresh: () => Promise<void>;
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

  useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") return;
    void refresh();
    return subscribeActivity(
      (payload) => {
        if (payload.type === "conversation") {
          notify.current?.(payload.conversation);
          return;
        }
        dispatch({ type: "payload", payload });
        // A finished run carries server-side durations; pull the list so stats stay honest.
        if (payload.type === "run" && payload.run.finished_at) void refresh();
      },
      (connected) => dispatch({ type: "connection", connected }),
    );
  }, [enabled, refresh]);

  return { state, refresh };
}
