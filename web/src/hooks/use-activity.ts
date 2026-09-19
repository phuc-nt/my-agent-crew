import { useCallback, useEffect, useReducer } from "react";
import { api, subscribeActivity } from "../api/client";
import { activityReducer, emptyActivity, type ActivityState } from "../state/activity-reducer";

export interface ActivityController {
  state: ActivityState;
  refresh: () => Promise<void>;
}

const RECENT_LIMIT = 50;

/** Every agent's runs: recent ones from the API, live ones from the SSE stream. */
export function useActivity(enabled = true): ActivityController {
  const [state, dispatch] = useReducer(activityReducer, emptyActivity);

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
        dispatch({ type: "payload", payload });
        // A finished run carries server-side durations; pull the list so stats stay honest.
        if (payload.type === "run" && payload.run.finished_at) void refresh();
      },
      (connected) => dispatch({ type: "connection", connected }),
    );
  }, [enabled, refresh]);

  return { state, refresh };
}
