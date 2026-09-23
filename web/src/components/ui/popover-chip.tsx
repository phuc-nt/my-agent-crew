import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { Tone } from "./metric-card";

interface Props {
  /** What the pill says while closed: the one figure worth seeing without opening it. */
  label: ReactNode;
  /** Names the card that opens, for assistive tech. */
  popoverLabel: string;
  /** Tints the pill's border and dot; absent is the neutral grey. */
  tone?: Tone;
  /** A status dot before the label, for pills that report a state. */
  dot?: boolean;
  title?: string;
  testId?: string;
  className?: string;
  children: ReactNode;
}

/**
 * A pill in a header that opens a card of detail under it.
 *
 * The pill carries the headline, the card the breakdown and the switches, so a header
 * holds three short pills instead of every control in a row. The card closes on Escape,
 * on a click outside and on a second click of the pill; clicks inside it (a switch
 * being flipped) leave it open so several settings can be changed in one visit.
 *
 * Escape is the card's alone while it is open: it is caught before the app's own Escape
 * shortcut (which folds the activity panel) and hands focus back to the pill, so a
 * keyboard user closing the card lands where they opened it.
 */
export function PopoverChip({ label, popoverLabel, tone, dot = false, title, testId, className = "", children }: Props) {
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLDivElement>(null);
  const pill = useRef<HTMLButtonElement>(null);
  const cardId = useId();
  const card = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!open || !card.current || !pill.current) return;
    const room = window.innerHeight - pill.current.getBoundingClientRect().bottom - 24;
    card.current.style.setProperty("--popover-room", `${Math.max(160, room)}px`);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (anchor.current && !anchor.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      setOpen(false);
      pill.current?.focus();
    };
    document.addEventListener("mousedown", onPointer);
    // Capture on the window, so the app's own Escape listener never sees this key.
    window.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      window.removeEventListener("keydown", onKey, true);
    };
  }, [open]);

  return (
    <div className="popover-anchor" ref={anchor}>
      <button
        type="button"
        className={`pill${tone ? ` ${tone}` : ""}${open ? " open" : ""} ${className}`.trim()}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls={open ? cardId : undefined}
        ref={pill}
        title={title}
        data-testid={testId}
        onClick={() => setOpen((value) => !value)}
      >
        {dot && <span className="pill-dot" aria-hidden="true" />}
        {label}
        <span className="pill-caret" aria-hidden="true">
          ⌄
        </span>
      </button>
      {open && (
        <div className="popover" id={cardId} ref={card} role="dialog" aria-label={popoverLabel}>
          {children}
        </div>
      )}
    </div>
  );
}
