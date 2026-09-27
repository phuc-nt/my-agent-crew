import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api/client";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { runSummaryText } from "../lib/run-summary";
import { type PendingApproval, pendingFromApproval } from "../state/thread-reducer";
import { ApprovalBar } from "./approval-bar";
import { ExpiryCountdown, useRemaining } from "./expiry-countdown";
import { QuestionCard } from "./question-card";

interface Props {
  run: RunInfo;
  conversationId: string;
  /** Who is waiting, since when, and the way to their conversation. */
  children: ReactNode;
  /** The row head's id: in a list the request is named by who asks, not by a shared title. */
  labelledBy?: string;
  /** The request is closed and nothing else waits in its place: the row can go. */
  onSettled: () => void;
  /** The server changed under the list, so the activity it shows is read again. */
  onReload: () => void;
}

type Load =
  | { state: "loading" }
  | { state: "ready"; pending: PendingApproval | null }
  | { state: "failed"; message: string };

const messageOf = (err: unknown) => (err instanceof Error ? err.message : String(err));

/** The row does not replay the resumed turn; it only has to know when it has ended. */
const ignoreEvent = () => undefined;

/**
 * A run that waits on a person, with the request itself in place of a link to it.
 *
 * The run list says a run is waiting but not what for; the conversation holds the open
 * request, with its real deadline. Deciding here goes through the same routes as the chat,
 * and waits for the resumed stream to end before the row decides whether it is done — a
 * turn can pause again on the next tool, and that new request belongs in the same row.
 */
export function AttentionRow({ run, conversationId, children, labelledBy, onSettled, onReload }: Props) {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [working, setWorking] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  // Held in a ref: the parent hands a new callback each render, and the expiry effect
  // below must fire once per deadline, not once per render.
  const reload = useRef(onReload);
  reload.current = onReload;

  const fetchPending = useCallback(async () => {
    const detail = await api.getConversation(conversationId);
    return detail.pending_approval ? pendingFromApproval(detail.pending_approval) : null;
  }, [conversationId]);

  useEffect(() => {
    let current = true;
    fetchPending().then(
      (pending) => current && setLoad({ state: "ready", pending }),
      (err) => current && setLoad({ state: "failed", message: messageOf(err) }),
    );
    return () => {
      current = false;
    };
  }, [fetchPending]);

  const pending = load.state === "ready" ? load.pending : null;
  const remaining = useRemaining(pending?.expiresAt);
  const expired = remaining === 0;

  // The server closes an expired request on its own sweep and resumes the run with a
  // refusal or a default answer; reading the list again lets the row follow it.
  useEffect(() => {
    if (expired) reload.current();
  }, [expired]);

  const settle = async (send: () => Promise<void>) => {
    setWorking(true);
    setNote(null);
    try {
      await send();
      const next = await fetchPending();
      if (next) setLoad({ state: "ready", pending: next });
      else onSettled();
    } catch (err) {
      // Someone got there first: another tab, Telegram or the expiry sweep. Saying the
      // conversation is busy would send the person to wait for something already over.
      if (err instanceof ApiError && err.status === 409) {
        setNote(vi.attentionHandled);
        setLoad({ state: "ready", pending: await fetchPending().catch(() => null) });
      } else {
        setNote(vi.errorPrefix + messageOf(err));
      }
    } finally {
      setWorking(false);
      reload.current();
    }
  };

  const busy = working || expired;
  const deadline = remaining !== null ? <ExpiryCountdown remaining={remaining} /> : undefined;
  return (
    <li className="awaiting_approval inline" data-testid="attention-row">
      {children}
      <div className="attention-inline">
        {load.state === "loading" && <p className="muted">{vi.attentionLoading}</p>}
        {load.state === "failed" && <p className="attention-note">{vi.errorPrefix + load.message}</p>}
        {pending?.kind === "question" && (
          <QuestionCard
            pending={pending}
            labelledBy={labelledBy}
            busy={busy}
            deadline={deadline}
            onAnswer={(answer) =>
              void settle(() => api.answerApproval(conversationId, pending.approvalId, answer, ignoreEvent))
            }
          />
        )}
        {pending && pending.kind !== "question" && (
          <ApprovalBar
            pending={pending}
            labelledBy={labelledBy}
            busy={busy}
            deadline={deadline}
            onDecide={(approve) =>
              void settle(() => api.resolveApproval(conversationId, pending.approvalId, approve, ignoreEvent))
            }
          />
        )}
        {load.state === "ready" && !pending && !note && run.summary && (
          <p className="run-preview muted">{runSummaryText(run)}</p>
        )}
        <p className="attention-note" role="status">
          {working ? vi.attentionResuming : note}
        </p>
      </div>
    </li>
  );
}
