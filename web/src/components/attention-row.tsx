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
  /** Offered once the request is closed and nothing waits in its place. */
  dismiss?: ReactNode;
  /** A decision is on its way: the row must outlive its run leaving the waiting list. */
  onHold?: () => void;
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
export function AttentionRow(props: Props) {
  const { run, conversationId, children, labelledBy, onSettled } = props;
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [working, setWorking] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  // Held in a ref: the parent hands a new callback each render, and the expiry effect
  // below must fire once per deadline, not once per render.
  const reload = useRef(props.onReload);
  reload.current = props.onReload;

  const fetchPending = useCallback(async () => {
    const detail = await api.getConversation(conversationId);
    return detail.pending_approval ? pendingFromApproval(detail.pending_approval) : null;
  }, [conversationId]);

  useEffect(() => {
    let current = true;
    fetchPending().then(
      (pending) => {
        if (!current) return;
        setLoad({ state: "ready", pending });
        // Listed as waiting while nothing waits: a restart left the run behind, or it was
        // settled elsewhere while the activity stream was down. The list may know better.
        if (!pending) reload.current();
      },
      (err) => current && setLoad({ state: "failed", message: messageOf(err) }),
    );
    return () => {
      current = false;
    };
  }, [fetchPending]);

  const pending = load.state === "ready" ? load.pending : null;
  // Once a decision is sent the deadline no longer applies: counting on would turn the
  // chip red and reload the list for a request that was answered, not one that expired.
  const remaining = useRemaining(working ? undefined : pending?.expiresAt);
  const expired = remaining === 0;

  // The server closes an expired request on its own sweep and resumes the run with a
  // refusal or a default answer; reading the list again lets the row follow it.
  useEffect(() => {
    if (expired) reload.current();
  }, [expired]);

  const settle = async (send: () => Promise<void>) => {
    props.onHold?.();
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
      const handled = err instanceof ApiError && err.status === 409;
      setNote(handled ? vi.attentionHandled : vi.errorPrefix + messageOf(err));
      // Whatever failed, the request shown may be over: a stream cut after the server took
      // the decision leaves nothing to decide, or the next request. A 409 is proof enough.
      const now = await fetchPending().catch(() => (handled ? null : undefined));
      if (now !== undefined) setLoad({ state: "ready", pending: now });
    } finally {
      setWorking(false);
      reload.current();
    }
  };

  const busy = working || expired;
  // False rather than undefined while the decision is on its way: no fallback deadline either.
  const deadline = !working && remaining !== null && <ExpiryCountdown remaining={remaining} />;
  const closed = load.state === "ready" && !pending && !working;
  return (
    <li className="awaiting_approval inline" data-testid="attention-row">
      {children}
      <div className="attention-inline">
        {load.state === "loading" && <p className="muted">{vi.attentionLoading}</p>}
        {load.state === "failed" && <p className="attention-note">{vi.errorPrefix + load.message}</p>}
        {pending?.kind === "question" && (
          // Keyed by the request: a follow-up must not inherit the reply typed to the last one.
          <QuestionCard
            key={pending.approvalId}
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
            key={pending.approvalId}
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
          {working ? vi.attentionResuming : (note ?? (closed ? vi.attentionHandled : null))}
        </p>
        {closed && props.dismiss}
      </div>
    </li>
  );
}
