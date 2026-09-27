import { useEffect, useId, useRef, useState } from "react";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { runSummaryText } from "../lib/run-summary";
import { markSeen, seenKey } from "../lib/seen-runs";
import { AttentionRow } from "./attention-row";
import { formatClock } from "./run-timeline";
import { Icon, type IconName } from "./ui/icon";

interface Props {
  runs: RunInfo[];
  agentName: (id: string) => string;
  onOpenConversation: (conversationId: string) => void;
  /** Names the run that handed out this work, when it is a delegated one. */
  parentTitle?: (run: RunInfo) => string | null;
  /** Waiting rows carry their request in place, so it is settled without leaving. */
  inline?: boolean;
  /** Reads the activity list again after a row changed something on the server. */
  onReload?: () => void;
  /** Requests waiting in another section, so this card never says there is nothing. */
  waitingElsewhere?: number;
  onOpenWaiting?: () => void;
  /** Failures not yet read, listed in another section — the same promise the other way. */
  failedElsewhere?: number;
  onOpenFailed?: () => void;
}

/** A run pauses for two unrelated reasons, and only one of them is a permission request.
 *  The open question step is what tells them apart: a tool approval never writes one. */
function isAsking(run: RunInfo): boolean {
  return run.steps.some((step) => step.kind === "question" && step.duration_ms === null);
}

function label(run: RunInfo, agent: string): string {
  if (run.status === "awaiting_approval") {
    return isAsking(run) ? vi.attentionAsking(agent) : vi.attentionAwaiting(agent);
  }
  if (run.status === "error") return vi.attentionFailed(agent);
  return vi.attentionHalted(agent);
}

/** The shape of the ask, so a question, a permission and a failure differ before they are read. */
function icon(run: RunInfo): IconName {
  if (run.status === "awaiting_approval") return isAsking(run) ? "help" : "approvals";
  return "alert";
}

const noop = () => undefined;

/** Newest first, as the activity list is: a held row goes back where it was listed. */
const byStart = (a: RunInfo, b: RunInfo) => b.started_at.localeCompare(a.started_at);

/** Approvals waiting anywhere plus runs that ended badly, one click from their conversation. */
export function AttentionCenter(props: Props) {
  const { runs, agentName, onOpenConversation, parentTitle, inline = false } = props;
  const waitingElsewhere = props.waitingElsewhere ?? 0;
  const failedElsewhere = props.failedElsewhere ?? 0;
  const titles = useId();
  // Rows settled or dismissed from here leave at once, before the list is read again.
  const [settled, setSettled] = useState<string[]>([]);
  // Rows whose decision is still resuming their run. The run stops waiting as soon as the
  // server has the decision, and its row would leave with it — taking "Đang chạy tiếp…"
  // and any error from the resumed turn along before either could be read.
  const [held, setHeld] = useState<RunInfo[]>([]);
  const extra = held.filter((h) => !runs.some((run) => run.id === h.id));
  const listed = extra.length > 0 ? [...runs, ...extra].sort(byStart) : runs;
  const shown = listed.filter((run) => !settled.includes(seenKey(run)));
  // "Nothing needs you" must hold for the whole manage screen, not just this list: the
  // nav still counts the work listed on the other page, and the two would contradict.
  const calm = shown.length === 0 && waitingElsewhere === 0 && failedElsewhere === 0;

  // A row that leaves takes the focus inside it along, and the next Tab would start over
  // from the top of the page: it goes to the row that took its place, or to the heading.
  const heading = useRef<HTMLHeadingElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const current = useRef(shown);
  current.current = shown;
  const leaving = useRef<number | null>(null);
  useEffect(() => {
    const at = leaving.current;
    if (at === null) return;
    leaving.current = null;
    if (document.activeElement && document.activeElement !== document.body) return;
    const rows = list.current?.querySelectorAll<HTMLElement>(":scope > li");
    const next = rows?.[Math.min(at, rows.length - 1)];
    (next?.querySelector<HTMLElement>("button:not(:disabled)") ?? heading.current)?.focus();
  });
  const leave = (run: RunInfo) => {
    leaving.current = current.current.findIndex((r) => r.id === run.id);
    setSettled((keys) => [...keys, seenKey(run)]);
    setHeld((rows) => rows.filter((r) => r.id !== run.id));
  };
  const hold = (run: RunInfo) => setHeld((rows) => [...rows.filter((r) => r.id !== run.id), run]);

  // Said of a failure once it is read, and of a request found closed with nothing to decide.
  const seenButton = (run: RunInfo) => (
    <button
      type="button"
      className="ghost attention-seen"
      aria-label={vi.attentionSeenLabel(label(run, agentName(run.agent_id)))}
      onClick={() => {
        markSeen(seenKey(run));
        leave(run);
      }}
    >
      <Icon name="check" />
      {vi.attentionSeen}
    </button>
  );

  const head = (run: RunInfo, preview: boolean) => {
    const parent = parentTitle?.(run);
    return (
      <>
        <span className="attention-icon">
          <Icon name={icon(run)} />
        </span>
        <span className="attention-text">
          <span className="attention-title" id={`${titles}-${run.id}`}>
            {label(run, agentName(run.agent_id))}
            <span className="muted tabular"> · {formatClock(run.started_at)}</span>
          </span>
          {parent && (
            <span className="attention-child" data-testid="attention-child">
              {vi.delegateChildOf.replace("{parent}", parent)}
            </span>
          )}
          {preview && run.summary && <span className="run-preview muted">{runSummaryText(run)}</span>}
        </span>
        <span className="attention-actions">
          {run.conversation_id && (
            <button
              type="button"
              className="attention-open"
              onClick={() => onOpenConversation(run.conversation_id as string)}
            >
              {vi.openConversation}
              <Icon name="arrow-right" />
            </button>
          )}
          {/* A failure is read, not decided: saying so is the only thing left to do with it. */}
          {run.status !== "awaiting_approval" && seenButton(run)}
        </span>
      </>
    );
  };

  return (
    // Amber only while something is waiting on a person. A card that stays amber on an
    // empty list teaches the eye to skip it, which is the one thing it must not do.
    <section className={`attention${calm ? " calm" : ""}`} aria-label={vi.attention} data-testid="attention">
      <h3 ref={heading} tabIndex={-1}>
        {vi.attention}
      </h3>
      {calm && (
        <p className="attention-calm">
          <Icon name="check" />
          {vi.attentionEmpty}
        </p>
      )}
      {shown.length > 0 && (
        <ul className="attention-list" ref={list}>
          {shown.map((run) =>
            inline && run.status === "awaiting_approval" && run.conversation_id ? (
              <AttentionRow
                key={run.id}
                run={run}
                conversationId={run.conversation_id}
                labelledBy={`${titles}-${run.id}`}
                dismiss={seenButton(run)}
                onReload={props.onReload ?? noop}
                onHold={() => hold(run)}
                onSettled={() => leave(run)}
              >
                {head(run, false)}
              </AttentionRow>
            ) : (
              <li key={run.id} className={run.status}>
                {head(run, true)}
              </li>
            ),
          )}
        </ul>
      )}
      {waitingElsewhere > 0 && (
        <button type="button" className="attention-elsewhere" onClick={props.onOpenWaiting}>
          {vi.attentionWaitingElsewhere(waitingElsewhere)}
          <Icon name="arrow-right" />
        </button>
      )}
      {failedElsewhere > 0 && (
        <button type="button" className="attention-elsewhere" onClick={props.onOpenFailed}>
          {vi.attentionFailedElsewhere(failedElsewhere)}
          <Icon name="arrow-right" />
        </button>
      )}
    </section>
  );
}
