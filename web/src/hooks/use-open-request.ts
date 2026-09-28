import { type Dispatch, type SetStateAction, useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { RunInfo } from "../api/types";
import { type PendingApproval, pendingFromApproval } from "../state/thread-reducer";
import { errorText } from "../lib/error-text";

export type OpenRequest =
  | { state: "loading" }
  | { state: "ready"; pending: PendingApproval | null }
  | { state: "failed"; message: string };

export const messageOf = (err: unknown) => errorText(err);

interface Controller {
  load: OpenRequest;
  setLoad: Dispatch<SetStateAction<OpenRequest>>;
  /** The request open on the conversation now, or null; throws when the read fails. */
  read: () => Promise<PendingApproval | null>;
  /** Reads and shows the result. Undefined when the read failed: a request already on
   *  screen stays, since it is still the best guess, and only a first read turns into an error. */
  refresh: () => Promise<PendingApproval | null | undefined>;
}

/**
 * The request a waiting run's conversation holds open. The run list says a run waits but
 * not on what; the conversation has the request, with its real deadline.
 *
 * Read again each time the activity stream hands over a new copy of the run while no
 * decision is on its way — a reconnect after a restart, a decision taken in another tab —
 * so a row whose first read failed, or that shows a request since closed, catches up.
 */
export function useOpenRequest(conversationId: string, run: RunInfo, deciding: boolean): Controller {
  const [load, setLoad] = useState<OpenRequest>({ state: "loading" });

  const read = useCallback(async () => {
    const detail = await api.getConversation(conversationId);
    return detail.pending_approval ? pendingFromApproval(detail.pending_approval) : null;
  }, [conversationId]);

  const refresh = useCallback(async () => {
    try {
      const pending = await read();
      setLoad({ state: "ready", pending });
      return pending;
    } catch (err) {
      setLoad((was) => (was.state === "ready" ? was : { state: "failed", message: messageOf(err) }));
      return undefined;
    }
  }, [read]);

  // The copy seen last, updated while deciding too: the decision reads the request itself
  // once its turn ends, and a second read on top of that would only race it.
  const seen = useRef(run);
  useEffect(() => {
    if (seen.current === run) return;
    seen.current = run;
    if (!deciding) void refresh();
  }, [run, deciding, refresh]);

  return { load, setLoad, read, refresh };
}
