import { useEffect, useId, useRef, useState } from "react";
import type { RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { foldRepeats } from "../lib/attention-repeats";
import { dayClock, dayOrClock } from "../lib/relative-time";
import { type HeldRun, heldAt, withHeld } from "../lib/run-order";
import { runSummaryText } from "../lib/run-summary";
import { markSeen, seenKey } from "../lib/seen-runs";
import { AttentionElsewhere, type Elsewhere, elsewhereCount } from "./attention-elsewhere";
import { icon, label } from "./attention-label";
import { AttentionRow } from "./attention-row";
import { Icon } from "./ui/icon";

interface Props extends Elsewhere {
  runs: RunInfo[];
  agentName: (id: string) => string;
  onOpenConversation: (conversationId: string) => void;
  /** Names the run that handed out this work, when it is a delegated one. */
  parentTitle?: (run: RunInfo) => string | null;
  /** Waiting rows carry their request in place, so it is settled without leaving. */
  inline?: boolean;
  /** Reads the activity list again after a row changed something on the server. */
  onReload?: () => void;
  /** Names the list where it holds only part of what waits, as in the chat. */
  heading?: string;
  /** Drawn only while it holds a row: off the page about waiting work, "nothing" is noise. */
  hideWhenCalm?: boolean;
  className?: string;
}

const noop = () => undefined;

/** Approvals waiting anywhere plus runs that ended badly, one click from their conversation. */
export function AttentionCenter(props: Props) {
  const { runs, agentName, onOpenConversation, parentTitle, inline = false, heading: title = vi.attention } = props;
  const titles = useId();
  // Rows settled or dismissed from here leave at once, before the list is read again.
  const [settled, setSettled] = useState<string[]>([]);
  // Rows whose decision is still resuming their run. The run stops waiting as soon as the
  // server has the decision, and its row would leave with it — taking "Đang chạy tiếp…"
  // and any error from the resumed turn along before either could be read. Each stays where
  // it was listed, or the next request's buttons would slide under the pointer.
  const [held, setHeld] = useState<HeldRun[]>([]);
  const extra = held.filter((h) => !runs.some((run) => run.id === h.run.id));
  const listed = extra.length > 0 ? withHeld(runs, extra) : runs;
  const shown = listed.filter((run) => !settled.includes(seenKey(run)));
  // A job failing night after night is one row, saying how many nights (`foldRepeats`).
  const rows = foldRepeats(shown);
  const earlierOf = (run: RunInfo) => rows.find((row) => row.run.id === run.id)?.earlier ?? [];
  // "Nothing needs you" must hold for the whole manage screen, not just this list: the
  // nav still counts the work listed on the other page, and the two would contradict.
  const calm = shown.length === 0 && elsewhereCount(props) === 0;

  // A row that leaves takes the focus inside it along, and the next Tab would start over
  // from the top of the page: it goes to the row that took its place, or to the heading.
  const heading = useRef<HTMLHeadingElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const current = useRef(shown);
  current.current = shown;
  const currentRows = useRef(rows);
  currentRows.current = rows;
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
  const leave = (run: RunInfo, earlier: RunInfo[] = []) => {
    leaving.current = currentRows.current.findIndex((row) => row.run.id === run.id);
    setSettled((keys) => [...keys, seenKey(run), ...earlier.map(seenKey)]);
    setHeld((rows) => rows.filter((r) => r.run.id !== run.id));
  };
  const hold = (run: RunInfo) => {
    const kept = heldAt(current.current, run);
    setHeld((rows) => [...rows.filter((r) => r.run.id !== run.id), kept]);
  };

  // Said of a failure once it is read, and of a request found closed with nothing to decide.
  // A row standing for several failures of one job reads them all.
  const seenButton = (run: RunInfo) => {
    const earlier = earlierOf(run);
    return (
      <button
        type="button"
        className="ghost attention-seen"
        aria-label={vi.attentionSeenLabel(label(run, agentName(run.agent_id)))}
        onClick={() => {
          for (const each of [run, ...earlier]) markSeen(seenKey(each));
          leave(run, earlier);
        }}
      >
        <Icon name="check" />
        {earlier.length > 0 ? vi.attentionSeenAll(earlier.length + 1) : vi.attentionSeen}
      </button>
    );
  };

  const head = (run: RunInfo, preview: boolean) => {
    const parent = parentTitle?.(run);
    const repeats = earlierOf(run).length;
    return (
      <>
        <span className="attention-icon">
          <Icon name={icon(run)} />
        </span>
        <span className="attention-text">
          <span className="attention-title" id={`${titles}-${run.id}`}>
            {label(run, agentName(run.agent_id))}
            <span className="muted tabular">
              {" · "}
              <time className="attention-when" dateTime={run.started_at} title={dayClock(run.started_at)}>
                {dayOrClock(run.started_at)}
              </time>
            </span>
            {repeats > 0 && <span className="muted attention-repeats"> · {vi.attentionRepeats(repeats + 1)}</span>}
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

  if (props.hideWhenCalm && shown.length === 0) return null;
  const classes = ["attention", calm && "calm", props.className].filter(Boolean).join(" ");
  return (
    // Amber only while something is waiting on a person. A card that stays amber on an
    // empty list teaches the eye to skip it, which is the one thing it must not do.
    <section className={classes} aria-label={title} data-testid="attention">
      <h3 ref={heading} tabIndex={-1}>
        {title}
      </h3>
      {calm && (
        <p className="attention-calm">
          <Icon name="check" />
          {vi.attentionEmpty}
        </p>
      )}
      {shown.length > 0 && (
        <ul className="attention-list" ref={list}>
          {rows.map(({ run }) =>
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
      <AttentionElsewhere {...props} />
    </section>
  );
}
