/**
 * The bar at the foot of the panel that asks the agent about the passage selected in the canvas:
 * the passage, the lines it lies on, and a box for the question. It sits in the panel's flow, so
 * the text above shrinks to make room instead of being covered.
 *
 * A passage is picked in the canvas and the box opens on it; from then on the passage is kept
 * though the page's own selection goes, as pressing into the box takes it away. A passage chosen
 * anew while the box is open replaces it. Sending saves the canvas first, so the lines named are
 * those of a version the server holds, and asks nothing if the text changed meanwhile: the lines
 * would no longer be the ones the person saw. Every way it can fail leaves the question in the box.
 */

import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import type { MessageCanvas } from "../../api/artifact-types";
import { vi } from "../../i18n/vi";
import { type CanvasSelection, charCount } from "../../lib/canvas-selection";
import { showHiddenChars } from "../../lib/hidden-chars";
import type { SendResult } from "../../lib/send-result";

/** Why asking is off for now, if it is. */
export type AskDisabled = "busy" | "pending" | "budget" | null;

/** How much of the passage the bar shows, in characters. */
export const EXCERPT_CHARS = 80;
/** The lines holding a rendered selection are sent whole; past this many times the characters the
 *  person selected, the bar says so. */
export const LONGER_RATIO = 2;

type Props = {
  artifactId: string;
  /** What is selected in the canvas now; null when nothing is, or the text has changed since. */
  selection: CanvasSelection | null;
  /** Rises with every change to the canvas's text. */
  gen: number;
  hidden: boolean;
  disabled: AskDisabled;
  /** The panel's last save, which no version may be missing from: the version, or null. */
  flush(): Promise<number | null>;
  /** The chat's send. Answers once the server has taken the message, not when its turn is over. */
  onAsk(canvas: MessageCanvas, question: string): Promise<SendResult>;
  /** The question went through, so the passage is spent. */
  onAsked(): void;
};

type Held = { selection: CanvasSelection; gen: number };

/** The start of a passage on one line, the characters that cannot be seen written out. The marks
 *  come first: a pattern for spaces takes a byte-order mark for one. */
function excerptOf(text: string): string {
  const flat = showHiddenChars(text).replace(/\s+/g, " ").trim();
  const chars = Array.from(flat);
  return chars.length > EXCERPT_CHARS ? `${chars.slice(0, EXCERPT_CHARS).join("")}…` : flat;
}

const isComposing = (event: KeyboardEvent) => event.nativeEvent.isComposing || event.keyCode === 229;

const sameLines = (a: CanvasSelection, b: CanvasSelection) =>
  a.text === b.text && a.line_start === b.line_start && a.line_end === b.line_end;

export function CanvasAsk({ artifactId, selection, gen, hidden, disabled, flush, onAsk, onAsked }: Props) {
  const [held, setHeld] = useState<Held | null>(null);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const refocus = useRef(false);
  const latestGen = useRef(gen);
  latestGen.current = gen;
  const open = held !== null;

  // With the box open, a passage chosen anew is the one asked about, and the note about the old one
  // is spent. When the choice goes, the last passage stays.
  if (held && selection && (held.selection !== selection || held.gen !== gen)) {
    setHeld({ selection, gen });
    if (held.gen !== gen || !sameLines(held.selection, selection)) setError(null);
  }

  useEffect(() => {
    if (open) field.current?.focus();
    else if (refocus.current) button.current?.focus();
    refocus.current = false;
  }, [open]);

  const close = () => {
    refocus.current = root.current?.contains(document.activeElement) ?? false;
    setHeld(null);
    setQuestion("");
    setError(null);
  };

  /** The words of the failure, or null once the server has the question. */
  async function sendPassage({ selection: picked, gen: pickedGen }: Held, words: string): Promise<string | null> {
    const version = await flush();
    if (version === null) return vi.canvas.ask.notSaved;
    if (latestGen.current !== pickedGen) return vi.canvas.ask.changed;
    const { text, line_start, line_end } = picked;
    const result = await onAsk({ artifact_id: artifactId, selection: { version, text, line_start, line_end } }, words);
    return result.status === "failed" ? result.error : null;
  }

  const words = question.trim();
  const canSend = open && !sending && disabled === null && words !== "";
  const submit = async () => {
    if (!held || !canSend) return;
    setSending(true);
    setError(null);
    let failure: string | null;
    try {
      failure = await sendPassage(held, words);
    } catch {
      failure = vi.sendFailed.other;
    }
    setSending(false);
    if (failure !== null) {
      setError(failure);
      return;
    }
    close();
    onAsked();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (isComposing(event)) return;
    if (event.key === "Escape") {
      event.preventDefault();
      if (!sending) close();
    } else if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };

  const passage = held?.selection ?? selection;
  if (hidden || !passage) return null;
  const chars = charCount(passage.text);
  return (
    <div ref={root} className="canvas-ask" role="group" aria-label={vi.canvas.ask.group}>
      <blockquote className="canvas-ask-excerpt">{excerptOf(passage.text)}</blockquote>
      <div className="canvas-ask-row">
        <span className="canvas-ask-meta">{vi.canvas.ask.lines(passage.line_start, passage.line_end, chars)}</span>
        {!open && (
          <button
            ref={button}
            type="button"
            className="primary"
            disabled={disabled !== null}
            // Keeps the page's own selection, and the keyboard where it was, as the box takes over.
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => setHeld({ selection: passage, gen })}
          >
            {vi.canvas.ask.button}
          </button>
        )}
      </div>
      {chars > passage.shown * LONGER_RATIO && <p className="canvas-ask-note">{vi.canvas.ask.longer}</p>}
      {disabled && <p className="canvas-ask-note">{vi.canvas.ask[disabled]}</p>}
      {open && (
        <form
          className="canvas-ask-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <textarea
            ref={field}
            aria-label={vi.canvas.ask.question}
            placeholder={vi.canvas.ask.placeholder}
            rows={2}
            value={question}
            readOnly={sending}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={onKeyDown}
          />
          {error && (
            <div className="notice error" role="alert">
              {error}
            </div>
          )}
          <div className="canvas-ask-actions">
            <button type="submit" className="primary" disabled={!canSend}>
              {vi.send}
            </button>
            <button type="button" className="ghost" disabled={sending} onClick={close}>
              {vi.canvas.ask.cancel}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
