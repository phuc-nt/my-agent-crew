import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api/client";
import type { RunInfo } from "../api/types";
import { messageOf, useOpenRequest } from "../hooks/use-open-request";
import { vi } from "../i18n/vi";
import { runSummaryText } from "../lib/run-summary";
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

/** The row does not replay the resumed turn; it only has to know when it has ended. */
const ignoreEvent = () => undefined;

/** The server closes expired requests on its scheduler's tick, every 20 seconds: by this
 *  long after the deadline the sweep has run, whatever the phase of the tick. */
const AFTER_SWEEP_MS = 25_000;

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
  const [working, setWorking] = useState(false);
  const { load, setLoad, read, refresh } = useOpenRequest(conversationId, run, working);
  // What the last decision met, and on which request: once the row shows a newer one,
  // "already handled" or an error about the old one would read as being about it.
  const [note, setNote] = useState<{ text: string; about: string } | null>(null);
  // Held in a ref: the parent hands a new callback each render, and the expiry effect
  // below must fire once per deadline, not once per render.
  const reload = useRef(props.onReload);
  reload.current = props.onReload;
  const row = useRef<HTMLLIElement>(null);

  // Listed as waiting while nothing waits: a restart left the run behind, or it was settled
  // elsewhere while the activity stream was down. The list may know better.
  const open = useCallback(() => void refresh().then((pending) => pending === null && reload.current()), [refresh]);
  useEffect(open, [open]);

  const pending = load.state === "ready" ? load.pending : null;
  // Once a decision is sent the deadline no longer applies: counting on would turn the
  // chip red and reload the list for a request that was answered, not one that expired.
  const remaining = useRemaining(working ? undefined : pending?.expiresAt);
  const expired = remaining === 0;

  // The server closes an expired request on its own sweep and resumes the run with a
  // refusal or a default answer; reading the list again lets the row follow it. The read
  // at the deadline usually beats the sweep, so both are read again once it has run —
  // without that the row would wait, disabled, on the activity stream alone.
  useEffect(() => {
    if (!expired) return;
    reload.current();
    const after = window.setTimeout(() => void refresh().then(() => reload.current()), AFTER_SWEEP_MS);
    return () => window.clearTimeout(after);
  }, [expired, refresh]);

  const settle = async (about: string, send: () => Promise<void>) => {
    // The buttons disable themselves next, which would drop a keyboard user's focus to the
    // top of the page; the row keeps it until the request is settled.
    if (row.current?.contains(document.activeElement)) row.current.focus();
    props.onHold?.();
    setWorking(true);
    setNote(null);
    try {
      await send();
      const next = await read();
      if (next) setLoad({ state: "ready", pending: next });
      else onSettled();
    } catch (err) {
      // Someone got there first: another tab, Telegram or the expiry sweep. Saying the
      // conversation is busy would send the person to wait for something already over.
      const handled = err instanceof ApiError && err.status === 409;
      setNote({ text: handled ? vi.attentionHandled : vi.errorPrefix + messageOf(err), about });
      // Whatever failed, the request shown may be over: a stream cut after the server took
      // the decision leaves nothing to decide, or the next request. A 409 is proof enough.
      const now = await read().catch(() => (handled ? null : undefined));
      if (now !== undefined) setLoad({ state: "ready", pending: now });
    } finally {
      setWorking(false);
      reload.current();
    }
  };

  const decide = (id: string, approve: boolean) =>
    settle(id, () => api.resolveApproval(conversationId, id, approve, ignoreEvent));
  const answer = (id: string, text: string) =>
    settle(id, () => api.answerApproval(conversationId, id, text, ignoreEvent));

  const busy = working || expired;
  // False rather than undefined while the decision is on its way: no fallback deadline either.
  const deadline = !working && remaining !== null && <ExpiryCountdown remaining={remaining} />;
  const closed = load.state === "ready" && !pending && !working;
  const said = note && (!pending || note.about === pending.approvalId) ? note.text : null;
  return (
    <li ref={row} tabIndex={-1} className="awaiting_approval inline" data-testid="attention-row">
      {children}
      <div className="attention-inline">
        {load.state === "loading" && <p className="muted">{vi.attentionLoading}</p>}
        {load.state === "failed" && (
          <>
            <p className="attention-note">{vi.errorPrefix + load.message}</p>
            <button
              type="button"
              className="attention-retry"
              aria-describedby={labelledBy}
              onClick={() => {
                setLoad({ state: "loading" });
                open();
              }}
            >
              {vi.attentionRetry}
            </button>
          </>
        )}
        {pending?.kind === "question" && (
          // Keyed by the request: a follow-up must not inherit the reply typed to the last one.
          <QuestionCard
            key={pending.approvalId}
            pending={pending}
            labelledBy={labelledBy}
            busy={busy}
            deadline={deadline}
            onAnswer={(text) => void answer(pending.approvalId, text)}
          />
        )}
        {pending && pending.kind !== "question" && (
          <ApprovalBar
            key={pending.approvalId}
            pending={pending}
            labelledBy={labelledBy}
            busy={busy}
            deadline={deadline}
            onDecide={(approve) => void decide(pending.approvalId, approve)}
          />
        )}
        {load.state === "ready" && !pending && !said && run.summary && (
          <p className="run-preview muted">{runSummaryText(run)}</p>
        )}
        <p className="attention-note" role="status">
          {working ? vi.attentionResuming : (said ?? (closed ? vi.attentionHandled : null))}
        </p>
        {closed && props.dismiss}
      </div>
    </li>
  );
}
